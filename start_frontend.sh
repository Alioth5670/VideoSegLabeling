#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # Make Node 18+ available even when this script is started from a non-interactive shell.
  # shellcheck disable=SC1091
  source "${HOME}/.nvm/nvm.sh"
  nvm use --silent node >/dev/null 2>&1 || true
fi

export BACKEND_PORT="${BACKEND_PORT:-8010}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js 18+ and npm before starting the frontend." >&2
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [[ "${NODE_MAJOR}" -lt 18 ]]; then
  echo "Node.js 18+ is required for the frontend. Current: $(node -v)" >&2
  echo "If nvm is installed, run: source ~/.nvm/nvm.sh && nvm install 18 && nvm use 18" >&2
  exit 1
fi

echo "Starting frontend"
echo "  URL: http://localhost:${FRONTEND_PORT}"
echo "  VITE_BACKEND_URL=${VITE_BACKEND_URL}"
echo "  node=$(node -v)"

cd "${ROOT_DIR}/frontend"
exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}"
