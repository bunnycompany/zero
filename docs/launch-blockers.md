# Zero: Non-Code Launch Blockers — Founder Decision Brief

*Synthesis of five research streams (privacy/legal, economics, gateway SPOF, support). Not legal advice — §6 flags where a lawyer is actually required. Two rules frame everything: don't charge a stranger for a promise you can't keep today, and don't store an EU friend's key without a deletion path.*

---

## 1. THE LAUNCH BLOCKERS (ranked, each with the single next action)

These are the things that must be resolved **before charging a stranger money or storing an EU friend's key.** Everything else is a fast-follow.

**#1 — "Private by construction" copy while the enclave doesn't exist.** *(Highest risk. FTC §5 deception, direct Zoom precedent.)* Advertising an unbuilt, verifiable cryptographic guarantee as a live feature is textbook unsubstantiated-claim deception (FTC Advertising Substantiation doctrine; *FTC v. Zoom*, 2020 — 20 years of assessments for claiming an encryption property Zoom didn't deliver). **Next action:** rewrite every hosted-compute claim to explicit future tense and make it unpurchaseable (exact wording in §2). Nothing about danger.plus privacy ships present-tense until the enclave verifies. *(Privacy/legal Q4.)*

**#2 — Passkey-signed deletion endpoint before any EU friend's key is stored.** "No email = no PII" is false: the handle + WebAuthn public key + registration IP/rendezvous logs are **pseudonymous personal data** under GDPR Art. 4(1)/Recital 26, and you are the controller for the identity layer. GDPR reaches a US founder who knowingly onboards EU-resident friends (Art. 3(2); free counts). The right answer is elegant: **the user signs a "delete my handle" challenge with their passkey** — stronger than an email link, no PII needed (Art. 11 governs). **Next action:** build the passkey-authenticated deletion path with true *cascading* deletion (KV handle→key record, all coordinator/IP/rendezvous logs, backups). This is engineering, not a legal judgment call — build it now. *(Privacy Q1/Q2.)*

**#3 — Don't sell "always-on" against an origin that emits 530s.** The paid pitch is *"awake all the time, even when your Mac is off."* danger.plus is a single Mac on one Cloudflare tunnel (the 530 is the fingerprint of a single unmanaged origin — Cloudflare's edge reporting "origin gone"), with an honest availability ceiling of ~95–99%. Billing a 24/7 guarantee against an intermittently-dead gateway is a refund/chargeback *and* trust liability. **Next action:** label the hosted tier "beta / best-effort, no SLA" and do not attach an uptime promise until Option B redundancy exists (§4). *(Gateway SPOF §2.)*

**#4 — A minimal, honest, two-layer privacy policy.** App stores require one; GDPR Arts. 13–14 require transparency to any EU data subject. Achievable as a 1–2 page Signal-style doc. **Next action:** draft it leading with the local-tier truth ("nothing leaves your Mac"), then honestly enumerate the coordinator identifiers (handle, public key, registration IP, rendezvous timestamps, retention), then the passkey deletion path — then hand to counsel for legal-basis wording. *(Privacy Q3.)*

**#5 — The one guardrail that protects the flat price.** Not a blocker at friends-and-family scale (the tail is socially bounded — you know everyone), but must exist **before the base grows past people you know.** A single unbounded/scripted account is the bankruptcy vector, not the honest heavy user. **Next action:** ship a per-account concurrency cap (§3) before the first *stranger* pays. *(Economics §2.)*

**Not blockers now (documented, deferred):** CCPA/CPRA (thresholds — $26.6M revenue or 100k CA users — are nowhere close); EU Art. 27 representative (plausible "occasional processing" exemption at beta scale, but a lawyer question — §6); hosted redundancy Option B (premature spend).

---

## 2. THE PRIVACY-CLAIM DECISION — exact wording for "private by construction"

**The bright line:** the moment a user can **pay** for hosted compute, every enclave/privacy claim attached to it must be true and client-verifiable *at that moment*. Present-tense or billable before the enclave verifies = the Zoom fact pattern.

**Do NOT ship, anywhere (site, pricing card, app, onboarding):**
- ❌ "Runs in a sealed enclave your device can verify"
- ❌ "Hosted, but nobody can read it" / "even we can't read it" — as an *available* feature
- ❌ any present-tense description of danger.plus privacy as a thing you can buy today

