// One full registration + authentication round trip against a running
// `wrangler dev`. If this fails, the synthetic authenticator's byte
// encoding is wrong somewhere — fix it here before trusting any load-test
// numbers built on top of it.

import { syntheticRegister, syntheticAuthenticate } from "./synthetic-authenticator.js";

const BASE = process.env.BASE_URL || "http://localhost:8787";
// index.js::originFor() derives the expected origin from the real request
// URL, so a synthetic client must claim the same origin the Worker actually
// sees — http://localhost:8787 in local dev, https://0.computer once
// deployed for real. RP_ID (rpId, the WebAuthn relying-party) stays
// "0.computer" either way; that's a separate concept from origin.
const RP_ID = process.env.RP_ID || "0.computer"; // must match the Worker's own rpId(env) — see .dev.vars
const ORIGIN = process.env.ORIGIN || BASE;

async function post(path, body, opts = {}) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = text; }
  return { status: res.status, body: json };
}

async function main() {
  const handle = "smoketest-" + Math.random().toString(36).slice(2, 8);
  console.log("handle:", handle);

  const opts1 = await post("/register/options", { handle });
  if (opts1.status !== 200) throw new Error("register/options failed: " + JSON.stringify(opts1));
  console.log("1. register/options ok");

  const { registration, cred } = await syntheticRegister({
    rpId: RP_ID, origin: ORIGIN, challenge: opts1.body.options.challenge,
  });

  const verify1 = await post("/register/verify", {
    handle, challengeId: opts1.body.challengeId, registration,
  });
  if (verify1.status !== 200) throw new Error("register/verify failed: " + JSON.stringify(verify1));
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
  if (verify2.status !== 200) throw new Error("auth/verify failed: " + JSON.stringify(verify2));
  console.log("4. auth/verify ok — sessionToken issued:", !!verify2.body.sessionToken);

  // exercise the session + anchor + device-link paths too
  const token = verify2.body.sessionToken;
  const anchorReg = await post("/anchor/register", { name: "test-mini" }, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (anchorReg.status !== 200) throw new Error("anchor/register failed: " + JSON.stringify(anchorReg));
  console.log("5. anchor/register ok —", anchorReg.body);

  console.log("\nFULL ROUND TRIP PASSED — the real verifyRegistration/verifyAuthentication path works.");
}

main().catch((e) => { console.error("\nSMOKE TEST FAILED:", e.message); process.exit(1); });
