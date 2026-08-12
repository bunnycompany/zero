# Ship review — `@0-computer/zero` as a Node installer

Question: can we ship `npx @0-computer/zero` to a non-technical friend today?

## 1. Verdict

**NO-GO today. GO-WITH-CAVEATS is one focused day of work away.**

The installer skeleton is real and well-shaped — `npm/bin/preflight.js` already checks
the machine honestly, `npm/bin/zero.js` is a clean dispatcher, and `install.js` correctly
refuses to download 6.7GB behind the user's back. But the one command that matters,
`zero setup`, dead-ends: it prints `(v0.1.0 stub) setup.sh is not bundled yet` and exits 1
(`npm/bin/zero.js:46-48`). There is no `setup.sh` anywhere in the repo, and the
`github.com/0-computer/zero` it would clone returns **404**. So neither onboarding path
completes on a stock Mac. A trust product cannot ship a front door that opens onto a wall.

The good news: the wall is thin. Everything the friend needs already exists in the repo
(`launch_zero.sh`, `scripts/zero`, `requirements.txt`, the launchd template). What's missing
is the ~120 lines of `setup.sh` that glue them together, plus deciding how the Python source
reaches the machine. Do that and the honest small thing ships.

## 2. Ship-blockers, ranked

Ranked by "will this fail the friend at a crucial moment."

### B1 — `zero setup` is a stub; there is no installer. (~1 day)
`npm/bin/zero.js:46-48` looks for `../setup.sh`, doesn't find it, and quits. **No `setup.sh`
exists.** This is THE blocker: preflight passes, the friend types the one command the UI told
them to, and nothing installs.
**Fix:** write `npm/setup.sh`. It must, in order: create `~/.venv` with `python3.12 -m venv`;
`pip install -r requirements.txt`; fetch the Zero source into `~/.0-computer/zero` (see B2);
pre-download the model with a visible progress line (see B3); render the launchd plist (B4);
`launchctl load` it. Exit non-zero on any step so `zero.js:54` propagates the failure.

### B2 — No Zero source is shipped, and the git remote 404s. (~2 hrs, a decision)
`npm/package.json:6` ships only `bin/`, `install.js`, `README.md` — not `main.py`, `brain/`,
`danger_core/`, `zero/`, `observer/`. And `repository.url` → `github.com/0-computer/zero`
is **404**. So `setup.sh` has nothing to clone and nothing to run.
**Fix, pick one:** (a) push the repo to the public `0-computer/zero` and have `setup.sh` clone
a pinned tag — cleanest, keeps the npm package tiny; or (b) bundle a source tarball inside the
npm package and unpack it. (a) is the right call for v0.1. Until this is decided, B1 cannot land.

### B3 — First-run model download is silent, sold as "~45s". (~1 hr)
`brain/orchestrator.py:18` pulls the model at first `load()`; `scripts/zero:90` promises
"~45s" and `nohup … >launch.log` (line 89) buries the download; the status poll gives up at
90s (`scripts/zero:132-146`). The real download is **3.58GB** (verified on HF —
`mlx-community/gemma-4-e2b-it-4bit` is public, not gated, no token needed). A friend watching
a frozen terminal for several minutes assumes it's broken.
**Fix:** do the download in `setup.sh` (B1) as an explicit, watchable step —
`huggingface-cli download …` or a tiny Python `snapshot_download` with a "downloading the
brain, ~3.6GB, one time" line — so first `zero start` loads from warm cache in seconds.

### B4 — launchd daemon is never rendered or loaded. (~1 hr, folds into B1)
`packaging/launchd/computer.zero.agent.plist.template` has three unrendered `__ZERO_ROOT__`
placeholders (lines 9, 13, 24-25) and nothing loads it. Without this, Zero doesn't survive a
logout/reboot — it isn't "living on your Mac," it's a script you have to re-run.
**Fix:** in `setup.sh`, `sed` the placeholders to `~/.0-computer/zero` (the install home
`zero.js:19` already fixes) → `~/Library/LaunchAgents/` → `launchctl load`. Note: the
`ZERO_ROOT` decision is already correct; only the render + load step is missing.

## 3. What v0.1.0 on npm should be

