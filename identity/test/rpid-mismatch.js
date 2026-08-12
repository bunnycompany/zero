// Regression test for the missing `domain` key in handleAuthVerify's call to
// server.verifyAuthentication (index.js).
//
// The bug only shows up when the request's ORIGIN hostname differs from the
// Worker's configured RP_ID — exactly the shape of a real deployment, where
// a user's browser sits at https://someone.0.computer (origin) but every
// passkey is scoped to the shared relying party "0.computer" (rpId(env), see
// index.js's own header: "ONE passkey works at any handle.0.computer").
// Local dev normally hides this because .dev.vars sets RP_ID=localhost and
// wrangler dev also serves from a "localhost" origin, so origin-derived and
// configured rpId happen to collide.
//
// This test breaks that coincidence on purpose: it points RP_ID at
// "0.computer" (via `wrangler dev --var`, overriding .dev.vars) while still
// hitting the Worker over its real http://localhost:PORT origin. Before the
// fix: registration passes (handleRegisterVerify already sent `domain`) but
// authentication throws "Unexpected RpIdHash" inside handleAuthVerify's catch
// and surfaces as a generic 401. After the fix: both pass.
//
// Usage: start a wrangler dev instance with a mismatched RP_ID first, e.g.
//   npx wrangler dev --port 8788 --var RP_ID:0.computer
// then:
//   BASE_URL=http://localhost:8788 node test/rpid-mismatch.js

import { syntheticRegister, syntheticAuthenticate } from "./synthetic-authenticator.js";

const BASE = process.env.BASE_URL || "http://localhost:8788";
// What the Worker is configured with (must match the --var RP_ID passed to
// wrangler dev) — the value the options endpoints actually hand back as
// `domain`, and so what a real authenticator would bind its credential to.
const RP_ID = process.env.RP_ID || "0.computer";
// The origin the Worker itself derives from the request (originFor()) —
// deliberately NOT sharing a hostname with RP_ID above.
const ORIGIN = process.env.ORIGIN || BASE;

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = text; }
  return { status: res.status, body: json };
}

async function main() {
  const handle = "rpidtest-" + Math.random().toString(36).slice(2, 8);
  console.log(`Worker RP_ID=${RP_ID}  request origin=${ORIGIN}  (deliberately mismatched hostnames)`);
  console.log("handle:", handle);

  const opts1 = await post("/register/options", { handle });
  if (opts1.status !== 200) throw new Error("register/options failed: " + JSON.stringify(opts1));
  if (opts1.body.options.domain !== RP_ID) {
    throw new Error(`server is not actually configured with RP_ID=${RP_ID} (got domain=${opts1.body.options.domain}) — pass --var RP_ID:${RP_ID} to wrangler dev`);
  }
  console.log("1. register/options ok — domain:", opts1.body.options.domain);

  const { registration, cred } = await syntheticRegister({
    rpId: RP_ID, origin: ORIGIN, challenge: opts1.body.options.challenge,
  });

  const verify1 = await post("/register/verify", {
    handle, challengeId: opts1.body.challengeId, registration,
  });
  if (verify1.status !== 200) throw new Error("register/verify failed (expected to pass even with mismatch): " + JSON.stringify(verify1));
  console.log("2. register/verify ok —", verify1.body);

  const opts2 = await post("/auth/options", { handle });
  if (opts2.status !== 200) throw new Error("auth/options failed: " + JSON.stringify(opts2));
  console.log("3. auth/options ok");

  const authentication = await syntheticAuthenticate({
    rpId: RP_ID, origin: ORIGIN, challenge: opts2.body.options.challenge, cred,
  });

  const verify2 = await post("/auth/verify", {
    handle, challengeId: opts2.body.challengeId, authentication,
  });
  if (verify2.status !== 200) {
    throw new Error(
      "auth/verify failed: " + JSON.stringify(verify2) +
      "\n\nTHIS IS THE BUG: handleAuthVerify's server.verifyAuthentication call is missing " +
      "`domain: rpId(env)`, so it falls back to the request origin's hostname instead of the " +
      "Worker's configured RP_ID. Add `domain: rpId(env)` to the options object in handleAuthVerify " +
      "(index.js), mirroring handleRegisterVerify."
    );
  }
  console.log("4. auth/verify ok — sessionToken issued:", !!verify2.body.sessionToken);

  console.log("\nPASSED — auth verification correctly uses the configured RP_ID, not the request origin's hostname.");
}

main().catch((e) => { console.error("\nRPID-MISMATCH TEST FAILED:", e.message); process.exit(1); });
