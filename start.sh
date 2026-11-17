#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  --foreground)
    exec "${ROOT_DIR}/start_backend.sh"
    ;;
  --dev)
    exec "${ROOT_DIR}/service.sh" start --dev
    ;;
  ""|--release)
    exec "${ROOT_DIR}/service.sh" start
    ;;
  *)
    echo "Usage: ./start.sh [--dev|--release|--foreground]" >&2
    exit 2
    ;;
esac
