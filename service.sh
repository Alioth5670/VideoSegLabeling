#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${ROOT_DIR}/runtime_env.sh"
exec "${PYTHON_BIN}" "${ROOT_DIR}/tools/service_control.py" --root "${ROOT_DIR}" "$@"
