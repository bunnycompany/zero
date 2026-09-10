# The shape of the product: identity, compute, and what money buys

A design note. Follows `reaching-zero.md`, and corrects one thing in it.

We own `0.computer`. That is not branding — it removes the one real technical
wrinkle in the last note, and it forces a business-model question we should
answer on purpose rather than by drift.

## The correction

`reaching-zero.md` called the WebAuthn origin an "honest wrinkle": a passkey binds
to a domain, and a thing on `localhost` has none. Owning `0.computer` dissolves it.
Passkeys register against a real origin we control, and every person's agent gets
an address — `you.0.computer`. The name you'd say out loud *is* the security
origin. That is a rare case where the nice-sounding thing and the correct thing
are the same thing.

## Three layers that must never merge

The discipline from the last note — don't conflate reachability with identity —
generalizes into the whole product. There are three layers, and the entire design
depends on keeping them separate:

| layer | what it is | where it lives | who pays |
|---|---|---|---|
| **Identity** | your handle `you.0.computer`, your passkey origin, the rendezvous that lets a phone find your Mac | `0.computer` (DNS + a thin coordinator) | free |
| **Compute** | the brain that thinks — the model, the loop, your files | **your Mac by default**; danger.plus by choice | local is free; hosted is paid |
| **Transport** | how bytes get from phone to brain | mesh or relay | free |

The one that matters: **identity is not hosting.** Claiming `you.0.computer` does
not move your Zero off your machine. The domain is a nameplate and a doorbell, not
a house. Conflating them is how a local-first product quietly becomes a cloud
product — you register for an "account", and three versions later your data is on
someone's server because that was the path of least resistance. Naming the layers
now is what prevents that later.

## Registration comes late, and never gates the first run

Failure ledger #8 was a dead surface with nothing to say. The account-wall version
of that failure is worse: a non-technical person downloads Zero, and the first
thing it demands is a signup. For this audience that is where most of them leave.

So the rule is: **you can use Zero fully, locally, forever, having told us
nothing.** Download, it makes a local Zero, you talk to it. No handle, no passkey,
no `0.computer`, no email.

You claim `you.0.computer` only when you want the one thing local-anonymous cannot
give you: **to reach your Zero from your phone when you're out.** Registration is
the unlock for remote reach, not the toll for entry. That ordering is the whole
difference between "an app you own" and "an account you rent."

## What danger.plus is *for* — and the line it must not cross

danger.plus is optional hosted compute. The tension is obvious and worth stating
plainly: the pitch is *"stays on your machine,"* and hosted compute is, by
definition, not your machine. If we are careless, the revenue product erodes the
trust product.

**Decided (2026-07-30):** identity is **free** — you claim `you.0.computer` at no
cost, and we charge for compute, never for your own name. danger.plus bills as a
**flat monthly "always-on"** price, not per-token — a bad-with-computers person
should never fear a surprise bill from talking to their assistant, and legible
beats technically-fair for this audience. And hosting is **private by
construction** from the first day it exists (see "The privacy promise" below).

The resolution is to sell danger.plus **only against limits local genuinely has**,
never against a crippled free tier:

- **No Mac, or a Mac that sleeps.** Local Zero is asleep when your Mac is. Hosted
  Zero is awake at 3am when the reminder should fire. This is the honest core of
  the offer: *always-on.*
- **Models that cannot fit on the machine.** e2b runs on 8GB; qwen-480b, kimi,
  glm-5 do not. If you want the big brain, it has to run somewhere with the RAM.
- **A phone-only person.** Someone with no Mac at all can still have a Zero — it
  just lives on danger.plus from day one.

And the line, stated as a rule the product must keep:

> **The free local tier is never deliberately crippled to sell the paid one.**

The standard SaaS move is to nerf the free tier until upgrading is relief. That is
forbidden here, because it is the trust thesis applied to pricing: you upgrade
because your Mac sleeps or you want a 480B model, **not** because we made local
worse on purpose. Local is complete. Hosted is for limits local cannot lift.

## The privacy promise: private by construction, or it doesn't ship

**Decided: we promise private hosting now — and the discipline that keeps that
honest is that we never ship the readable kind at all.**

The tempting compromise was to launch readable hosting fast, warn people plainly
("we can see what you tell it"), and earn the private version later. The owner's
call is braver and, taken seriously, actually *more* aligned with the trust thesis:
private is not a later upgrade to hosting — **private is the definition of
hosting.** danger.plus does not offer a tier we can read. Until hosted compute
meets that bar, hosting simply does not exist as a product.

