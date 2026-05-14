#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"

usage() {
  cat <<'EOF'
Usage:
  ./install.sh
  ./install.sh --runtime
  ./install.sh --runtime-sam3
  ./install.sh --build-frontend
  ./install.sh --build-frontend-sam3
  ./install.sh --sam3
  ./install.sh --manual

Modes:
  --runtime             Install Python dependencies only. Use this for release zips.
  --runtime-sam3        Install Python dependencies and fetch SAM3.
  --build-frontend      Install Python dependencies, then build frontend/dist.
  --build-frontend-sam3 Install Python dependencies, fetch SAM3, then build frontend/dist.
  --sam3                Fetch or update SAM3 only.
  --manual              Print manual commands without installing anything.
EOF
}

print_manual() {
  cat <<'EOF'
Manual install:

  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt

Optional SAM3 setup:

  git submodule update --init --recursive

If you are using a release package without Git metadata:

  git clone https://github.com/facebookresearch/sam3.git sam3

Optional frontend build for a source checkout:

  cd frontend
  npm ci
  npm run build

Run:

  ./start.sh
EOF
}

install_python() {
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  python -m pip install --upgrade pip
  pip install -r "${ROOT_DIR}/requirements.txt"
}

install_sam3() {
  if ! command -v git >/dev/null 2>&1; then
    echo "git not found. Install Git, then fetch SAM3 manually:" >&2
    echo "  git clone https://github.com/facebookresearch/sam3.git sam3" >&2
    exit 1
  fi

  if [[ -d "${ROOT_DIR}/sam3/.git" ]]; then
    echo "SAM3 already exists at ${ROOT_DIR}/sam3"
    echo "Leaving existing checkout unchanged."
    return
  fi

  if [[ -d "${ROOT_DIR}/.git" && -f "${ROOT_DIR}/.gitmodules" ]]; then
    cd "${ROOT_DIR}"
    git submodule update --init --recursive sam3
    return
  fi

  if [[ -e "${ROOT_DIR}/sam3" ]]; then
    echo "sam3 exists but is not a Git checkout. Move it away or set SAM_REPO_PATH to use it." >&2
    exit 1
  fi

  cd "${ROOT_DIR}"
  git clone https://github.com/facebookresearch/sam3.git sam3
}

install_frontend() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found. Install Node.js 18+ to build frontend/dist, or use a GitHub Release package that already includes it." >&2
    exit 1
  fi

  cd "${ROOT_DIR}/frontend"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
  npm run build
}

run_mode() {
  case "${1}" in
    runtime)
      install_python
      echo "Python dependencies installed. Run ./start.sh"
      ;;
    runtime-sam3)
      install_python
      install_sam3
      echo "Python dependencies installed and SAM3 is available. Place checkpoints under ./checkpoints before using a real SAM backend."
      ;;
    build-frontend)
      install_python
      install_frontend
      echo "Python dependencies installed and frontend built. Run ./start.sh"
      ;;
    build-frontend-sam3)
      install_python
      install_sam3
      install_frontend
      echo "Python dependencies installed, SAM3 is available, and frontend built. Run ./start.sh"
      ;;
    sam3)
      install_sam3
      echo "SAM3 is available at ./sam3. Place checkpoints under ./checkpoints before using a real SAM backend."
      ;;
    manual)
      print_manual
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
}

case "${1:-}" in
  --runtime)
    run_mode runtime
    ;;
  --runtime-sam3)
    run_mode runtime-sam3
    ;;
  --build-frontend)
    run_mode build-frontend
    ;;
  --build-frontend-sam3)
    run_mode build-frontend-sam3
    ;;
  --sam3)
    run_mode sam3
    ;;
  --manual)
    run_mode manual
    ;;
  --help|-h)
    usage
    ;;
  "")
    cat <<'EOF'
VideoSegLabeling installer

1) Auto install Python dependencies only
2) Auto install Python dependencies and fetch SAM3
3) Auto install Python dependencies, fetch SAM3, and build frontend
4) Fetch or update SAM3 only
5) Show manual install commands
EOF
    read -r -p "Select [1-5]: " choice
    case "${choice}" in
      1) run_mode runtime ;;
      2) run_mode runtime-sam3 ;;
      3) run_mode build-frontend-sam3 ;;
      4) run_mode sam3 ;;
      5) run_mode manual ;;
      *)
        echo "Invalid selection." >&2
        exit 1
        ;;
    esac
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
