#!/bin/bash
# Zero setup — the one heavy, opt-in step. Run by `zero setup` after preflight
# passes. Idempotent: safe to re-run; every step checks before it acts.
#
# What this does, in order, out loud:
#   1. Python venv at ~/.venv (3.12+)
#   2. Zero source into $ZERO_ROOT (git clone or updates an existing checkout)
#   3. Python deps into the venv
#   4. The model — ~3.6GB, once, with visible progress (never behind the back)
#   5. launchd daemon so Zero survives reboots
set -euo pipefail

ZERO_ROOT="${ZERO_ROOT:-$HOME/.0-computer/zero}"
REPO_URL="${ZERO_REPO:-https://github.com/bunnycompany/zero.git}"
REPO_REF="${ZERO_REF:-main}"
MODEL="mlx-community/gemma-4-e2b-it-4bit"
VENV="$HOME/.venv"

step() { printf "\n  \033[1m%s\033[0m\n" "$1"; }
sub()  { printf "    %s\n" "$1"; }
die()  { printf "\n  ✗ %s\n" "$1" >&2; exit 1; }

# ---- 1. python venv --------------------------------------------------------
step "Python"
PY=""
for cand in python3.13 python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    v=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    case "$v" in 3.1[2-9]|3.[2-9]*) PY="$cand"; break;; esac
  fi
done
[ -n "$PY" ] || die "Python 3.12+ not found. Install it from python.org, then re-run  zero setup"
if [ ! -x "$VENV/bin/python3" ]; then
  sub "creating a private Python at $VENV (one time)"
  "$PY" -m venv "$VENV"
else
  sub "found $VENV — keeping it"
fi

# ---- 2. zero source --------------------------------------------------------
step "Zero itself"
if [ -d "$ZERO_ROOT/.git" ]; then
  sub "updating the copy at $ZERO_ROOT"
  git -C "$ZERO_ROOT" fetch --quiet origin "$REPO_REF" || sub "(offline — keeping what's here)"
  git -C "$ZERO_ROOT" checkout --quiet "$REPO_REF" 2>/dev/null || true
elif [ -f "$ZERO_ROOT/main.py" ]; then
  sub "found an existing copy at $ZERO_ROOT — keeping it"
else
  sub "downloading Zero to $ZERO_ROOT"
  mkdir -p "$(dirname "$ZERO_ROOT")"
  git clone --quiet --depth 1 --branch "$REPO_REF" "$REPO_URL" "$ZERO_ROOT" \
    || die "couldn't download Zero. Are you online? ($REPO_URL)"
fi

# ---- 3. python deps --------------------------------------------------------
step "Libraries"
sub "installing what Zero needs (a few minutes, one time)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ZERO_ROOT/requirements.txt" \
  || die "library install failed — run  zero setup  again to retry"

# ---- 4. the model, out loud ------------------------------------------------
step "The brain"
if "$VENV/bin/python3" - <<PYEOF
import sys
from huggingface_hub import snapshot_download
try:
    snapshot_download("$MODEL", local_files_only=True)
    sys.exit(0)
except Exception:
    sys.exit(1)
PYEOF
then
  sub "model already downloaded — skipping"
else
  sub "downloading the model (~3.6GB, one time — progress below)"
  "$VENV/bin/python3" - <<PYEOF || die "model download failed — run  zero setup  again to resume"
from huggingface_hub import snapshot_download
snapshot_download("$MODEL")
PYEOF
fi

# ---- 5. launchd daemon -----------------------------------------------------
step "Keeping Zero alive"
PLIST_SRC="$ZERO_ROOT/packaging/launchd/computer.zero.agent.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/computer.zero.agent.plist"
if [ -f "$PLIST_SRC" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  sed "s|__ZERO_ROOT__|$ZERO_ROOT|g" "$PLIST_SRC" > "$PLIST_DST"
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST" 2>/dev/null \
    && sub "Zero now starts by itself, even after a restart" \
    || sub "(couldn't register the auto-start — Zero still works via  zero start)"
else
  sub "(no daemon template in this copy — Zero still works via  zero start)"
fi

printf "\n  \033[1mDone.\033[0m Say something to it:\n\n      zero what can you do\n\n"
printf "  It starts in shadow mode: it says what it would do and changes nothing\n"
printf "  until you decide otherwise. Everything stays on this Mac.\n\n"
