#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# SAM3 contains internal bare .cuda() calls. Expose one physical GPU by default
# so process-local cuda:0 consistently maps to the intended card.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export SAM_BACKEND="${SAM_BACKEND:-mock}"
export SAM_DEVICE="${SAM_DEVICE:-cuda:0}"
export BACKEND_PORT="${BACKEND_PORT:-8010}"
export PROJECTS_DIR="${PROJECTS_DIR:-${ROOT_DIR}/projects}"
export SAM_REPO_PATH="${SAM_REPO_PATH:-${ROOT_DIR}/sam3}"
export SAM_CHECKPOINT_PATH="${SAM_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.pt}"
export SAM31_CHECKPOINT_PATH="${SAM31_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.1_multiplex.pt}"
export CUDA_LAUNCH_BLOCKING="${CUDA_LAUNCH_BLOCKING:-0}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  :
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif [[ -x "${ROOT_DIR}/venv-server/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/venv-server/bin/python"
else
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python not found at ${PYTHON_BIN}. Run ./install.sh or set PYTHON_BIN." >&2
  exit 1
fi

echo "Starting backend"
echo "  URL: http://127.0.0.1:${BACKEND_PORT}"
echo "  SAM_BACKEND=${SAM_BACKEND}"
echo "  SAM_DEVICE=${SAM_DEVICE}"
echo "  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}"
echo "  CUDA_LAUNCH_BLOCKING=${CUDA_LAUNCH_BLOCKING}"

cd "${ROOT_DIR}/backend"
exec "${PYTHON_BIN}" run_backend.py
