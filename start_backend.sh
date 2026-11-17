#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${ROOT_DIR}/runtime_env.sh"
echo "Starting backend at http://127.0.0.1:${BACKEND_PORT} (SAM_BACKEND=${SAM_BACKEND})"
cd "${ROOT_DIR}/backend"
exec "${PYTHON_BIN}" run_backend.py