**Package:** `@0-computer/zero` (npm scopes can't contain dots; `0.computer` → `@0-computer`).
A Node **installer/launcher only** — Zero itself is Python + MLX + Swift and is not, and will
never be, npm-installable. The package's whole job is to get the real thing onto the machine
and then get out of the way (`zero.js:8-11` already states this).

**`npx @0-computer/zero` → then `zero setup`, step by step:**
1. `postinstall` runs `install.js`: prints the preflight report, never fails the npm install
   (`|| true`, and `install.js` is side-effect-free by design). Tells the friend the one next
   step: `zero setup`.
2. `zero setup` re-runs preflight; refuses with a plain-English fix list if anything is ✗.
3. On all-green, hands to `setup.sh`, which: creates the venv → pip-installs deps →
   fetches Zero source into `~/.0-computer/zero` → downloads the model with a visible
   progress line → renders + `launchctl load`s the daemon.
4. `zero <words>` forwards to the installed bash CLI; `zero` alone reads the last answer;
   `zero doctor` re-runs preflight any time.

**Preflight checks** (`npm/bin/preflight.js`, already built): macOS, Apple Silicon,
Python 3.12+, Xcode CLT, ≥10GB free — each with a spoken-language fix and no stack traces.

**What v0.1.0 honestly does NOT support — say it in the README, out loud:**
- **Intel Macs and non-Macs.** `package.json:9-10` (`os:["darwin"], cpu:["arm64"]`) makes npm
  refuse with `EBADPLATFORM` before postinstall — so the friendly Intel message at
  `preflight.js:36-41` never actually runs on the machines it targets. The README must state
  "Apple-Silicon Mac only" plainly, because npm's own error is not friendly.
- **No GUI onboarding.** v0.1 is 100% terminal. The menubar app (`gui/`) is a real, compiled
  SwiftPM target but is not shipped by this installer. Don't promise a window.
- **Model download time.** Say "~3.6GB, one time, several minutes" — not "~45s."
- **Remote brain is off by default.** Local-only unless the friend sets `ZERO_API_KEY`.

## 4. Fix-before-friends (cheap, land regardless of B1–B4)

These are confirmed defects a friend hits on the manual/README path or at a crucial moment:

- **`README.md:13`** teaches `python3.12 -m venv` — absent on a stock Mac (only 3.9.6). The
  README self-contradicts the installer; fix it to point at `npx @0-computer/zero`.
- **`README.md:14`** `ln -s … /usr/local/bin/zero` needs sudo (dir is root:wheel) → "permission
  denied," and the promised `zero` command never appears. Drop it; npm provides the `bin`.
- **`scripts/zero:51`** the `_greet` trust-handoff prints `echo live > "$NS/control/mode"`
  inside a quoted heredoc — `$NS` never expands, so pasting it fails. Use the working relative
  form (`echo live > namespace/control/mode`, as `README.md:46` already has).
- **`scripts/zero:17` vs `launch_zero.sh:9-16`** venv-discovery mismatch: the CLI checks only
  `~/.venv` then silently falls back to system `python3` (3.9.6); the launcher checks project
  `./.venv` first. A README-following friend gets a daemon on 3.12 and a CLI on 3.9. Unify on
  one venv path (`~/.venv`, per CLAUDE.md).
- **`scripts/zero:87-91`** `zero start` prints "starting Zero…" unconditionally, even when
  `launch_zero.sh` exits instantly (no venv). Add a post-launch `_alive` poll before claiming
  success.
- **`preflight.js:61-63`** the free-space guard `freeG === 0 || freeG >= 10` treats a genuinely
  full disk (0GB) as PASS. Split the "couldn't parse" case from the "actually 0GB free" case.
- **`preflight.js:64-65`** labels the model "~7GB"/"~6.7GB"; real size is 3.58GB. Correct it.
- **License:** `package.json:11` is `SEE LICENSE IN README.md` but `npm/README.md` doesn't
  exist (also breaks `files:["…","README.md"]`). Add the README or use a real SPDX id.

## 5. Disclose-and-ship (honest gaps the README states, don't block v0.1)

Safe for a short single-user trial on one friend's Mac; must be named in the README:

- **Xcode CLT is gated as a hard check** (`preflight.js:53-58`) though the headless CLI needs
  no Swift. Downgrade to a warning for v0.1, or disclose that it's for the (unshipped) menubar
  app. Don't block a novice on a tool the running system doesn't use.
- **`status` during download is opaque** (`scripts/zero:65-68` prints "awake — waking" while
  the model pulls). B3's visible progress line largely covers this; disclose the gap.
- **Unbounded local growth:** the journal (`zero/ns.py:156-166`), memory facts
  (`memory.py:66-71`), and `.zero-backups/` (`tools.py:117-124`) never prune. Fine for a trial,
  real on a machine left running for weeks — say "trims nothing yet."
- **Everything is plaintext under `$HOME`** and rides Time Machine/iCloud; `main.py:70` logs
  full tool results (incl. file contents) uncapped. Disclose: "Zero keeps a readable local
  history; treat it like your Notes."
- **No singleton lock** (`launch_zero.sh` has none; `scripts/zero:57` guards only via `pgrep`).
  Two instances = two 6.7GB model loads = OOM on an 8GB Mac. The launchd daemon (B4) plus the
  pgrep guard covers the normal path; disclose "don't run it twice by hand."
- **Crash-to-silence on the process boundary** (verified: any non-`TypeError` mid-turn
  exception drops the whole claimed command batch — `main.py:54-62`; unguarded model load —
  `orchestrator.py:18`; unguarded `json.loads` on gateway body — `remote.py:55,73`). These are
  real but bite rarely on a single-user local trial. Add the three guards when convenient;
  `docs/failure-ledger.md:72-73` already discloses the crash case (understated as singular).
- **"Everything stays on this machine"** (`scripts/zero:53`) is false in remote mode
  (`ZERO_API_KEY` → `remote.py:118` POSTs the full prompt + up to 6000 chars of memory to
  `api.danger.plus`). Make the greet line conditional on the active brain (`health()` already
  knows). Local-only is the default, so this is disclose-and-fix, not a blocker.

---

**Bottom line:** the smallest honest shippable thing is `@0-computer/zero` v0.1.0 = the
existing preflight + dispatcher + a real `setup.sh` (B1) fed by a public pinned repo (B2), with
a visible model-download step (B3) and a rendered launchd daemon (B4), the six fix-before-friends
cleanups landed, and the README stating plainly what it doesn't support. That is roughly one
focused day. Ship that, not less — and not nothing.
