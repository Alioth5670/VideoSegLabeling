#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
SESSION_NAME="${TMUX_SESSION:-video-seg-labeling}"

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "${SESSION_NAME}" >/dev/null 2>&1; then
  echo "Stopping tmux session: ${SESSION_NAME}"
  tmux kill-session -t "${SESSION_NAME}" >/dev/null 2>&1 || true
  sleep 1
fi

port_pids() {
  python - "$@" <<'PY'
import os
import sys

ports = {int(port) for port in sys.argv[1:]}
inodes = set()

for table in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        with open(table, encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                fields = line.split()
                if len(fields) < 10 or fields[3] != "0A":
                    continue
                port = int(fields[1].rsplit(":", 1)[1], 16)
                if port in ports:
                    inodes.add(fields[9])
    except FileNotFoundError:
        pass

pids = set()
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    try:
        for fd in os.listdir(f"/proc/{name}/fd"):
            try:
                target = os.readlink(f"/proc/{name}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                pids.add(int(name))
                break
    except (FileNotFoundError, PermissionError):
        continue

for pid in sorted(pids):
    print(pid)
PY
}

kill_pid_list() {
  local signal="$1"
  shift
  local pid
  for pid in "$@"; do
    [[ -n "${pid}" ]] && kill "${signal}" "${pid}" 2>/dev/null || true
  done
}

collect_project_pids() {
  local pid cwd
  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)"
    case "${cwd}" in
      "${ROOT_DIR}/backend"| "${ROOT_DIR}/frontend")
        echo "${pid}"
        ;;
    esac
  done < <(pgrep -f 'run_backend.py|uvicorn.*app.main|vite|node.*vite' 2>/dev/null || true)
}

mapfile -t pids < <(
  {
    collect_project_pids
    port_pids "${BACKEND_PORT}" "${FRONTEND_PORT}"
  } | sort -n | uniq
)

if [[ "${#pids[@]}" -eq 0 ]]; then
  echo "No VideoSegLabeling processes found on ports ${BACKEND_PORT}/${FRONTEND_PORT}."
  exit 0
fi

echo "Stopping VideoSegLabeling processes: ${pids[*]}"
kill_pid_list "" "${pids[@]}"
sleep 1

mapfile -t pids < <(
  {
    collect_project_pids
    port_pids "${BACKEND_PORT}" "${FRONTEND_PORT}"
  } | sort -n | uniq
)

if [[ "${#pids[@]}" -gt 0 ]]; then
  echo "Force stopping remaining processes: ${pids[*]}"
  kill_pid_list "-9" "${pids[@]}"
fi
