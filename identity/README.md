# 0.computer identity

Anonymous passkey identity for `you.0.computer`, plus device-linking for
headless anchor machines. See `docs/product-model.md` and
`docs/reaching-zero.md` for the design this implements.

## The rule this code exists to keep

No email field. No password field. Ever. A handle and a device-bound
passkey are the whole account. Registration is opt-in for remote reach —
Zero itself works fully, locally, forever, without any of this.

## What's here

| file | what |
|---|---|
| `src/index.js` | the Worker: register/auth passkey ceremonies, sessions, anchors, device-link |
| `src/challenge-store.js` | single-use WebAuthn challenges (Durable Object — KV's eventual consistency can't guarantee single-use) |
| `src/link-store.js` | pending device-link codes (see "Headless anchors" below) |

## Verified this session, and how

- **Library choice**: `@passwordless-id/webauthn`, not `simplewebauthn` —
  the latter is only "unofficially supported" on Workers per its own docs;
  the former is built on `crypto.subtle` and officially lists Cloudflare
  Workers as supported. Checked directly against the library's docs.
- **rpID**: `"0.computer"` (bare domain). Confirmed one passkey registered
  against that rpID authenticates at any `handle.0.computer` — WebAuthn
  validates origin as rpID-or-subdomain. **This cannot be changed later
  without re-registering every passkey** — do not casually edit `RP_ID`.
- **Challenge storage**: a Durable Object, not KV, because KV is eventually
  consistent and a delete-after-read there isn't atomic globally — a
  replayed challenge is a real vulnerability, not a theoretical one.
- **Attestation**: `"none"`. Apple's platform authenticators return no
  usable attestation under any conveyance; asking for more buys nothing.
- **The Worker builds and bundles cleanly** on the real Workers runtime, no
  `nodejs_compat` flag needed: `npx wrangler deploy --dry-run` passes,
  53KB total, all three bindings (2 Durable Objects + 1 KV) resolve.

## What's NOT verified, honestly

A real `navigator.credentials.create()/get()` ceremony needs an actual
browser with an actual authenticator (Face ID, Touch ID, a security key) —
that cannot be exercised from a terminal. **The registration and
authentication endpoints have not been tested against a real passkey
ceremony.** Before this goes live: build the two-page static frontend
(`register.html`, `link.html`), run it against `wrangler dev`, and complete
a real registration + login with an actual device.

## Headless anchors: "is there passkeys in terminal yet?"

No — and structurally can't be. A terminal has no biometric sensor and no
DOM to run the WebAuthn API in. Bypassing that would defeat the reason
passkeys are safe.

The correct substitute, same shape as `gh auth login`, `wrangler login`,
and (closest precedent) `tailscale up`:

```
$ zero link
  To connect this machine, go to https://0.computer/link
  and enter the code:  X7K2-M9QR

  waiting…
```

1. The anchor calls `POST /link/start` → gets a short high-entropy code
   (~40 bits, 10-minute TTL) and starts polling `POST /link/poll`.
2. The human opens `0.computer/link` on a device they've already
   registered a passkey on, authenticates for real (the actual ceremony,
   the actual biometric check), types the code, and the browser calls
   `POST /link/approve` with its own session bearer token.
3. The Worker mints a session for the *approving human's handle* and hands
   it to the polling anchor via the next `/link/poll` response — **once**;
   the token is deleted from the Durable Object the moment it's collected,
   so a stolen poll response can't be replayed for a second copy.
4. The anchor now holds a normal 30-day session token and can call
   `/anchor/register`, `/anchor/heartbeat` like any authenticated client.

The private key never leaves the approving device. The anchor never sees a
passkey ceremony, real or synthetic — it only ever receives the *result* of
one that happened somewhere it could be trusted.

**Reconnection** (an anchor that goes offline and comes back — a laptop
closing its lid, a Mac mini losing power) is deliberately **not** this
Worker's job. It is `scripts/zero`'s job, client-side: exponential backoff
with jitter, capped, so a flaky connection doesn't hammer the Worker or
burn the anchor's battery. `/anchor/heartbeat` just answers one honest
question — when did we last hear from it — and a missed heartbeat means
*offline right now*, never *deregistered*.

## Before you deploy (all still gated on an explicit human go-ahead)

```bash
npm install
wrangler kv namespace create HANDLES        # → paste the id into wrangler.toml
wrangler secret put SESSION_SECRET          # a long random value, never committed
wrangler dev                                # local only — does not touch production
```

`npm run deploy` is a deliberate stub. Going live on the real domain is a
separate, explicit step — same rule as everywhere else in this project.

## What's next, in order

1. Static `register.html` / `link.html` frontend (paper/ink/amber tokens,
   per `docs/north-star.html`) — needed before any real device test.
2. A real end-to-end test: register a passkey, authenticate, link a second
   "anchor" device, confirm a session round-trips.
3. ~~Rate limiting on `/link/start` and `/auth/options`~~ — done. A
   DO-backed token bucket (`src/rate-limiter.js`, `RATE_LIMITS` in
   `src/index.js`) now sits in front of every unauthenticated route:
   `/register/options`, `/register/verify`, `/auth/options`, `/auth/verify`,
   `/link/start`, `/link/poll`. Authenticated routes (`/anchor/*`,
   `/link/approve`) are out of scope for now — reaching them already
   requires a completed passkey ceremony.
4. Anchor deregistration (`DELETE /anchor/:id`) — not built; you can add a
   machine but not yet remove one.
