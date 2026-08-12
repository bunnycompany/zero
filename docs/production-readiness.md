# Zero / 0.computer — Master Production-Readiness Report

For: founder. Scope: `/Users/dalnk/zero` (core agent, npm installer, GUI clients) and `/Users/dalnk/zero/identity` (Cloudflare Worker). Nothing in this pass was deployed, published, or pushed anywhere — every verification below ran locally (unit tests, `wrangler dev`, `swift build`, `./gradlew`, `npm pack --dry-run`).

---

## 1. GO/NO-GO SUMMARY

| Component | Light | One-liner |
|---|---|---|
| **Core agent** (main.py, brain/, danger_core/, zero/) | 🟡 YELLOW | Both blockers (crash-loses-queued-commands, no singleton lock) are fixed and verified; three medium/low gaps remain (backup/observation pruning, no error status on model-load failure) but none block a small launch. |
| **npm installer** (`npx @0-computer/zero`) | 🔴 RED | Packaging is now genuinely correct end-to-end locally, but `github.com/0-computer/zero` does not exist (`git ls-remote` → "Repository not found") — `setup.sh`'s clone step dies for every real user regardless of any other fix. |
| **Identity Worker** (identity/src/index.js) | 🔴 RED | Backend hardening (rate limiting, CORS, rpID bug, status-code oracle, secret validation) is now solid and verified — but there is no frontend (`register.html`/`link.html` don't exist), Cloudflare Workers Paid plan is not enabled (Durable Objects require it), and `SESSION_SECRET` has never been set. It has never been deployed once. |
| **Menubar app** (gui/) | 🔴 RED | Now builds into a real, launchable `Zero.app` locally (`packaging/build_macos_app.sh`) — but it's ad-hoc signed only; no Developer ID + notarization means Gatekeeper hard-blocks it on any Mac but the builder's own. |
| **Android app** (android/) | 🟢 GREEN (sideload only) | Release APK now signs and verifies cleanly (`apksigner verify --print-certs` passes) with a locally-generated keystore — this is the one distribution path that actually works today, for direct-sideload friends-and-family only, not Play Store. |
| **Observability** (journal/log/backup retention, status signaling) | 🟡 YELLOW | Journal rotation landed and is verified (10MB cap, 3 backups). Backup-directory pruning, observation-queue pruning, and model-load-failure status signaling are still unbounded/silent gaps — all fixable, none attempted this pass. |

---

## 2. WHAT GOT FIXED THIS PASS

All 13 attempted fixes report `outcome: fixed`, each with independent local verification (not just "tests pass" — most included a live repro of the original bug, a fix, and a re-check that the repro now succeeds). None failed. Two caveats are called out below where honesty requires it.

| # | Finding | Fix | Verification |
|---|---|---|---|
| 1 | Crash mid-batch lost every queued command behind the in-flight one (`main.py:44`, `zero/ns.py` `take_commands_full()` eagerly materialized `list(_claim_commands())`) | Added `iter_commands_full()` — a lazy generator claim-and-process loop in `main.py::handle_commands()` | Scripted a mid-batch crash (3 commands, brain raises on #2): command 3 stayed in `inbox/`, survived, replayed cleanly on simulated restart. Full suite: 96→ still green. |
| 2 | No singleton lock — launchd + manual launch could double-load the MLX model, OOM on 8GB Macs | `acquire_singleton_lock()` in `main.py`, `fcntl.flock` on `ZERO_ROOT/.zero.lock`, called before `build_brain()` | Real concurrent-process test: process A holds lock, process B refused with exit 1 and a clear stderr message, process C acquires cleanly after A exits. No stale-lock case (flock auto-releases on crash). |
| 3 | `namespace/log/journal.ndjson` had no rotation — unbounded growth | Size/count-based rotation in `zero/ns.py::log()` (10MB cap, 3 rotated backups) | Real 5,500-write loop against production constants: journal capped at 968KB, `.1` backup created at 10.49MB, `read_journal()` still correct with no gap. |
| 4 | Consolidator (`zero/consolidator.py`) never invoked — memory pipeline silently no-op'd | Wired `consolidator.run_once()` into `main.py`'s existing idle-tick branch (`idle_heartbeat()`) | Negative-control test: stripped the fix back out, test failed (`0 != 1`); restored, test passed. Proves the test catches the actual bug, not green-by-construction. |
| 5 | `setup.sh` written but excluded from published npm package (`npm/package.json:6` `files` array) | Added `"setup.sh"` to `files` | `npm pack --dry-run` now lists 5 files including setup.sh; extracted the real tarball and confirmed `fs.existsSync` (the exact check `zero.js` runs) now returns true. |
| 6 | `npm/package.json:11` license pointed at a `README.md` that didn't exist | Wrote `npm/README.md`; set license to `"UNLICENSED"` (accurate — never published, no OSS grant exists) | `npm pack --dry-run` now packages README.md (1.7kB); no license/install warnings. **Founder should confirm `UNLICENSED` is actually the intended terms before ever publishing** — this was a reasonable stand-in, not a legal decision this pass was authorized to make. |
| 7 | No rate limiting on any of 9 identity routes — unbounded DO/KV spend, handle-probe spam | New `RateLimiter` Durable Object (`identity/src/rate-limiter.js`), DO-per-(route,IP) token bucket, wired in front of `/register/options`, `/register/verify`, `/auth/options`, `/auth/verify`, `/link/start`, `/link/poll` | Live burst tests against real `wrangler dev`: 25 rapid `/register/options` → 19×200, 6×429; refill confirmed after wait; 429s still carry CORS headers; a 15-way concurrent handle-claim race still produces exactly 1 winner under the new limiter. **Caveat**: the repo's own `test/stress.js` 50-way concurrent tests now trip the rate limiter and report false failures when run back-to-back — that test file needs updating (not done this pass, flagged as a follow-up). |
| 8 | `handleAuthOptions` leaked handle existence via HTTP status code (400 vs 200) despite a comment saying "deliberately vague" (`identity/src/index.js:327-333`) | Rewrote to always return 200 with a real challenge + decoy credential for unknown handles | Live: unknown handle and real handle now return identical status/shape. Full smoke test (register→auth→anchor) and 50-way stress test still pass. |
| 9 | No CORS handling at all; `handle.0.computer → apex` is cross-origin by the product's own subdomain design | Added `corsHeaders()` with an anchored allowlist regex (`*.0.computer` and bare apex only, never `*`), `OPTIONS` short-circuit to 204 | Live curl tests: allowed origin gets headers, `evil.example.com` gets none, lookalike-suffix spoof (`0.computer.evil.com`) correctly rejected by the regex anchor. Smoke test still passes. |
| 10 | `SESSION_SECRET` unset fails closed today only by WebCrypto accident (empty-key rejection), not by design — opaque 500 with no diagnosis | `assertSessionSecret(env)` guard in `hmacKey()`, distinct `ConfigError` → `{"error":"server misconfigured — check Worker logs"}` | Real repro: pulled `.dev.vars` aside, hit `/anchor/register`, got the new diagnosable 500 with a log line naming the fix (`wrangler secret put SESSION_SECRET`). Restored `.dev.vars` after. |
| 11 | `handleAuthVerify` omitted `domain: rpId(env)` — auth breaks on any real deploy where login origin ≠ rpID (`identity/src/index.js`, verifyAuthentication call) | Added `domain: rpId(env)`, matching `handleRegisterVerify` | Reproduced for real: served from `RP_ID=0.computer` on a mismatched origin, pre-fix auth/verify returned 401; post-fix, same setup returns 200 with a session token. Regression-checked against normal localhost dev path too. |
| 12 | Menubar app was a bare Mach-O binary, not a `.app` bundle — nothing to double-click | New `packaging/build_macos_app.sh`: `swift build -c release`, assembles `Contents/{MacOS,Resources}`, real `Info.plist` (`LSUIElement=true`), ad-hoc codesign | Built and actually launched via `open Zero.app`; `lsappinfo` confirms bundle ID `computer.zero.menubar` running from inside the bundle; `codesign --verify` passes. |
| 13 | Android release build was literally unsigned (`app-release-unsigned.apk`, `apksigner verify` → no manifest) | Generated local keystore (`android/zero-release.keystore`, gitignored), added `signingConfigs`/`keystore.properties` loading to `android/app/build.gradle.kts` | `apksigner verify --print-certs app-release.apk` now shows a real V2 signer, exit code 0. Build without a keystore present still configures cleanly (guarded). |

**Duplicate-finding note**: two separate audit passes flagged the `SESSION_SECRET` gap (high severity in the identity audit, low in the danger_core audit) and two flagged rate-limiting/handle-enumeration together — one fix covers both listings in each case. Not double work, just double reporting upstream.

---

## 3. REMAINING PUNCH LIST

Ordered by severity. Every item here is either not `fixable_now` (needs a founder decision/credential) or was never attempted this pass.

### Blockers
1. **`github.com/0-computer/zero` does not exist.** `npm/package.json:12`, `npm/setup.sh:14` both point at a dead URL; `git ls-remote` confirms "Repository not found." *Why it matters*: every other npm fix is moot — `zero setup` still dies at the clone step for a real user. *Effort*: founder-only (push repo or bundle a source tarball instead), minutes to an hour of code if the tarball path is chosen.
2. **No Developer ID signing / notarization for the macOS app.** Confirmed 0 valid codesigning identities on this machine (`security find-identity -v -p codesigning`). *Why it matters*: any friend who receives `Zero.app` (AirDrop, download, USB) hits Gatekeeper's "can't be opened" wall on first launch — the exact first-contact experience that reads as malware to a non-technical user. *Effort*: founder must enroll in Apple Developer Program ($99/yr), get a cert; then ~1 day to wire `notarytool`/`stapler` into `packaging/build_macos_app.sh`.

### High
None outstanding — every "high" finding across all four audits was fixed and verified this pass (journal rotation, consolidator wiring, npm license, handle-enumeration leak, CORS, `SESSION_SECRET` guard).

### Medium
3. **`memory/observations/done/` never pruned.** `zero/memory.py:32-63` claims observations the same way `command/done/` does, but unlike commands there's no `prune_memory_done()` anywhere. *Why it matters*: unbounded disk growth for a "runs for weeks unattended" agent. *Effort*: small, ~1-2 hrs — mirror `ns.prune_done()`.
4. **`.zero-backups/` never pruned.** `danger_core/tools.py:117-124` snapshots every mutated file, forever, with no age/count cap. *Why it matters*: disk growth proportional to every LIVE-mode edit. *Effort*: small, ~1-2 hrs.
5. **Root `README.md` still teaches the broken manual install path.** `README.md:12` has a literal unfilled `<this repo>` placeholder; `README.md:13` assumes `python3.12` (this machine has 3.9.6); no mention of `npx` anywhere. *Why it matters*: a friend reading the README copy-pastes a command that fails verbatim. *Effort*: small, ~1 hr rewrite.
6. **No request-size limit on any of 9 identity routes.** Every handler calls `request.json()` before any size check (`identity/src/index.js:139,159,218,230,251,281,328,352`). Confirmed live: a 48MB POST parses fully (~1.1s) before being rejected. *Why it matters*: cheap CPU/memory cost lever, now that rate limiting exists this is the next cheapest DoS vector. *Effort*: small, ~1-2 hrs — one shared `Content-Length` check across handlers.
7. **`danger_core`'s write-denylist doesn't cover `tests/`.** `danger_core/policy.py:87-96` `_DENIED` protects `namespace/control`, `zero/`, `brain/`, `main.py` — not `tests/`. *Why it matters*: an unattended LIVE-mode agent can rewrite its own test suite to make a failing test pass instead of fixing the bug — a direct hit on the "verify every change" gate in `CLAUDE.md`, and the project's own stated threat model ("a small model at temperature," self-modification, not an external attacker). *Effort*: trivial, ~30 min — one line + a test.
8. **Durable Objects require the Cloudflare Workers Paid plan** ($5/mo min) — `wrangler.toml:20-34` binds `ChallengeStore`/`LinkStore`/`HandleRegistry`, none of which run on Free. *Why it matters*: `wrangler deploy` fails outright on a fresh/free account regardless of code readiness; undocumented anywhere in the repo. *Effort*: not code — billing decision.
9. **Play Store not viable for v0.1** — no signing beyond the local keystore generated this pass, no privacy policy, no Data Safety form, Google requires a closed-testing period for new accounts. *Why it matters*: only relevant if Play Store is the intended v0.1 channel; sideload already works. *Effort*: founder decision, not urgent.

### Low
10. **No status-channel signal on model-load failure.** `main.py:97-98` → `build_brain()` isn't wrapped in try/except; a crash leaves `namespace/status/current` stale instead of `error`. *Why it matters*: a human watching the menubar/`zero status` sees nothing informative; they'd have to read `daemon.log`. *Effort*: small, ~1 hr.
11. **Xcode CLT is a hard preflight blocker** for a CLI-only install (`npm/bin/preflight.js:52-58`) though the shipped installer never touches Swift. *Effort*: trivial, ~15 min.
12. **Debug APK is signed with the machine-local `~/.android/debug.keystore`**, not the new release keystore. *Why it matters*: only matters if that keystore is ever regenerated — forces an uninstall/reinstall for anyone who sideloaded a debug build. Not urgent for a one-off friend install. *Effort*: trivial if repeat distribution is planned.

---

## 4. WHAT ONLY THE FOUNDER CAN DO

Deduplicated across all four audits. Nothing here was or will be executed by this workflow.

**Accounts / plans**
- Enable Cloudflare Workers Paid plan ($5/mo min) on whatever account will host `identity/` — Durable Objects don't exist on Free at all, independent of code readiness.
- Enroll in the Apple Developer Program ($99/yr) and obtain a Developer ID Application certificate for macOS signing + notarization.
- Decide whether/when to pursue Google Play distribution (Play Console account fee, hosted privacy policy, Data Safety form, mandatory closed-testing period).

**Repository / DNS**
- Push this repo to a real, public `github.com/0-computer/zero` (or implement the alternative: bundle a source tarball inside the npm package instead of git-cloning) — `npm/setup.sh`'s clone step has no fallback today.
- When the identity frontend is built, decide what origin(s) `register.html`/`link.html` will be served from, so the CORS allowlist (already scoped to `*.0.computer`) matches reality.

**Secrets / credentials**
- Run `wrangler secret put SESSION_SECRET` with a real high-entropy value before any real identity deploy — nothing enforces this today beyond the new fail-closed guard (`identity/src/index.js`, `assertSessionSecret`).
- Take custody of the newly-generated Android signing keystore: `android/zero-release.keystore` + `android/keystore.properties` (gitignored, local-only). Back these up somewhere outside git — losing them means future release builds can't update devices that already have this build installed.

**Product / policy decisions**
- Set the retention/rotation numbers for `.zero-backups/` age cap and `memory/observations/done/` age cap (journal.ndjson's cap is now code-set at 10MB/3 backups — revisit if that number is wrong for the product).
- Confirm `tests/` should be added to `danger_core/policy.py`'s `_DENIED` list (a real repo/process decision, not applied silently by this pass).
- Confirm the `UNLICENSED` value now in `npm/package.json:11` is the actual intended terms before `npm publish` is ever run.
- Decide the real Android release-signing key's long-term owner/rotation policy if distribution grows past a handful of sideloads.

**Explicit deploy/publish actions — never run by this workflow**
- `git push` this repo to a real GitHub org.
- `npm publish` from `npm/` once the repo above exists and a fresh `npm pack --dry-run` is re-verified.
- `wrangler deploy` for `identity/` (currently the route mount in `wrangler.toml:47-48` is commented out — leave it that way until Paid plan + secret + frontend are all in place).
- Uncomment and load `packaging/launchd/computer.zero.agent.plist.template` for real unattended daemon operation.
- A real physical passkey ceremony test against a non-localhost RP_ID/origin pair, to confirm the `domain` fix (finding #11 above) holds up outside `wrangler dev` — the README already admits auth has "not been tested against a real passkey ceremony."

---

## 5. THE HONEST BOTTOM LINE

**Not production-ready for a friends-and-family launch today.** Two real crash/OOM blockers in the core agent got fixed and verified this pass, which matters — the agent itself is meaningfully closer to safe unattended operation than it was. But every actual *distribution* path still has a hard stop in front of it except one:

- **Android**: works. Signed, verified, sideloadable today.
- **macOS npm installer**: code is correct end-to-end, but points at a GitHub repo that doesn't exist. Dead on arrival for any real user regardless of anything else fixed.
- **macOS menubar app**: now double-clickable locally, but unsigned beyond ad-hoc — Gatekeeper stops it cold on any Mac but the one it was built on.
- **Identity Worker**: backend is now genuinely hardened (rate limiting, CORS, the rpID auth bug, the handle-enumeration oracle, the silent secret failure — all real bugs, all fixed and verified live). But it has never been deployed, there's no frontend to call it from, and the Cloudflare plan it needs isn't enabled. This is the least launch-ready piece by a wide margin, and — per `docs/product-model.md`'s own framing of identity as a separable, freely-offered feature — is arguably not on the critical path for a first local-agent-only friends test at all.

**The single highest-leverage action**: push this repository to a real `github.com/0-computer/zero`. It's minutes of founder work, it unblocks the one distribution channel (`npx @0-computer/zero`) that has been verified, end to end, to work correctly once that one dependency is satisfied — and it's the channel that puts the actual product (the local agent) in a friend's hands, independent of identity or the menubar app being ready. Everything downstream of that (macOS notarization, identity's frontend + paid plan) can follow as v1.1 without blocking a first small launch.