**DO ship — future-tense, explicitly gated, unpurchaseable:**

> **Hosted compute (danger.plus) is not yet available.** When it launches, it will run in an attested enclave that your own device can verify — and we won't ship a version we could read. We'll announce it when that guarantee is real.

Three conditions make roadmap framing safe: (a) it's unmistakably future, (b) users **cannot pay** for it yet, (c) the aspiration does not bleed into the description of what they're buying *today*. Keep marketing copy and the privacy policy **consistent** — the FTC's classic hook is the gap between the two. This copy gets a lawyer's eyes before any public site goes up (§6). *(Privacy Q4.)*

---

## 3. THE MONEY DECISION — flat price + the one guardrail, with arithmetic

**Defensible flat price: $15–20/month** for a small-model (multiplexed Mac) tier. Below $10 is fragile (one heavy user + overhead eats it); above $25 breaks the "friends" framing.

**The arithmetic.** Multiplexed COGS on Mac minis: ~$25–30/mo per always-on box; an ambient agent is ~99% idle, so oversubscribe 10–20 users/box → **~$1.5–3/user-month.** Break-even at $20 (variable rate $0.20/M tokens) is **100M tokens/mo ≈ 1,333 turns/day** — no honest human hits that. A 100-user book (90 median @ $2.25, 5 heavy @ $7.50, 5 whale @ $30) = $3.90 avg → **~80% gross margin at $20.** The portfolio survives a *bounded* tail and dies only on an *unbounded* one: one scripted/multi-instance account at 500M–1B tokens = $100–200+/mo, wiping ~10–13 paying users.

**The ONE guardrail: a per-account concurrency cap (1–2 in-flight requests).** Highest-leverage move — it caps *instantaneous* cost, is invisible to any real human, kills the parallel-loop abuse vector, and matches Zero's architecture (`main.py` is concurrency-1 per instance, so abuse = many instances against one account). **Throttle/queue, never bill, never hard-cut** — that's what preserves the "no surprise bill" promise. *(Economics §2/§3.)*

**Critical repricing caveat:** do **not** attach "private by construction" to a shared-mini deployment — it isn't true there (no hardware enclave). The *enclave* promise requires a confidential H100 (~$2,700/GPU-month = ~135–180 users at $15 just to break even on one GPU), which F&F volume cannot cover. That arithmetic is *why* hosting waits — the delay is financially correct, not something to apologize for.

---

## 4. THE UPTIME DECISION — one posture for the SPOF

**Posture: do not stake v1 on danger.plus reliability. The free local tier is the load-bearing product; the paid/hosted tier ships as explicitly "beta / best-effort."** Spend the cheap reliability budget on honest degradation, not on a second always-on Mac (Option B redundancy) yet.

**The scoping correction that makes this safe:** identity is **entirely Cloudflare** (Workers/DO/KV — zero danger.plus dependency), and the *recommended* remote-reach path (mesh/Tailscale) doesn't touch the gateway either. The gateway's uptime caps only (a) the paid hosted tier and (b) the relay *fallback* for remote reach. The one discipline: never let anyone wire identity or the default remote path through the gateway later "because it was there."

**What MUST degrade to local (and how):**
- **Mac-resident users' think-loop.** Today `RemoteBrain._generate` returns `""` on failure → the turn is silently *lost*. **The single highest-leverage code fix:** on gateway failure, run the turn on the local `BrainOrchestrator` instead of dropping it (bounded read-only retry first, per `executor.py`'s never-retry-mutations rule). Turns a gateway blip into transparent local degradation. Cheapest, pure code.
- **Big models that don't fit locally:** degrade to the local small model with a *labeled* message ("running your on-Mac model; the large model is unreachable") — never silent.
- **Default remote-reach to mesh, not relay**, so the gateway is off the reach critical path.

**What genuinely CANNOT degrade — so the copy must be honest:** "always-on when your Mac is off" is definitionally un-local; **phone-only/no-Mac users' uptime *equals* the gateway's uptime, full stop.** These populations are the smallest at F&F scale, which is why the cheap code fix covers most of the risk and Option B (hosted redundancy) is premature. The interface must never present a gateway-dependent feature as "always available" — same discipline as shadow mode announcing itself. *(Gateway SPOF §1–3.)*