This is only a promise and not a lie because the bar is real and already proven:

- **Confidential computing.** The model runs inside an attested secure enclave
  (H100 confidential compute, Nitro-style isolation). The provider — us — cannot
  read the memory of the running session, and the client can *verify* that
  cryptographically before sending anything.
- **The precedent is shipping.** Apple's Private Cloud Compute is exactly this:
  hosted inference the provider cannot inspect, with client-verifiable attestation.
  "Promise private now" is not vaporware; it is pointing at a pattern that exists
  and building danger.plus to that line.

The honesty requirement therefore moves from a *warning* to an *attestation*: the
interface does not say "we can see this, sorry" — it says, and lets your device
check, "this runs where even we can't read it." That is the same discipline as
shadow mode announcing itself, raised to its strongest form. And it is the version
a competitor who merely rents GPUs cannot copy, because it is a promise enforced by
hardware and math rather than by policy.

**The cost we accept, stated plainly:** hosting ships *later* this way. Attested
enclave inference is materially harder than renting a GPU and running a server, so
choosing "private by construction" means danger.plus arrives when it can be
private, not the week we could first bill for it. That is the honest price of the
promise, and it is the right one for a product whose entire thesis is that it does
not say what it has not built.

## What money actually buys, on one card

At the point of choice, the honest framing:

**Zero, on your Mac — free, forever.**
Lives on your computer. Private by default — nothing leaves the machine. Asleep
when your Mac is. Runs a model sized for your hardware.

**Zero, hosted on danger.plus — flat monthly.**
Awake all the time, even when your Mac is off. Runs the big models. Works with no
Mac at all. Runs in a sealed enclave your own device can verify — hosted, but
still nobody's business but yours.

Same Zero, same voice, same trust ladder. The only differences are where it runs
and the flat price of running it there. Privacy is not one of the differences —
that is the point, and the reason hosting waits until it can be true.

## Why this is defensible, not just nice

Everyone is building the personal agent, and most will monetize by hosting,
because hosting is where the recurring revenue is. The thing they will find hard to
copy is not the hosting — anyone can rent GPUs. It is a company whose free,
local, private tier is *genuinely complete*, whose paid tier is sold honestly
against real limits, and whose interface tells you the uncomfortable truth in the
sentence where you choose. That posture is a moat precisely because it is the one
thing a growth-at-all-costs competitor cannot bring themselves to do. Zero's
business model is the same asset as its architecture: it is trustworthy on purpose,
and it says so out loud.

## The three decisions, settled

Resolved by the owner on 2026-07-30:

1. **`you.0.computer` is free.** Identity is cheap to run and charging for your own
   name erodes the trust the product sells. Charge for compute, never for identity.
2. **danger.plus bills flat monthly**, not per-token. Legible beats technically-fair
   for a friends-and-family audience; nobody should fear a surprise bill from
   talking to their assistant.
3. **Private hosting is promised now — and enforced by never shipping the readable
   kind.** Private is the definition of danger.plus, not a later upgrade, built to
   the attested-enclave bar that Apple's Private Cloud Compute already proves is
   real. The accepted cost is that hosting arrives later, when it can be private.

**The standing risk to watch**, since decision 3 is the one that stakes the trust
thesis on something unbuilt: the promise stays honest only as long as hosting does
not ship before the enclave does. The failure mode is a quarter where revenue is
tight and "just launch readable hosting for now" looks reasonable. That is the one
line whose crossing would cost more than the money it made. Write it down, and when
the pressure comes, re-read `failure-ledger.md` #5 — the previous Zero performed a
personality it did not have, and this would be the same lie wearing a pricing page.

The only thing already built is the lock the last note argued for — remote commands
capped at `approve` — because that invariant has to exist before any of this ships,
whatever the model above.

## Addendum, 2026-09-10 — hosting is not 0.computer's job

Founder decision, recorded as stated: **people will not host content on
0.computer domains.** The earlier idea of letting anyone put pages or
artifacts on a `*.0.computer` subdomain is withdrawn; hosting of that kind is
what `spell.host` does (see `docs/ontology.md`, "The publishing side").

What this note assumes, until the founder says otherwise: the identity layer
above is unchanged. `you.0.computer` remains a nameplate and a doorbell (a
passkey origin and a rendezvous for your own devices), never a house. That
was already the rule ("identity is not hosting"); this addendum only removes
the one thing that would have blurred it.
