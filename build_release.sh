#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-0.1.0}"
NAME="VideoSegLabeling-${VERSION}"
RELEASE_ROOT="${ROOT_DIR}/release"
PACKAGE_DIR="${RELEASE_ROOT}/${NAME}"
ARCHIVE_PATH="${RELEASE_ROOT}/${NAME}.tar.gz"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js 18+ to build the frontend before packaging." >&2
  exit 1
fi

mkdir -p "${RELEASE_ROOT}"

echo "Building frontend"
cd "${ROOT_DIR}/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build

echo "Preparing ${PACKAGE_DIR}"
rm -rf "${PACKAGE_DIR}" "${ARCHIVE_PATH}"
mkdir -p "${PACKAGE_DIR}/frontend" "${PACKAGE_DIR}/projects" "${PACKAGE_DIR}/checkpoints"

cp -R "${ROOT_DIR}/backend" "${PACKAGE_DIR}/backend"
cp -R "${ROOT_DIR}/frontend/dist" "${PACKAGE_DIR}/frontend/dist"
cp "${ROOT_DIR}/requirements.txt" "${PACKAGE_DIR}/requirements.txt"
cp "${ROOT_DIR}/README.md" "${PACKAGE_DIR}/README.md"
cp "${ROOT_DIR}/LICENSE" "${PACKAGE_DIR}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${PACKAGE_DIR}/THIRD_PARTY_NOTICES.md"
cp "${ROOT_DIR}/.env.example" "${PACKAGE_DIR}/.env.example"
cp "${ROOT_DIR}/install.sh" "${PACKAGE_DIR}/install.sh"
cp "${ROOT_DIR}/start.sh" "${PACKAGE_DIR}/start.sh"
cp "${ROOT_DIR}/start_backend.sh" "${PACKAGE_DIR}/start_backend.sh"
cp "${ROOT_DIR}/stop.sh" "${PACKAGE_DIR}/stop.sh"
cp "${ROOT_DIR}/projects/.gitkeep" "${PACKAGE_DIR}/projects/.gitkeep"
cp "${ROOT_DIR}/checkpoints/.gitkeep" "${PACKAGE_DIR}/checkpoints/.gitkeep"

find "${PACKAGE_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${PACKAGE_DIR}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

chmod +x "${PACKAGE_DIR}/install.sh" "${PACKAGE_DIR}/start.sh" "${PACKAGE_DIR}/start_backend.sh" "${PACKAGE_DIR}/stop.sh"

cd "${RELEASE_ROOT}"
tar -czf "${ARCHIVE_PATH}" "${NAME}"

echo "Release package created:"
echo "  ${PACKAGE_DIR}"
echo "  ${ARCHIVE_PATH}"
