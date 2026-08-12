#!/bin/bash
# Zero - Native Agent Launcher
set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
export ZERO_ROOT="$APP_ROOT"

# Prefer a project venv; fall back to the shared ~/.venv (Python 3.12 + mlx).
if [ -x "$APP_ROOT/.venv/bin/python3" ]; then
    PY="$APP_ROOT/.venv/bin/python3"
elif [ -x "$HOME/.venv/bin/python3" ]; then
    PY="$HOME/.venv/bin/python3"
else
    echo "No venv found. Create one: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

cd "$APP_ROOT"

# Observer runs as its own process; the namespace is the IPC.
"$PY" -m observer.context_monitor &
OBSERVER_PID=$!
trap 'kill "$OBSERVER_PID" 2>/dev/null || true' EXIT INT TERM

"$PY" "$APP_ROOT/main.py"
