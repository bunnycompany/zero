#!/bin/bash
# Serve local MLX models to the Zero Chat app (OpenAI-compatible /v1 API).
#
#   ./scripts/serve_models.sh                     # default model
#   ./scripts/serve_models.sh mlx-community/gemma-4-31b-it-4bit
#
# The app's Settings screen wants the URL printed below.
set -euo pipefail

MODEL="${1:-mlx-community/gemma-4-e2b-it-4bit}"
PORT="${PORT:-8080}"

if [ -x "$HOME/.venv/bin/python3" ]; then
    PY="$HOME/.venv/bin/python3"
else
    echo "Expected the MLX venv at ~/.venv (see requirements.txt)" >&2
    exit 1
fi

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<mac-ip>")
echo "════════════════════════════════════════════════════"
echo "  Zero model server starting"
echo "  Model:    $MODEL"
echo "  In the app enter:  http://$IP:$PORT/v1"
echo "════════════════════════════════════════════════════"

exec "$PY" -m mlx_lm.server --model "$MODEL" --host 0.0.0.0 --port "$PORT"
