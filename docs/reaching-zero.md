# Reaching Zero from the outside

A design note, written before any of it is built.

Zero lives on your Mac at home. You are at a cafe with your phone, and you want
to reach the thing that knows you. This is the wall every personal-agent project
walks into, and it is worth slowing down for, because the obvious answers are all
slightly wrong and the careful answer falls out of a distinction most designs
skip.

**The need, in one sentence:** you, away from home, should be able to reach your
own agent securely and without ceremony — and no one else should, ever.

## Two problems wearing one coat

"Let me reach Zero from my phone" is really two questions that have nothing to do
with each other, and every fragile design is one that answered them together.

**Reachability** — how do bytes from your phone get to a Mac behind a home
router? This is plumbing. NAT, sleep, dynamic IPs.

**Identity** — how does Zero know the bytes are from *you* and not someone who
found the door? This is trust. And for a product whose entire thesis is trust, it
is the one to get right first.

Solve them separately. Conflating them is how you end up with a port forwarded to
the open internet "protected" by a password — reachable and unsafe in one move.

## Identity: passkeys, and why they are principled here, not trendy

The right answer is a **synced passkey** — the thing your phone already offers to
create and store in iCloud Keychain. Not because it is modern, but because of one
property that is *exactly* Zero's ethos:

> The secret never touches Zero, and never touches whoever built Zero.

A passkey is a keypair. The private half is minted in your phone's Secure Enclave,
syncs between your own Apple devices through iCloud Keychain, and **physically
cannot leave** — not to Zero, not to a server, not to a backup you could lose.
Zero stores only the *public* half. Signing in is a challenge-response: Zero sends
a random challenge, your phone signs it with a key it never reveals, Zero checks
the signature against the public key it has. At no point does Zero learn anything
it could leak, and at no point does anyone type a password into anything.

That last part matters twice over. It is better security — there is no shared
secret to phish, reuse, or breach. And it is the correct boundary for how this
gets built: **the credential ceremony happens entirely on your device.** Nobody —
not me, not a future Zero, not a support person — ever handles your key. An agent
that can be *reached* but can never hold the secret used to reach it is the same
shape as an agent that can *act* but can never promote itself to act unsupervised.
Same principle, one layer out.

**The honest wrinkle.** Passkeys (WebAuthn) bind a credential to an *origin* — a
domain name. A thing running on `localhost` on your Mac has no stable public
origin, and that friction is real: you need one fixed name that the phone's
passkey is registered against, and it has to resolve to your Mac. This is the
seam where reachability and identity touch, and it is the part that takes thought
rather than typing. The mesh option below happens to solve it cleanly, which is
part of why it wins.

## Reachability: three roads, one recommendation

| approach | how | good | bad |
|---|---|---|---|
| **Port-forward + dynamic DNS** | open a port on the home router | no dependencies | you just put your agent on the open internet; router config is beyond the audience; breaks when the ISP rotates your IP |
| **Relay through the gateway** | Mac holds an outbound connection to a relay; phone talks to the relay | zero config, no router touching, works behind any NAT | the relay sees traffic (mitigated by end-to-end encryption); it is a dependency that can go down — and we have watched `api.danger.plus` 500 and 530 this very week |
| **Mesh VPN (Tailscale / WireGuard)** | Mac and phone join a private encrypted network; they see each other as if on the same LAN | encrypted device-to-device, no open ports, gives you a **stable name** for your Mac (solving the WebAuthn origin wrinkle for free), survives cafe Wi-Fi client isolation | the user installs one more app and signs into it once |

**Recommendation: mesh for the people you hand this to, relay as the zero-config
fallback.** A mesh is the pragmatic convergence point the whole industry keeps
landing on because it makes the remote case behave like the local case — and
Zero's entire architecture is already built for the local case. The relay is
worth having as the option that needs no setup at all, for the friend who will
never install a second app, with the honest caveat that it adds a dependency of
exactly the kind that has failed on us repeatedly.

## The architectural fit: a remote command is just another writer to the inbox

Here is the part that makes this cheap rather than a rewrite. Zero already has one
front door: the command inbox. The scheduler proved the pattern last night — a
scheduled task is *another writer to the inbox*, tagged `source: scheduler`, and
it reused the queue, the tiers, shadow mode, the journal, and the answer channel
without a single new execution path.

A remote command is the same move again:

```
  phone ──(passkey auth)──► bridge ──► command/inbox   {source: "remote"}
                                             │
                                     the ordinary loop
                                             │
   phone ◄──(same secure channel)──── answer/current
```

The bridge is a thin authenticated listener. It verifies the passkey signature,
drops the text into `command/inbox` with `source: "remote"`, and streams
`answer/current` back. Everything downstream is untouched. The seam already
exists: `ns.submit_command(text, source="remote")` was written to take a source
last night, and the loop already journals it.

## The new trust rung this demands

Remote reachability is the **highest-blast-radius setting in the whole product**,
and it has to be treated that way. Until now, only local processes and a
cable-tethered phone could put a command in the inbox. Opening a remote door means
the agent that can touch your files is reachable from outside your house. So:

- **Off by default, human-only to turn on** — the same rule as `control/mode`. A
  setting the agent cannot flip for itself, living where the agent cannot write.
- **Remote commands are capped, independent of the action ladder.** Even when
  Zero is in `live` mode for you at the keyboard, a command that arrived from
  `source: "remote"` should not silently trigger a DANGER-tier action. The cleanest
  rule: **remote defaults to `approve`** — it can read and report freely, but a
  mutation from outside the house waits for a confirmation, forever if need be.
  This is the one place the source of a command must reach the executor, and it is
  worth the wiring precisely because the blast radius is largest here.
- **The journal already tells organic from remote from scheduled**, so "what did
  my agent do while I was out, and who asked it to" is answerable by reading one
  file. For a thing you let reach you from the world, that log is not a nicety.

## Offline is a promise, not an error

Your Mac will be asleep sometimes. A command sent to a sleeping Zero should
**wait in the inbox and be handled when it wakes**, with the phone told plainly:
"Zero is asleep — this will be waiting when it wakes." We built exactly this
copy into the Android client already ("What you type will be waiting for it when
it wakes up"). The remote path should keep that promise rather than inventing a
failure.

## What I will not do, and why that is the design working

I will not handle your passkey, create the accounts a mesh or relay needs, or set
up the relying-party origin. That is not a limitation to apologize for — it is the
architecture being honest. The credential ceremony belongs on your device by
design; the accounts are yours to own; and a system where the builder never needs
to touch the user's secrets is the system you can actually trust with the keys to
your own machine.

## The order

1. **`source: "remote"` reaches the executor, and remote defaults to `approve`.**
   The lock before the door. Small, and it is a safety invariant that should exist
   before any remote channel does — the failure ledger's lesson about building the
   seam before the capability.
2. **The mesh path**, documented as the recommended setup, because it solves
   reachability and the WebAuthn origin in one move.
3. **The bridge** — the authenticated listener — as its own surface, finished
   before the next one is started, per the one-surface-at-a-time rule.
4. **The relay fallback**, last, for the setup-averse, with its dependency risk
   stated out loud.

Everyone is building this exact thing, and it is closer every time — but the part
most of them skip is step 1. The door is easy. The lock, and the discipline to
build it first, is the whole product.
