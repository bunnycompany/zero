# The danger.plus / 0.computer ontology

A reference map of the whole system. Written to the project's own rule: **cite
or abstain.** Where this session or the repos give real evidence, it is stated
as fact. Where they don't, the entry says *author to define* rather than invent a
plausible meaning — a confident fiction here would be failure-ledger #5 (performing
knowledge it doesn't have), and this map refuses to do that.

Confidence: **known** (direct evidence) · **inferred** (reasoned from a cite) ·
**?** (no evidence found — yours to fill in).

---

## The agent

**zero** — *known.* A local-first macOS ambient agent. Observer → gemma-4 brain →
tiered shadow-mode executor → plain-file namespace → menubar/CLI/Android surfaces.
The trust-engineering core of everything: shadow → approve → live. This whole repo.

**twin** — *inferred, confirm.* Appeared as `zero-twin` in the previous prototype's
`agents/` (now detached). Most likely a mirror/digital-twin of you or of a Zero
instance. *Author to confirm: twin of the user, or a second synced Zero?*

**pepper research** — *inferred, confirm.* Described by you as "an autonomous
researcher vtuber girl on device" (and your address is pepperchanresearch@). An
on-device autonomous-research persona with a presented character. *Author to
confirm: relationship to zero — a persona layer over it, or a separate agent?*

**ceo** — *?* No evidence in either repo or the session. *Author to define — an
orchestrator that directs the other agents?*

## The coding side

**under** — *known.* The CLI coding agent (`~/underclass`). Node, pi-coding-agent
SDK, local-first OpenAI endpoints, fan-out to parallel worktrees, ability-based
model routing. Zero's sibling; the plan is under maintains zero.

**danger (the terminal)** — *known.* A zsh shell integration shipping with
underclass: `danger init` (installs into `~/.zshrc`, prepends to PATH), `danger
shell`, plus model-backed features. The ambient terminal layer.

**why** — *known.* `danger why <status> <cmd>` — post-mortem: explains *why* a
command just failed (works in any shell, not only zsh). The "what went wrong"
button for the terminal.

## The fabric (compute + connection)

**danger.plus** — *known.* The inference gateway. 140+ models, an `auto` routing
mode that picks a model for you, an `--exo` (sharded) entry live in the list. The
paid hosted-compute layer — and, per `product-model.md`, private-by-construction.

**collective** — *known (named this session).* A customer's own Mac minis pooled
into one reliable brain — replication + load balancing behind one URL (see
`fleet-brain.md`). Extension: optional contribution of idle compute to a
danger.plus "hivemind." **Open tension:** contributed strangers' machines are not
attested enclaves, so hivemind work must be labeled and kept off anything promised
private.

**link** — *inferred, confirm.* Your words: "something like LM Studio link" — the
discovery/connection layer that lets machines find and join each other into a
collective. *Author to confirm: is link the discovery protocol, or the product name
for the whole pooling feature?*

**permanent** — *inferred, confirm.* Your words: "runtime autoscaler." Scales
compute up/down under load — the thing that keeps the fabric sized to demand.
*Author to confirm: autoscales the danger.plus fleet, the local collective, or both?*

**group** — *?* No evidence found. *Author to define — a shared/multi-user Zero, a
team tier, or a grouping of agents?*

## The rest

**time machine** — *inferred-weak, confirm.* No direct evidence this session. The
previous prototype kept `reincarnation-logs` and checkpoints, so a state/history/
rollback capability is a plausible read — but this is a guess. *Author to define.*

**nfinit** — *?* Described only as "our version of buzz.xyz." buzz.xyz was not
researched this session. *Author to define — what does buzz.xyz do, and which part
is nfinit?*

---

## What only you can answer

These are the gaps this map deliberately refuses to fill:

1. **twin** — a twin of the user, or a synced second Zero?
2. **pepper research** — persona layer over zero, or a separate agent?
3. **ceo** — what is it? (best guess: an orchestrator over the other agents)
4. **group** — what is it? (multi-user Zero? a team tier? an agent grouping?)
5. **time machine** — is it state/history/rollback, or something else?
6. **nfinit** — what does buzz.xyz do, and what is nfinit's version of it?
7. **link** vs **collective** — which name is the protocol and which is the product?
8. **permanent** — what does it autoscale, and against what signal?

Answer these and a swarm can turn this scaffold into the full referenced page —
the workflow to do it is staged at `scratchpad/ontology-wf.js`, deliberately not
run yet to stay honest (and conservative on tokens).
