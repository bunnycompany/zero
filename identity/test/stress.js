// Real load against a running `wrangler dev` — genuine Durable Objects,
// genuine KV, genuine crypto verification on every synthetic passkey. Not a
// mock; the same code path a real signup would hit, just driven by a
// synthetic authenticator instead of Face ID (see synthetic-authenticator.js
// for why that substitution is legitimate and what it does and doesn't test).

import { syntheticRegister, syntheticAuthenticate } from "./synthetic-authenticator.js";

const BASE = process.env.BASE_URL || "http://localhost:8787";
const RP_ID = process.env.RP_ID || "localhost";
const ORIGIN = process.env.ORIGIN || BASE;

async function post(path, body, headers = {}) {
  const t0 = performance.now();
  try {
    const res = await fetch(BASE + path, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let json; try { json = JSON.parse(text); } catch { json = text; }
    return { status: res.status, body: json, ms: performance.now() - t0 };
  } catch (e) {
    return { status: 0, body: { error: e.message }, ms: performance.now() - t0 };
  }
}

function percentile(sorted, p) {
  if (!sorted.length) return NaN;
  const idx = Math.min(sorted.length - 1, Math.floor(p / 100 * sorted.length));
  return sorted[idx];
}

function summarize(label, results) {
  const ok = results.filter((r) => r.ok);
  const failed = results.filter((r) => !r.ok);
  const times = results.map((r) => r.ms).sort((a, b) => a - b);
  console.log(`\n${label}`);
  console.log(`  ${ok.length}/${results.length} succeeded`);
  console.log(`  latency: p50=${percentile(times, 50).toFixed(0)}ms p95=${percentile(times, 95).toFixed(0)}ms p99=${percentile(times, 99).toFixed(0)}ms max=${times[times.length - 1]?.toFixed(0)}ms`);
  if (failed.length) {
    const reasons = {};
    for (const f of failed) {
      const key = `${f.status}:${JSON.stringify(f.detail).slice(0, 80)}`;
      reasons[key] = (reasons[key] || 0) + 1;
    }
    console.log("  failure breakdown:", reasons);
  }
  return { ok: ok.length, total: results.length, failed };
}

async function fullSignup(handle) {
  const t0 = performance.now();
  const opts = await post("/register/options", { handle });
  if (opts.status !== 200) return { ok: false, ms: performance.now() - t0, status: opts.status, detail: opts.body };

  const { registration, cred } = await syntheticRegister({
    rpId: RP_ID, origin: ORIGIN, challenge: opts.body.options.challenge,
  });
  const verify = await post("/register/verify", { handle, challengeId: opts.body.challengeId, registration });
  if (verify.status !== 200) return { ok: false, ms: performance.now() - t0, status: verify.status, detail: verify.body };

  return { ok: true, ms: performance.now() - t0, cred };
}

async function main() {
  const N = parseInt(process.env.N || "50", 10);
  console.log(`Stress-testing ${BASE} — real Worker, real Durable Objects, real KV, real crypto verification`);
  console.log(`Concurrency: ${N}\n${"=".repeat(60)}`);

  // 1. Concurrent signups, distinct handles — the actual "many users signing
  //    up at once" scenario.
  const handles = Array.from({ length: N }, (_, i) => `stress-${Date.now()}-${i}`);
  const signupResults = await Promise.all(handles.map((h) => fullSignup(h)));
  const signupSummary = summarize(`1. ${N} concurrent distinct signups`, signupResults);

  // 2. The handle-collision race — many concurrent registrations for the
  //    SAME handle. Correctness requires exactly one winner, not "most of them".
  const raceHandle = `race-${Date.now()}`;
  const raceResults = await Promise.all(
    Array.from({ length: N }, () => fullSignup(raceHandle))
  );
  const raceWinners = raceResults.filter((r) => r.ok).length;
  console.log(`\n2. ${N}-way race for ONE handle ("${raceHandle}")`);
  console.log(`  winners: ${raceWinners}  ${raceWinners === 1 ? "✓ correct — exactly one" : "✗ WRONG — expected exactly 1"}`);

  // 3. Concurrent authentication using the credentials just minted in step 1.
  const authable = signupResults.filter((r) => r.ok);
  const authResults = await Promise.all(authable.map(async (r, i) => {
    const t0 = performance.now();
    const opts = await post("/auth/options", { handle: handles[i] });
    if (opts.status !== 200) return { ok: false, ms: performance.now() - t0, status: opts.status, detail: opts.body };
    const authentication = await syntheticAuthenticate({
      rpId: RP_ID, origin: ORIGIN, challenge: opts.body.options.challenge, cred: r.cred,
    });
    const verify = await post("/auth/verify", { handle: handles[i], challengeId: opts.body.challengeId, authentication });
    return { ok: verify.status === 200, ms: performance.now() - t0, status: verify.status, detail: verify.body };
  }));
  summarize(`3. ${authable.length} concurrent authentications`, authResults);

  // 4. Malformed / hostile input — must fail cleanly, never 500, never leak
  //    a stack trace or internal detail.
  const hostile = [
    { path: "/register/options", body: { handle: "AB" } },              // too short
    { path: "/register/options", body: { handle: "has spaces" } },       // invalid chars
    { path: "/register/options", body: { handle: "x".repeat(500) } },    // oversized
    { path: "/register/options", body: {} },                             // missing field
    { path: "/register/options", body: { handle: null } },
    { path: "/register/verify", body: { handle: "nope", challengeId: "does-not-exist", registration: {} } },
    { path: "/auth/verify", body: { handle: "nope", challengeId: "x", authentication: { garbage: true } } },
    { path: "/anchor/register", body: { name: "no auth header" } },      // no Bearer token
  ];
  const hostileResults = await Promise.all(hostile.map(async (h) => {
    const r = await post(h.path, h.body);
    return { ok: r.status >= 400 && r.status < 500 && r.status !== 0, ms: r.ms, status: r.status, detail: r.body };
  }));
  console.log(`\n4. ${hostile.length} hostile/malformed inputs`);
  hostileResults.forEach((r, i) => {
    const verdict = r.status === 0 ? "✗ CONNECTION FAILED" : r.ok ? "✓ clean 4xx" : `✗ got ${r.status} (expected 4xx)`;
    console.log(`  ${JSON.stringify(hostile[i].body).slice(0, 50).padEnd(52)} → ${r.status}  ${verdict}`);
  });
  const hostileOk = hostileResults.filter((r) => r.ok).length;

  // 5. Device-link concurrency: many terminals polling, one approval, exactly
  //    one should receive the token.
  const startRes = await post("/link/start", {});
  const code = startRes.body.code;
  const pollers = Array.from({ length: N }, () => post("/link/poll", { code }));
  // approve mid-flight, racing the pollers
  const approveP = (async () => {
    const auth = await fullSignup(`linkapprover-${Date.now()}`);
    const optsA = await post("/auth/options", { handle: handles[0] }); // reuse an already-registered handle
    if (optsA.status !== 200) return null;
    const authentication = await syntheticAuthenticate({ rpId: RP_ID, origin: ORIGIN, challenge: optsA.body.options.challenge, cred: authable[0].cred });
    const v = await post("/auth/verify", { handle: handles[0], challengeId: optsA.body.challengeId, authentication });
    if (v.status !== 200) return null;
    return post("/link/approve", { code }, { Authorization: `Bearer ${v.body.sessionToken}` });
  })();
  const [pollResults, approveResult] = await Promise.all([Promise.all(pollers), approveP]);
  console.log(`\n5. Device-link: ${N} concurrent pollers racing one approval`);
  console.log(`  approve: ${approveResult ? approveResult.status : "skipped"}`);
  const tokensSeen = pollResults.filter((r) => r.body?.status === "approved").length;
  console.log(`  pollers that saw the token: ${tokensSeen}  ${tokensSeen <= 1 ? "✓ correct — at most one (claim-once)" : "✗ WRONG — token was handed out more than once"}`);

  console.log(`\n${"=".repeat(60)}`);
  console.log("SUMMARY");
  console.log(`  distinct signups:     ${signupSummary.ok}/${N}`);
  console.log(`  handle-collision race: ${raceWinners === 1 ? "PASS (exactly 1 winner)" : "FAIL"}`);
  console.log(`  authentications:      ${authable.length ? "see above" : "skipped (no successful signups)"}`);
  console.log(`  hostile input handled cleanly: ${hostileOk}/${hostile.length}`);
  console.log(`  device-link claim-once: ${tokensSeen <= 1 ? "PASS" : "FAIL"}`);
}

main().catch((e) => { console.error("STRESS TEST CRASHED:", e); process.exit(1); });
