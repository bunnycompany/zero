# Zero — agent working guide

Zero is a local-first macOS agent: observer (NSWorkspace → `namespace/context/current`)
→ brain (MLX, JSON tool calls) → danger_core (tiered executor) → SwiftUI menubar UI.
State and IPC are plain files under `namespace/` — see `namespace/README.md` for the
channel contract. This file is for any agent (Claude, under, …) editing this repo.

## Hard rules

- **Gemma 4 only.** The model is `mlx-community/gemma-4-e2b-it-4bit`
  (`DEFAULT_MODEL` in `brain/orchestrator.py`). Never introduce gemma-2/gemma-3.
- **One writer per namespace channel**, enforced by `zero/ns.py` (`OWNERS`).
  All namespace I/O goes through `zero/ns.py` — never `open()` a namespace path.
- **`namespace/control/mode` is human-only.** Code may read it, never write it.
- **No sed, no shell string interpolation in tools.** File edits are literal
  Python string replacement with an occurrence guard (`danger_core/tools.py`).
- **Relative tool paths resolve against `ZERO_ROOT`, never cwd**
  (`danger_core/policy.py::resolve_confined`).
- **Never auto-retry a mutation.** Retries are READ-tier only (`executor.py`).
- Swift UI: view state lives in `ObservableObject`/`@Published`, not `@State` —
  the CommandLineTools toolchain lacks the SwiftUI macros plugin.

## Verify every change

```bash
~/.venv/bin/python3 -m unittest discover -s tests -q   # 47 tests, ~3s — must stay green
```

Model-layer eval (loads 6.7GB model, ~2 min; run when touching brain/prompt/parse):

```bash
ZERO_RUN_MODEL_EVAL=1 ~/.venv/bin/python3 -m zero.agenteval.run
```

Swift UI (only when `gui/Sources/` changed):

```bash
cd gui && swift build
```

## Environment

- Python venv: `~/.venv` (3.12, mlx_lm, pyobjc). There is no `./.venv`.
- `ZERO_ROOT` env var points tests/sandboxes at a temp root; unset, paths
  resolve via the `.zero-root` marker at repo root.
- Run the agent: `./launch_zero.sh` (starts observer + loop; boots in shadow
  mode — mutations journal to `namespace/log/journal.ndjson` but don't execute
  until a human writes `live` to `namespace/control/mode`).
- `packaging/` is legacy py2app output kept untracked — don't build on it.
  `eval_results/legacy/` is archived pre-agent data — never compare against it.

## Layout

| path | what |
|---|---|
| `main.py` | loop; `handle_commands()` is the injectable agent step |
| `brain/` | model load, `decide()` (JSON tool calls), `parse.py` |
| `danger_core/` | `policy.py` (tiers/modes/confinement), `tools.py`, `executor.py` (registry) |
| `observer/` | NSWorkspace context monitor (separate process) |
| `zero/ns.py`, `zero/nspath.py` | the only namespace I/O module + path resolution |
| `zero/agenteval/` | model-layer scenario evals |
| `tests/` | wiring-layer tests (sandboxed, no MLX) |
| `gui/` | SwiftUI menubar app (SwiftPM) |
