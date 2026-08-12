// 0.computer identity Worker.
//
// The whole promise, in code: a handle and a passkey, nothing else. No email
// field exists anywhere in this file — that is not an oversight to fix later,
// it is the point. See docs/product-model.md ("registration comes late and
// never gates the first run") and docs/reaching-zero.md (the private key
// never leaves the Secure Enclave; this Worker only ever sees the public half).
//
// rpID is "0.computer" (bare domain, no scheme) so ONE passkey works at any
// handle.0.computer — verified against @passwordless-id/webauthn's docs this
// session. rpID is baked into the credential at creation and can never change
// later, so this constant is load-bearing; do not casually edit it.

import { server } from "@passwordless-id/webauthn";
export { ChallengeStore } from "./challenge-store.js";
export { LinkStore } from "./link-store.js";
export { HandleRegistry } from "./handle-registry.js";
export { RateLimiter } from "./rate-limiter.js";

// WebAuthn requires the request origin's effective domain to equal rpID or
// be a subdomain of it — "localhost" is neither, so rpID must be
// environment-configurable to be testable at all without deploying for
// real. Production always resolves to "0.computer" (the default); local
// dev overrides via RP_ID in .dev.vars (gitignored, never committed).
function rpId(env) {
  return (env && env.RP_ID) || "0.computer";
}
const HANDLE_RE = /^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$/; // dns-label-safe, 3-32 chars
const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days — a phone shouldn't re-auth constantly
const ANCHOR_STALE_MS = 3 * 60 * 1000; // no heartbeat in 3 min = "offline", not "gone"

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function randomChallenge() {
  // base64url, per the library's documented expectation
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function claimChallenge(env, id, purpose) {
  const stub = env.CHALLENGES.get(env.CHALLENGES.idFromName(id));
  const res = await stub.fetch("http://do/claim", {
    method: "POST",
    body: JSON.stringify({ purpose }),
  });
  if (!res.ok) return null;
  const { challenge } = await res.json();
  return challenge;
}

async function putChallenge(env, id, challenge, purpose) {
  const stub = env.CHALLENGES.get(env.CHALLENGES.idFromName(id));
  await stub.fetch("http://do/put", {
    method: "POST",
    body: JSON.stringify({ challenge, purpose }),
  });
}

// Found by test/stress.js: a plain KV get-then-put on a handle key let 2 of
// 50 concurrent requests for the SAME handle both win. A Durable Object
// keyed by handle name gives a real mutex — see handle-registry.js.
function handleRegistryStub(env, handle) {
  return env.HANDLE_CLAIMS.get(env.HANDLE_CLAIMS.idFromName(handle));
}
async function claimHandle(env, handle) {
  const res = await handleRegistryStub(env, handle).fetch("http://do/claim", { method: "POST" });
  return res.ok;
}
async function releaseHandle(env, handle) {
  await handleRegistryStub(env, handle).fetch("http://do/release", { method: "POST" });
}

// --- sessions -----------------------------------------------------------
//
// A signed, stateless bearer token: {handle, exp} + HMAC-SHA256 over it,
// base64url. No server-side session table to manage or leak. The secret
// lives in env.SESSION_SECRET (a Worker secret, never committed — see
// README "before you deploy").

// Guards against a deploy that forgot `wrangler secret put SESSION_SECRET`
// (wrangler.toml only has it as a comment — nothing enforces it). Without
// this check, an unset secret makes crypto.subtle.importKey reject a
// zero-length HMAC key, which surfaces to the client as a bare, opaque
// {"error":"internal error"} 500 with no clue in the logs about why. This
// turns that into a diagnosable failure: a specific console.error() line an
// operator can find in `wrangler tail`, plus a distinct client-facing error
// instead of the generic catch-all.
class ConfigError extends Error {}

function assertSessionSecret(env) {
  if (!env.SESSION_SECRET || env.SESSION_SECRET.length < 20) {
    console.error("SESSION_SECRET missing or too short — run `wrangler secret put SESSION_SECRET` before deploying (see README)");
    throw new ConfigError("SESSION_SECRET missing or too short");
  }
}

async function hmacKey(env) {
  assertSessionSecret(env);
  return crypto.subtle.importKey(
    "raw", new TextEncoder().encode(env.SESSION_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]
  );
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function issueSession(env, handle) {
  const payload = JSON.stringify({ handle, exp: Date.now() + SESSION_TTL_MS });
  const payloadB64 = btoa(payload).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(env), new TextEncoder().encode(payloadB64));
  return `${payloadB64}.${b64url(sig)}`;
}

async function verifySession(env, token) {
  if (typeof token !== "string" || !token.includes(".")) return null;
  const [payloadB64, sigB64] = token.split(".");
  const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const ok = await crypto.subtle.verify(
    "HMAC", await hmacKey(env), sig, new TextEncoder().encode(payloadB64)
  );
  if (!ok) return null; // tampered or wrong secret — reject before even parsing
  const { handle, exp } = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")));
  if (Date.now() > exp) return null;
  return handle;
}

function bearerToken(request) {
  const h = request.headers.get("Authorization") || "";
  return h.startsWith("Bearer ") ? h.slice(7) : null;
}

// --- anchors --------------------------------------------------------------
//
// An anchor is a machine that can run Zero on this handle's behalf — a Mac
// mini that's always on, a laptop that comes and goes. Multiple anchors per
// handle, because the founder wants "add a host machine" to be normal, not
// a one-time migration.
//
// Reconnection itself is NOT this Worker's job — it is a client-side
// property of scripts/zero / launch_zero.sh (exponential backoff with
// jitter, capped, per Zero's "never auto-retry a mutation, retries are
// READ-tier only" rule extended to network reconnects). This Worker only
// ever answers one honest question: when did we last hear from it. A missed
// heartbeat means "offline right now", never "deregistered" — a laptop that
// sleeps overnight must not lose its place.

async function handleAnchorRegister(request, env) {
  const handle = await verifySession(env, bearerToken(request));
  if (!handle) return json({ error: "sign in first" }, 401);

  const { name, publicKey } = await request.json();
  if (typeof name !== "string" || !name.trim() || name.length > 60) {
    return json({ error: "give the machine a short name, like \"Mac mini\" or \"laptop\"" }, 400);
  }

  const key = `anchors:${handle}`;
  const existing = JSON.parse((await env.HANDLES.get(key)) || "[]");
  const anchorId = crypto.randomUUID();
  existing.push({
    id: anchorId, name: name.trim(), publicKey: publicKey || null,
    registered: Date.now(), lastSeen: Date.now(),
  });
  await env.HANDLES.put(key, JSON.stringify(existing));

  return json({ ok: true, anchorId });
}

async function handleAnchorHeartbeat(request, env) {
  const handle = await verifySession(env, bearerToken(request));
  if (!handle) return json({ error: "sign in first" }, 401);
  const { anchorId } = await request.json();

  const key = `anchors:${handle}`;
  const anchors = JSON.parse((await env.HANDLES.get(key)) || "[]");
  const anchor = anchors.find((a) => a.id === anchorId);
  if (!anchor) return json({ error: "unknown anchor" }, 404);

  anchor.lastSeen = Date.now();
  await env.HANDLES.put(key, JSON.stringify(anchors));
  return json({ ok: true });
}

async function handleAnchorList(request, env) {
  const handle = await verifySession(env, bearerToken(request));
  if (!handle) return json({ error: "sign in first" }, 401);

  const anchors = JSON.parse((await env.HANDLES.get(`anchors:${handle}`)) || "[]");
  const now = Date.now();
  return json({
    anchors: anchors.map((a) => ({
      id: a.id, name: a.name, registered: a.registered, lastSeen: a.lastSeen,
      online: now - a.lastSeen < ANCHOR_STALE_MS,
    })),
  });
}

// --- device linking (headless anchors) ------------------------------------
//
// "is there passkeys in terminal yet?" — no, and there structurally can't
// be: a terminal has no biometric sensor and no DOM. This is the correct
// substitute, the same shape gh/wrangler/tailscale already use: the human
// approves from a device that DOES have a passkey, the terminal only ever
// receives the resulting session — the private key never comes near it.

const CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // no 0/O/1/I/L
function generateLinkCode() {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return [...bytes].map((b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join("");
}

function linkStub(env, code) {
  return env.LINKS.get(env.LINKS.idFromName(code));
}

async function handleLinkStart(request, env) {
  const code = generateLinkCode();
  await linkStub(env, code).fetch("http://do/create", {
    method: "POST", body: JSON.stringify({ code }),
  });
  return json({
    code,
    approveUrl: `https://${rpId(env)}/link`,
    message: `On a device you've signed into before, go to https://${rpId(env)}/link and enter ${code}`,
    pollIntervalMs: 3000,
    expiresInSeconds: 600,
  });
}

async function handleLinkPoll(request, env) {
  const { code } = await request.json();
  if (typeof code !== "string") return json({ status: "unknown" }, 400);
  const res = await linkStub(env, code).fetch("http://do/poll", { method: "POST", body: "{}" });
  return json(await res.json(), res.status);
}

// Called from the browser, by an already-passkey-authenticated human, to
// approve a code they read off the anchor machine's screen.
async function handleLinkApprove(request, env) {
  const handle = await verifySession(env, bearerToken(request));
  if (!handle) return json({ error: "sign in first" }, 401);

  const { code } = await request.json();
  if (typeof code !== "string") return json({ error: "missing code" }, 400);

  // The approving human's OWN session is what gets handed to the anchor —
  // never re-derive or mint a token for a different handle here.
  const sessionToken = await issueSession(env, handle);
  const res = await linkStub(env, code).fetch("http://do/approve", {
    method: "POST", body: JSON.stringify({ handle, sessionToken }),
  });
  if (!res.ok) return json(await res.json(), res.status);
  return json({ ok: true, handle });
}

// --- CORS -------------------------------------------------------------
//
// rpID is the bare apex specifically so a passkey works at any
// handle.0.computer (see the file-header comment), and wrangler.toml
// mounts this Worker at 0.computer/api/identity/* — so a call from
// handle.0.computer to the apex is cross-origin by the browser's own
// definition, every time, by design. That means an explicit CORS policy
// isn't optional here; "same-origin by default" never applied.
//
// Reflect the Origin header only when it is exactly 0.computer or a
// *.0.computer subdomain — never a blanket "*". /anchor/*, /link/approve,
// and /anchor/register all read a bearer token from Authorization, and a
// wildcard would let any origin ride a signed-in user's credentialed
// cross-origin fetch.
const ALLOWED_ORIGIN_RE = /^https:\/\/([a-z0-9-]+\.)?0\.computer$/;

function corsHeaders(request) {
  const origin = request.headers.get("Origin");
  if (!origin || !ALLOWED_ORIGIN_RE.test(origin)) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function originFor(request) {
  // Trust only the Worker's own configured domain, never a client-supplied
  // header — Origin spoofing here would defeat the entire ceremony.
  const url = new URL(request.url);
  return `${url.protocol}//${url.host}`;
}

// --- rate limiting ----------------------------------------------------
//
// Every route below is reachable with no login and no per-client counter.
// handleRegisterOptions and handleAuthOptions each spin up a brand-new
// ChallengeStore Durable Object (crypto.randomUUID() + putChallenge) on
// every call; handleLinkStart does the same for LinkStore; handleRegisterVerify
// and handleAuthVerify each hit a DO too (claimChallenge, and claimHandle for
// registration). Unlimited, unauthenticated, that's real Cloudflare billing
// cost handed to anyone with a loop, and it eats the KV free-tier daily
// quota that legitimate signups need the same day.
//
// One RateLimiter DO instance per (route, client IP) — bounded cardinality,
// unlike the per-request crypto.randomUUID() DOs above, because real
// client IPs reuse the same instance every time. See rate-limiter.js.

function clientIp(request) {
  // Set by Cloudflare's edge; the platform overwrites any client-supplied
  // copy of this header before the Worker sees it, so it cannot be
  // spoofed in production. `wrangler dev` has no such edge, so every local
  // request collapses to one shared "unknown" bucket — expected, and still
  // exercises the limiting/429 code path (see test/stress.js rate-limit case).
  return request.headers.get("CF-Connecting-IP") || "unknown";
}

async function rateLimit(env, request, routeKey, { capacity, refillPerSec }) {
  const ip = clientIp(request);
  const stub = env.RATE_LIMITER.get(env.RATE_LIMITER.idFromName(`${routeKey}:${ip}`));
  const res = await stub.fetch("http://do/take", {
    method: "POST",
    body: JSON.stringify({ capacity, refillPerSec }),
  });
  return res.json(); // { allowed, retryAfterMs }
}

// Every unauthenticated route that writes to KV or touches a Durable
// Object gets a bucket. Authenticated routes (/anchor/*, /link/approve)
// already require a passkey ceremony to reach — a much higher bar than an
// anonymous script — so they're out of scope for this pass.
//
// /link/poll gets the largest bucket on purpose: handleLinkStart tells
// legitimate clients to poll every 3s for up to 600s (~200 polls) to
// complete one link — a tight per-route cap would break that normal flow,
// not just abuse of it.
const RATE_LIMITS = {
  "POST /register/options": { capacity: 20, refillPerSec: 20 / 60 },   // 20/min
  "POST /register/verify": { capacity: 20, refillPerSec: 20 / 60 },
  "POST /auth/options": { capacity: 20, refillPerSec: 20 / 60 },
  "POST /auth/verify": { capacity: 20, refillPerSec: 20 / 60 },
  "POST /link/start": { capacity: 10, refillPerSec: 10 / 60 },          // 10/min
  "POST /link/poll": { capacity: 40, refillPerSec: 1 },                 // 60/min, covers the 3s poll loop
};

async function handleRegisterOptions(request, env) {
  const { handle } = await request.json();
  if (typeof handle !== "string" || !HANDLE_RE.test(handle)) {
    return json({ error: "handle must be 3-32 lowercase letters, digits, or hyphens" }, 400);
  }
  const key = `handle:${handle}`;
  if (await env.HANDLES.get(key)) {
    return json({ error: "that handle is already claimed" }, 409);
  }

  const challenge = randomChallenge();
  const challengeId = crypto.randomUUID();
  await putChallenge(env, challengeId, challenge, "registration");

  return json({
    challengeId,
    // What the browser passes straight to client.register(...).
    options: {
      challenge,
      user: handle,
      domain: rpId(env),
      userVerification: "preferred",   // Face ID / Touch ID / Windows Hello
      attestation: false,              // "none": platform authenticators return
                                       // nothing useful under any conveyance,
                                       // verified this session — don't ask for
                                       // ceremony the device can't honor.
    },
  });
}

async function handleRegisterVerify(request, env) {
  const { handle, challengeId, registration } = await request.json();
  if (typeof handle !== "string" || !HANDLE_RE.test(handle)) {
    return json({ error: "invalid handle" }, 400);
  }

  const challenge = await claimChallenge(env, challengeId, "registration");
  if (!challenge) return json({ error: "challenge missing, expired, or already used" }, 410);

  // Atomic claim FIRST, before the expensive crypto verification below — a
  // losing racer gets a fast 409 instead of paying for a signature check
  // that was always going to be thrown away.
  const key = `handle:${handle}`;
  if (!(await claimHandle(env, handle))) {
    return json({ error: "that handle is already claimed" }, 409);
  }

  let verified;
  try {
    verified = await server.verifyRegistration(registration, {
      challenge,
      origin: originFor(request),
      domain: rpId(env),
      userVerified: false, // "preferred" was requested, not required — don't reject a valid PIN-less device
    });
  } catch (e) {
    await releaseHandle(env, handle); // a failed ceremony must not permanently squat the handle
    return json({ error: `registration could not be verified: ${e.message}` }, 400);
  }

  // Stored: the handle and the public key. Nothing else. No email, no IP log
  // tied to identity, no device fingerprint beyond what WebAuthn itself needs
  // to authenticate next time.
  await env.HANDLES.put(key, JSON.stringify({
    handle,
    credentials: [{
      id: verified.credential.id,
      publicKey: verified.credential.publicKey,
      algorithm: verified.credential.algorithm,
      transports: verified.credential.transports,
    }],
    created: Date.now(),
  }));

  return json({ ok: true, handle });
}

async function handleAuthOptions(request, env) {
  const { handle } = await request.json();
  const record = handle && (await env.HANDLES.get(`handle:${handle}`));

  const challenge = randomChallenge();
  const challengeId = crypto.randomUUID();
  await putChallenge(env, challengeId, challenge, "authentication");

  // Same status code and response shape whether or not the handle exists.
  // A missing/unknown handle gets a real challenge and one decoy credential
  // id instead of an early 400 — the client can't complete the ceremony
  // (no matching authenticator), but a prober can no longer tell "no such
  // handle" from "real handle" by status code or body shape alone. A
  // KV-lookup timing difference can still exist; this only closes the
  // free, instant status-code oracle.
  const credentials = record
    ? JSON.parse(record).credentials
    : [{ id: randomChallenge(), transports: ["internal"] }];

  return json({
    challengeId,
    options: {
      challenge,
      domain: rpId(env),
      userVerification: "preferred",
      allowCredentials: credentials.map((c) => ({ id: c.id, transports: c.transports })),
    },
  });
}

async function handleAuthVerify(request, env) {
  const { handle, challengeId, authentication } = await request.json();
  const record = handle && (await env.HANDLES.get(`handle:${handle}`));
  if (!record) return json({ error: "authentication failed" }, 401);

  const challenge = await claimChallenge(env, challengeId, "authentication");
  if (!challenge) return json({ error: "challenge missing, expired, or already used" }, 410);

  const { credentials } = JSON.parse(record);
  const cred = credentials.find((c) => c.id === authentication.id);
  if (!cred) return json({ error: "authentication failed" }, 401);

  try {
    await server.verifyAuthentication(authentication, cred, {
      challenge,
      origin: originFor(request),
      domain: rpId(env),
      userVerified: false,
    });
  } catch (e) {
    return json({ error: "authentication failed" }, 401); // never echo the library's detail to the client
  }

  const sessionToken = await issueSession(env, handle);
  return json({ ok: true, handle, sessionToken });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    const routes = {
      "POST /register/options": handleRegisterOptions,
      "POST /register/verify": handleRegisterVerify,
      "POST /auth/options": handleAuthOptions,
      "POST /auth/verify": handleAuthVerify,
      "POST /anchor/register": handleAnchorRegister,
      "POST /anchor/heartbeat": handleAnchorHeartbeat,
      "POST /anchor/list": handleAnchorList,
      "POST /link/start": handleLinkStart,
      "POST /link/poll": handleLinkPoll,
      "POST /link/approve": handleLinkApprove,
    };
    const cors = corsHeaders(request);

    // Every real route above is POST, so any browser call to one of them
    // that needs a preflight sends OPTIONS first. Answer it here, before
    // the route lookup — an OPTIONS entry per-path in `routes` would 404
    // on the exact request the preflight is trying to clear. No body, no
    // route check: if Origin didn't match, `cors` is empty and the missing
    // Access-Control-Allow-Origin fails the preflight closed, same as
    // today's default, but now by policy instead of by accident.
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    const routeKey = `${request.method} ${pathname}`;
    const handler = routes[routeKey];
    let response;
    try {
      const limit = RATE_LIMITS[routeKey];
      if (handler && limit) {
        const { allowed, retryAfterMs } = await rateLimit(env, request, routeKey, limit);
        if (!allowed) {
          response = json(
            { error: "too many requests — slow down and try again shortly" },
            429,
            { "Retry-After": String(Math.max(1, Math.ceil(retryAfterMs / 1000))) }
          );
        }
      }
      if (!response) {
        response = handler ? await handler(request, env) : json({ error: "not found" }, 404);
      }
    } catch (e) {
      // ConfigError (missing/short SESSION_SECRET) gets a distinct,
      // diagnosable message; console.error already ran in assertSessionSecret
      // so `wrangler tail` names the real cause. Everything else stays a
      // bare "internal error" — never leak stack traces to the client.
      response = e instanceof ConfigError
        ? json({ error: "server misconfigured — check Worker logs" }, 500)
        : json({ error: "internal error" }, 500);
    }
    for (const [key, value] of Object.entries(cors)) response.headers.set(key, value);
    return response;
  },
};
