#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  "") exec "${ROOT_DIR}/service.sh" stop ;;
  --legacy) exec "${ROOT_DIR}/service.sh" stop-legacy ;;
  *) echo "Usage: ./stop.sh [--legacy]" >&2; exit 2 ;;
esac