---

## 5. THE SUPPORT PRINCIPLE

Local-first doesn't remove the support burden — it **relocates** it: the founder trades "I can log in and see the problem" for "the user is my only sensor." You have zero passive telemetry. Every privacy product that survived this (Tailscale, Signal, Obsidian, Standard Notes) solved it by making the user a willing, consent-gated reporter — not by peeking.

**The diagnostic principle (one line):** *The diagnostic shares the **shape** of the failure, never the **content** of the session; the user sees exactly what leaves, decides that it leaves, and chooses where it goes.*

Concretely, steal Tailscale's `bugreport`: **user-initiated only (never remote, never automatic); reviewable before it leaves the machine; redacted by construction via an allowlist** (app version, OS, model id, tier, error type, failing tool name, *which* `ns.py` channels are unhealthy — **never** channel contents, home paths, observer context, prompt/answer text, or file contents). Produce a short opaque code the user can read aloud plus an optional reviewed bundle; copy to clipboard and let the *human* choose the channel — no "send to founder" button that quietly recreates a data pipe home. At F&F scale the honest support model is *you, a text thread, and a good diagnostic button* — don't over-build a helpdesk. Note the alignment: **danger.plus subscribers are the one cohort whose problems you *can* see** (gateway health, never enclave contents), which cleanly justifies a paid private channel without violating the privacy promise.

**The onboarding expectation-setting line** (the largest lever on support load — most tickets are the gap between expected and actual):

> **Zero keeps everything on your Mac, runs a small brain sized for your computer, asks before it acts, and is asleep when your Mac is asleep. When something breaks, press "Something's wrong" and send the summary to whoever set up Zero for you — because it stays on your Mac, that's the only way we can see what went wrong.**

Onboarding must NOT imply "Siri that does everything," must NOT promise always-on for the free tier, must NOT dangle danger.plus/enclave as available, and must NOT promise a support SLA. *(Support §1–3.)*

---

## 6. WHERE A LAWYER IS ACTUALLY REQUIRED

Spend legal money only here (ideally counsel comfortable with **FTC advertising + GDPR**):

1. **The "private by construction" marketing copy — highest priority.** Every public claim about hosted-compute privacy. Review before the site launches, and again before hosting is billable. This is the FTC-deception surface. *(Privacy Q4; Gateway §3; Support flags.)*
2. **GDPR applicability + Art. 27 EU-representative decision.** Whether onboarding EU-resident friends triggers targeting, and whether the "occasional processing" exemption from appointing an EU rep genuinely applies (EDPB reads it narrowly). Get it documented. *(Privacy Q1.)*
3. **Legal-basis (Art. 6) wording** for holding the handle+key (legitimate interest vs. contract) and Arts. 13–14 transparency completeness in the policy. *(Privacy Q3.)*
4. **The Art. 11 deletion posture** — sign-off that "passkey-signed request only; no email fallback; unauthenticated requests declined" is defensible as written. *(Privacy Q2.)*
5. **Any uptime/SLA language** in the paid-tier copy ("always-on," "24/7") — a service-level representation to paying customers; confirm it isn't an actionable misrepresentation given observed reliability. *(Gateway §3.)*
6. **ToS / liability for an agent that takes actions on the user's machine** (the danger_core executor) — adjacent but important for a launch to non-technical users.
7. **Cloudflare KV sub-processor + cross-border transfer** disclosures (EU data landing in Cloudflare — SCCs/transfer language?) and confirmation that the "no PII" claim holds given a handle can be a real name. *(Privacy Q3; Support flags.)*

**Sources:** GDPR Recital 26, Arts. 4/11/17/27, Art. 3(2); EDPB Guidelines 3/2018; FTC Advertising Substantiation Policy Statement; *FTC v. Zoom* (2020); CCPA/CPRA 2026 thresholds (IAPP, Clym); Signal privacy policy; Tailscale `bugreport` docs; Obsidian/Standard Notes support models; Cloudflare 1016/530 docs; mlx-lm #965; internal `docs/product-model.md`, `docs/fleet-brain.md`, `docs/reaching-zero.md`, `brain/remote.py`.