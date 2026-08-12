# Fleet brain: N Mac minis as one reliable endpoint

How a customer's beowulf cluster of Mac minis becomes a single brain URL that
Zero points `ZERO_GATEWAY_URL` at — and stays up when a mini doesn't.

Grounding: `brain/remote.py` (RemoteBrain: one non-streaming POST to an
OpenAI-compatible `/chat/completions`, `health()` via `GET /models`, dead
gateway = failed turn, never a crash), `zero/ns.py` (durable file inbox,
claim-by-rename FIFO), `main.py` (strictly sequential: one command, one
`decide()`, one tool, one answer).

---

## 1. The honest distinction: sharding vs replication

**Sharding** (exo, MLX distributed, llama.cpp RPC): one model split across
minis. You get a *bigger* brain — a model no single mini can hold — and a
*less reliable* one. Every sharded stack on macOS today fails whole-cluster
on single-node failure: MLX `mlx.launch` kills all ranks when one dies; exo
truncates in-flight generations and may not re-form cleanly (issues #1726,
#1723 — silent slow-path fallback after crash). One node down = brain down.
Throughput also disappoints: a 4-node pipeline is ~1.5× one node, not 4×,
because most nodes idle per request.

**Replication**: every mini holds the full model and serves it independently;
a router in front makes N endpoints look like one. One node down = capacity
down 1/N, availability unchanged. Concurrent throughput scales nearly
linearly (it's queue-level parallelism). The cap: the model must fit in one
mini's RAM.

The models Zero's customers actually run (gemma-4-e2b class, and anything up
to ~30B Q4 on a 32–64GB mini) fit on one node. Sharding a model that fits is
strictly worse — measured 2.7× *slower* per token (mlx-optiq, 2-Mac ring) —
and adds shared fate.

**"Reliability for customers" is served by replication. Full stop.** Sharding
is a capability tier, not a reliability tool (§3).

## 2. Recommended v1

```
Zero(s) ──HTTP──▶ LiteLLM proxy (one mini, launchd KeepAlive)
                    │ least-busy, health checks, cooldown, retry
                    ├──▶ mini-a  mlx_lm.server :8080  (full model)
                    ├──▶ mini-b  mlx_lm.server :8080  (full model)
                    └──▶ mini-c  ...
```

### On each mini

One `mlx_lm.server` per mini, serving the full model, kept alive by launchd:

```bash
~/.venv/bin/python3 -m mlx_lm server \
  --model mlx-community/gemma-4-e2b-it-4bit \
  --host 0.0.0.0 --port 8080
```

(If a customer fleet standardizes on llama-server GGUF instead, the same
design holds and you gain `/slots?fail_on_no_slot=1` as a precise "I'm full"
signal — but don't switch stacks for that; MLX is Zero's world and the
weights are already cached.)

### The balancer: LiteLLM proxy

One process, one YAML, no Redis, no k8s. It is the only off-the-shelf router
with all four of: same-model-N-deployments, background health checks that
bench dead nodes *before* a request hits them, failure-count cooldowns, and
retry-on-another-deployment. `config.yaml`:

```yaml
model_list:
  - model_name: zero-brain
    litellm_params:
      model: openai/mlx-community/gemma-4-e2b-it-4bit
      api_base: http://mini-a.local:8080/v1
      api_key: "none"
    model_info: { id: mini-a }
  - model_name: zero-brain
    litellm_params:
      model: openai/mlx-community/gemma-4-e2b-it-4bit
      api_base: http://mini-b.local:8080/v1
      api_key: "none"
    model_info: { id: mini-b }

router_settings:
  routing_strategy: least-busy      # fewest in-flight; right for homogeneous minis
  num_retries: 2                    # retry a failed call on another deployment
  allowed_fails: 2                  # 2 strikes ->
  cooldown_time: 30                 #   benched 30s
  enable_pre_call_checks: true

general_settings:
  master_key: sk-zero-fleet         # becomes ZERO_API_KEY
  background_health_checks: true
  health_check_interval: 30
```

Run: `litellm --config config.yaml --port 4000` under launchd with
`KeepAlive: true`. The router is stateless; restart-on-crash is the whole HA
story it needs at 3–5 nodes.

This maps exactly onto underclass's health taxonomy without building it:
LISTED = in rotation, RATE-LIMITED = 429/`allowed_fails` cooldown (benched,
never blacklisted), DEAD = failed background health check (out until it
passes again).

### Health, failover, retry semantics

- **Node dead before dispatch**: background health check already benched it;
  requests never route there. Zero sees nothing.
- **Node dies during a request, pre-first-token**: LiteLLM retries on another
  deployment (`num_retries`). Zero sees added latency, nothing else.
- **Mid-stream death**: *does not apply to Zero.* `RemoteBrain._generate`
  sends `"stream": False` — there is no partial token stream to rescue; a
  died-mid-generation request is just a failed HTTP call, retried whole.
  Leave LiteLLM's mid-stream fallback machinery (its buggiest edge —
  prefill-continuation hacks, #27967/#26015) alone/disabled. If a future
  consumer streams, the rule is: agent consumers retry the whole request;
  only humans watching tokens care about partials.
- **Why whole-request retry is safe**: inference is a pure read — no server
  state mutates. The "never auto-retry a mutation" rule (`executor.py`)
  doesn't constrain this: the mutation is `executor.execute_tool`, which
  runs only after a complete response is received and parsed in `main.py`.
  Retrying `decide()` N times is always legitimate.

### How Zero consumes it: one env var, one small patch

Zero-side, the fleet is just another gateway:

```bash
ZERO_BRAIN=remote \
ZERO_GATEWAY_URL=http://gateway.local:4000/v1 \
ZERO_MODEL=zero-brain \
ZERO_API_KEY=sk-zero-fleet \
./launch_zero.sh
```

`RemoteBrain.health()` already does `GET /models` — against LiteLLM that
answers iff the proxy is up, which is the right question.

One patch is warranted, because of a real seam in `ns.py`: the inbox is
**not** a redelivery queue. `_claim_commands` renames a command into `done/`
*before* the brain call — claim equals consume. So if the gateway is down for
a whole turn, the command is not re-delivered; `main.py` journals
`decision_unparseable` and the answer channel reports the failure. That's
correct behavior for a dead brain, but it means transient-blip resilience
must live *in-process*, in `RemoteBrain._generate` — which currently returns
`""` on the first error. Add a bounded read-only retry:

```python
# brain/remote.py, in _generate — replace the single try with:
for attempt in range(3):                      # reads only; never mutations
    try:
        data = self._post(payload)
        break
    except urllib.error.HTTPError as e:
        if e.code != 429:                     # 429 = fleet busy, worth waiting
            self.logger.warning(f"gateway HTTP {e.code} (attempt {attempt+1})")
        time.sleep(2 ** attempt)              # 1s, 2s; then give up
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        self.logger.warning(f"gateway unreachable: {e} (attempt {attempt+1})")
        time.sleep(2 ** attempt)
else:
    return ""                                 # failed turn, as today
```

That is the *entire* Zero-side change. Everything else — balancing, health,
failover — lives behind the URL.

### Queue behavior under overload / backpressure

- A single Zero cannot overload anything: `main.py` is sequential — one
  in-flight brain call, ever. Commands arriving meanwhile queue durably in
  the inbox (FIFO, crash-safe) and are "never dropped." The inbox *is* the
  backpressure buffer; under fleet overload, turns get slower, not lost.
- Fleet-wide admission control: set `max_parallel_requests` per deployment in
  `litellm_params` (start at 2/node for mlx_lm.server, which has no slot
  introspection). Excess requests get 429 → the RemoteBrain backoff above
  absorbs it → the customer's other Zeros' commands wait in their own
  inboxes. No custom queue service needed anywhere.
- `timeout=120` in RemoteBrain already bounds a wedged request; LiteLLM's
  per-deployment `timeout` should be set slightly lower (100s) so the router,
  not the client, is what times out and retries.

## 3. When sharding IS worth it — and running both

Reach for exo only when a customer wants a model that genuinely exceeds one
mini's RAM (dense 70B+, big MoE). Requirements to say yes: M4 Pro minis or
better (TB5 — base M4 minis are TB4 and get the sad pre-RDMA numbers),
macOS 26.2+, matching OS versions, and acceptance that the big tier fails
whole-cluster and restarts cold (22–100s model reload).

Run it **beside** replication, not instead of it — as one more LiteLLM entry
under a different model name:

```yaml
  - model_name: zero-brain-big
    litellm_params:
      model: openai/<big-model-id>
      api_base: http://mini-a.local:52415/v1   # exo's API node
      api_key: "none"
    model_info: { id: exo-cluster }

router_settings:
  fallbacks: [{ "zero-brain-big": ["zero-brain"] }]   # big tier degrades to small, honestly
```

Pin exo at **v1.0.71** (last release, 2026-04-23; the June libp2p→zenoh swap
has ~7 weeks of soak and no release). exo has been abandoned once already
(Mar–Dec 2025) — wrap it behind your gateway contract so ripping it out later
touches one YAML stanza and zero Zero code. Selecting the tier per-request is
underclass's `tierModel()` problem, already solved there; Zero v1 just sets
`ZERO_MODEL` to one or the other.

## 4. Staged rollout — 2 minis, this week

**Stage 0 — one mini, direct (30 min).** Start `mlx_lm.server` on mini-a.
Verify: `curl http://mini-a.local:8080/v1/models`, then point a Zero at it
(`ZERO_GATEWAY_URL=http://mini-a.local:8080/v1`, `ZERO_MODEL=<model id>`),
submit a command, confirm the answer channel. Baseline established.

**Stage 1 — insert the router (1 hr).** `uv tool install "litellm[proxy]"`;
config with only mini-a; `litellm --config config.yaml --port 4000`. Repoint
Zero at `:4000/v1` with `ZERO_MODEL=zero-brain`. Verify identical behavior,
plus `curl -H "Authorization: Bearer sk-zero-fleet" http://gateway.local:4000/v1/models`.

**Stage 2 — second mini + failure drills (half day).** Add mini-b to the
YAML, restart the proxy. Then, in order:
1. *Balance*: fire 6 concurrent `curl`s at `/v1/chat/completions`; confirm
   both minis' logs show traffic.
2. *Dead node, new requests*: `kill -9` mini-b's server; within one
   `health_check_interval` requests all land on mini-a with no client errors.
3. *Dead node, in-flight*: `kill -9` mini-b mid-request; confirm the request
   still returns (router retry on mini-a) — this is the test that proves the
   whole design.
4. *Zero end-to-end*: with mini-b down, submit a Zero command; confirm a
   normal answer, and `journal.ndjson` shows no `decision_unparseable`.
5. *Recovery*: restart mini-b; confirm it re-enters rotation unattended.

**Stage 3 — make it boring (half day).** launchd plists with
`KeepAlive: true` for both servers and the proxy. Reboot mini-b entirely:
everything must return to rotation with zero human action. Pull mini-b's
Ethernet mid-request: same expectations as drill 3. Land the RemoteBrain
retry patch; run `~/.venv/bin/python3 -m unittest discover -s tests -q`.

**Stage 4 — optional big tier.** Only if a customer needs a model that
doesn't fit: exo v1.0.71 on TB5-capable minis, added as `zero-brain-big`
with fallback to `zero-brain`. Re-run drill 3 against it and document the
honest result (in-flight request dies; fallback tier answers).

## 5. What NOT to build

- **No custom scheduler/balancer.** Least-busy + health checks + cooldown +
  retry is LiteLLM config, not code. The interesting failure modes (health
  checks racing cooldowns, retry storms) are already debugged there.
- **No k8s, no Docker, no service mesh.** launchd `KeepAlive` is the
  process supervisor these machines already ship with.
- **No MLX distributed / JACCL for the standard tier.** Sharding a model
  that fits on one mini is a measured regression with added shared fate;
  JACCL needs TB5 meshes base minis don't have, and its RDMA driver is
  v0.0.1 with kernel-panic field reports.
- **No mid-stream failover machinery.** Zero doesn't stream; whole-request
  retry is strictly correct for an agent consumer.
- **No second queue.** The file inbox is the durable queue and the
  backpressure buffer. Don't add Redis/Celery/SQS-alikes in front of a brain
  call that a 3-line backoff loop handles.
- **No router HA pair.** Stateless proxy + KeepAlive restart is adequate at
  this scale; keepalived/VIP is Stage-N-if-ever.
- **No exo as the router.** exo is a capacity tool that happens to have an
  API; it is one *deployment* behind the router, never the front door.
- **No live ability probing in Zero.** Per-node health belongs to the
  router; per-model ability verdicts belong to underclass's `learn.ts`
  pattern, offline, if ever.
