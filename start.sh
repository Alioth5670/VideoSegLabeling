#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_NAME="${TMUX_SESSION:-video-seg-labeling}"

export BACKEND_PORT="${BACKEND_PORT:-8010}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
export PROJECTS_DIR="${PROJECTS_DIR:-${ROOT_DIR}/projects}"
export SAM_BACKEND="${SAM_BACKEND:-mock}"
export SAM_DEVICE="${SAM_DEVICE:-cuda:0}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export SAM_REPO_PATH="${SAM_REPO_PATH:-${ROOT_DIR}/sam3}"
export SAM_CHECKPOINT_PATH="${SAM_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.pt}"
export SAM31_CHECKPOINT_PATH="${SAM31_CHECKPOINT_PATH:-${ROOT_DIR}/checkpoints/sam3.1_multiplex.pt}"
export CUDA_LAUNCH_BLOCKING="${CUDA_LAUNCH_BLOCKING:-0}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

shell_quote() {
  printf "%q" "$1"
}

has_release_frontend() {
  [[ -f "${ROOT_DIR}/frontend/dist/index.html" ]]
}

start_release() {
  echo "Starting VideoSegLabeling release server"
  echo "  URL: http://127.0.0.1:${BACKEND_PORT}"
  echo "  SAM_BACKEND=${SAM_BACKEND}"
  exec "${ROOT_DIR}/start_backend.sh"
}

start_dev_tmux() {
  if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux not found. Either install tmux or build a release frontend with ./build_release.sh." >&2
    exit 1
  fi

  ENV_PREFIX="CUDA_VISIBLE_DEVICES=$(shell_quote "${CUDA_VISIBLE_DEVICES}")"
  ENV_PREFIX+=" SAM_BACKEND=$(shell_quote "${SAM_BACKEND}")"
  ENV_PREFIX+=" SAM_DEVICE=$(shell_quote "${SAM_DEVICE}")"
  ENV_PREFIX+=" BACKEND_PORT=$(shell_quote "${BACKEND_PORT}")"
  ENV_PREFIX+=" FRONTEND_PORT=$(shell_quote "${FRONTEND_PORT}")"
  ENV_PREFIX+=" VITE_BACKEND_URL=$(shell_quote "${VITE_BACKEND_URL}")"
  ENV_PREFIX+=" PROJECTS_DIR=$(shell_quote "${PROJECTS_DIR}")"
  ENV_PREFIX+=" SAM_REPO_PATH=$(shell_quote "${SAM_REPO_PATH}")"
  ENV_PREFIX+=" SAM_CHECKPOINT_PATH=$(shell_quote "${SAM_CHECKPOINT_PATH}")"
  ENV_PREFIX+=" SAM31_CHECKPOINT_PATH=$(shell_quote "${SAM31_CHECKPOINT_PATH}")"
  ENV_PREFIX+=" CUDA_LAUNCH_BLOCKING=$(shell_quote "${CUDA_LAUNCH_BLOCKING}")"

  echo "Starting VideoSegLabeling development servers in tmux: ${SESSION_NAME}"
  echo "  Backend:  http://127.0.0.1:${BACKEND_PORT}"
  echo "  Frontend: http://localhost:${FRONTEND_PORT}"

  "${ROOT_DIR}/stop.sh" >/dev/null 2>&1 || true
  tmux kill-session -t "${SESSION_NAME}" >/dev/null 2>&1 || true
  tmux new-session -d -s "${SESSION_NAME}" -n backend "cd $(shell_quote "${ROOT_DIR}") && ${ENV_PREFIX} exec ./start_backend.sh"
  tmux new-window -t "${SESSION_NAME}:" -n frontend "cd $(shell_quote "${ROOT_DIR}") && ${ENV_PREFIX} exec ./start_frontend.sh"
  tmux select-window -t "${SESSION_NAME}:backend"

  echo "Started. Attach with: tmux attach -t ${SESSION_NAME}"
}

case "${1:-}" in
  --dev)
    start_dev_tmux
    ;;
  --release)
    start_release
    ;;
  *)
    if has_release_frontend; then
      start_release
    else
      start_dev_tmux
    fi
    ;;
esac
