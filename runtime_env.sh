#!/usr/bin/env bash
# Sourced by launchers; .env stays private and is never printed.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"
if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi
export BACKEND_PORT="${BACKEND_PORT:-8080}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
export PROJECTS_DIR="${PROJECTS_DIR:-${ROOT_DIR}/projects}"
export SAM_BACKEND="${SAM_BACKEND:-sam3_multiplex_video}"
export SAM_DEVICE="${SAM_DEVICE:-cuda:0}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export SAM_REPO_PATH="${SAM_REPO_PATH:-${ROOT_DIR}/sam3}"
export SAM_CHECKPOINT_PATH="${SAM_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.pt}"
export SAM31_CHECKPOINT_PATH="${SAM31_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.1_multiplex.pt}"
export CUDA_LAUNCH_BLOCKING="${CUDA_LAUNCH_BLOCKING:-0}"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "${ROOT_DIR}/venv-server/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/venv-server/bin/python"
  else
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  fi
elif [[ "${PYTHON_BIN}" != /* ]]; then
  if [[ "${PYTHON_BIN}" == */* ]]; then
    PYTHON_BIN="${ROOT_DIR}/${PYTHON_BIN}"
  else
    PYTHON_BIN="$(command -v "${PYTHON_BIN}" || true)"
  fi
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python environment missing. Run ./install.sh or set PYTHON_BIN." >&2
  return 1
fi
export PYTHON_BIN
