#!/usr/bin/env python3
"""Linux service control, with a detached supervisor when systemd is unavailable."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import sys
import time
import urllib.request

UNIT = 'video-seg-labeling.service'
SCRIPT = Path(__file__).resolve()


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return fields[19]
    except (OSError, IndexError):
        return None


def read_state(root):
    try:
        state = json.loads((root / '.run/service.json').read_text())
        pid = state['pid']
        arguments = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if (state['root'] == str(root) and identity(pid) == state['identity'] and
                str(SCRIPT).encode() in arguments and b'_supervise' in arguments and str(root).encode() in arguments):
            return state
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


@contextmanager
def control_lock(root):
    directory = root / '.run'
    directory.mkdir(exist_ok=True)
    with (directory / 'control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write_state(root, state):
    path = root / '.run/service.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.replace(path)


def check_port(port):
    if not 1 <= port <= 65535:
        raise RuntimeError('Port must be between 1 and 65535')
    with socket.socket() as connection:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            connection.bind(('0.0.0.0', port))
        except OSError as exc:
            raise RuntimeError(f'Port {port} is in use. Stop the old instance first; no process was killed.') from exc


def ready(port):
    try:
        # Ignore ambient HTTP proxy settings for loopback health checks.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/auth/status', timeout=0.5) as response:
            return isinstance(json.load(response).get('initialized'), bool)
    except (OSError, ValueError):
        return False


def frontend_ready():
    try:
        with socket.create_connection(('127.0.0.1', int(os.environ.get('FRONTEND_PORT', '5173'))), timeout=0.3):
            return True
    except OSError:
        return False


def supervise(root, dev):
    instance = (root / '.run/instance.lock').open('a')
    try:
        fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 1
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    state = {'root': str(root), 'pid': os.getpid(), 'identity': identity(os.getpid()),
             'mode': 'dev' if dev else 'release', 'port': int(os.environ.get('BACKEND_PORT', '8080')),
             'frontend_port': int(os.environ.get('FRONTEND_PORT', '5173')) if dev else None,
             'started_at': datetime.now(timezone.utc).isoformat(), 'children': {}}
    processes = {}
    retry_at = {}
    launchers = ['start_backend.sh'] + (['start_frontend.sh'] if dev else [])
    try:
        while not stopping:
            for launcher in launchers:
                process = processes.get(launcher)
                if process is not None and process.poll() is not None:
                    print(f'{launcher} exited ({process.returncode}); retrying in 5 seconds.', flush=True)
                    # Kill orphan descendants of the failed backend before restart.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    processes.pop(launcher)
                    state['children'].pop(launcher, None)
                    retry_at[launcher] = time.monotonic() + 5
                if launcher not in processes and time.monotonic() >= retry_at.get(launcher, 0):
                    print(f'Starting {launcher}', flush=True)
                    process = subprocess.Popen(['bash', str(root / launcher)], cwd=root, start_new_session=True)
                    processes[launcher] = process
                    state['children'][launcher] = process.pid
            write_state(root, state)
            time.sleep(0.2)
    finally:
        for process in processes.values():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 25
        while any(process.poll() is None for process in processes.values()) and time.monotonic() < deadline:
            time.sleep(0.1)
        for process in processes.values():
            # Clean up descendants even if the main backend already exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        (root / '.run/service.json').unlink(missing_ok=True)
        instance.close()
    return 0


def start(root, dev):
    current = read_state(root)
    if current:
        if current['mode'] != ('dev' if dev else 'release'):
            raise RuntimeError('Already running in another mode. Stop it before switching modes.')
        print(f"Already running: supervisor PID {current['pid']}")
        return
    if dev and not (root / 'frontend/package.json').is_file():
        raise RuntimeError('Development mode requires the source frontend and its installed npm dependencies.')
    if not dev and not (root / 'frontend/dist/index.html').is_file():
        raise RuntimeError('Build the frontend first: npm --prefix frontend ci && npm --prefix frontend run build')
    port = int(os.environ.get('BACKEND_PORT', '8080'))
    check_port(port)
    if dev:
        check_port(int(os.environ.get('FRONTEND_PORT', '5173')))
    (root / 'logs').mkdir(exist_ok=True)
    with (root / 'logs/service.log').open('ab', buffering=0) as output:
        process = subprocess.Popen([sys.executable, str(SCRIPT), '--root', str(root), '_supervise'] + (['--dev'] if dev else []),
                                   cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Supervisor failed to start; see logs/service.log')
        if read_state(root) and ready(port) and (not dev or frontend_ready()):
            print(f'Started in background: http://127.0.0.1:{port}')
            if dev:
                print('Development UI: http://127.0.0.1:' + os.environ.get('FRONTEND_PORT', '5173'))
            print('SSH can be disconnected. Logs: ./service.sh logs | Stop: ./stop.sh')
            return
        time.sleep(0.2)
    raise RuntimeError('Still starting/retrying in background; run ./service.sh logs for details.')


def stop(root):
    current = read_state(root)
    if not current:
        print('No managed service is running. For an old tmux/manual instance use ./stop.sh --legacy.')
        return
    try:
        os.kill(current['pid'], signal.SIGTERM)
    except ProcessLookupError:
        print('Already stopped.')
        return
    deadline = time.monotonic() + 30
    while read_state(root) and time.monotonic() < deadline:
        time.sleep(0.1)
    if read_state(root):
        raise RuntimeError('Stop did not finish. Inspect ./service.sh logs; no unrelated process was killed.')
    print('Stopped. Managed inference/export children have also been stopped.')


def stop_legacy(root):
    # Match BOTH the project working directory and the expected entrypoint.
    # Never select by network port: other projects may use the same ports.
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            cwd = (entry / 'cwd').resolve(strict=True)
            args = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            owned = cwd in {root / 'backend', root / 'frontend'}
            matches = any(Path(arg).name in {'run_backend.py', 'uvicorn', 'vite', 'vite.js'} for arg in args if arg)
            if owned and matches and identity(int(entry.name)):
                found.append((int(entry.name), identity(int(entry.name))))
        except OSError:
            pass
    for pid, stamp in found:
        if identity(pid) == stamp:
            os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 25
    while any(identity(pid) == stamp for pid, stamp in found) and time.monotonic() < deadline:
        time.sleep(0.1)
    for pid, stamp in found:
        if identity(pid) == stamp:
            os.kill(pid, signal.SIGKILL)
    print(f'Stopped {len(found)} legacy project processes; other ports/processes were left alone.')


def systemd_owned(root):
    try:
        result = subprocess.run(['systemctl', 'show', UNIT, '--property=WorkingDirectory', '--value'],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip() == str(root)
    except (OSError, subprocess.SubprocessError):
        return False


def unit_text(root, username):
    if any(char in str(root) for char in ('\n', '\r')):
        raise ValueError('Service paths cannot contain newline characters')
    def quoted(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    return f'''[Unit]
Description=VideoSegLabeling
After=network.target

[Service]
Type=simple
User={username}
WorkingDirectory={str(root).replace(chr(37), chr(37) * 2)}
ExecStart={quoted(root / 'start.sh')} --foreground
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=35

[Install]
WantedBy=multi-user.target
'''


def install_systemd(root, username):
    if Path('/proc/1/comm').read_text().strip() != 'systemd':
        raise RuntimeError('systemd is not running on this host. Use ./start.sh for detached background mode instead.')
    if os.geteuid() != 0:
        raise RuntimeError('Install with sudo ./service.sh install-systemd --user YOUR_LOGIN_USER')
    pwd.getpwnam(username)
    if read_state(root):
        raise RuntimeError('Stop the detached service with ./stop.sh before installing systemd.')
    check_port(int(os.environ.get('BACKEND_PORT', '8080')))
    path = Path('/etc/systemd/system') / UNIT
    if path.exists() and not systemd_owned(root):
        raise RuntimeError('A service with this name already exists for another directory; leaving it untouched.')
    path.write_text(unit_text(root, username))
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', UNIT], check=True)
    print('Installed and enabled at boot. Start with ./start.sh; stop with ./stop.sh.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=SCRIPT.parent.parent)
    parser.add_argument('command', choices=['start', 'stop', 'restart', 'status', 'logs', 'stop-legacy', 'install-systemd', '_supervise'])
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--user', default=os.environ.get('SUDO_USER') or pwd.getpwuid(os.getuid()).pw_name)
    options = parser.parse_args()
    root = options.root.resolve()
    if options.command == '_supervise':
        return supervise(root, options.dev)
    if options.command == 'install-systemd':
        install_systemd(root, options.user)
        return 0
    if systemd_owned(root):
        if options.dev:
            raise RuntimeError('systemd manages release mode. For development, run ./start_backend.sh and ./start_frontend.sh directly.')
        if options.command == 'stop-legacy':
            raise RuntimeError('A systemd service is installed. Use ./stop.sh to stop it.')
        if options.command == 'logs':
            return subprocess.call(['journalctl', '-u', UNIT, '-n', '100', '-f'])
        if options.command != 'stop-legacy':
            prefix = [] if os.geteuid() == 0 or options.command == 'status' else ['sudo']
            return subprocess.call(prefix + ['systemctl', options.command, UNIT])
    if options.command == 'logs':
        path = root / 'logs/service.log'
        path.parent.mkdir(exist_ok=True)
        path.touch(exist_ok=True)
        return subprocess.call(['tail', '-n', '100', '-F', str(path)])
    with control_lock(root):
        if options.command == 'restart':
            current = read_state(root)
            if current and current['mode'] == 'dev':
                options.dev = True
        if options.command in {'stop', 'restart'}:
            stop(root)
        if options.command in {'start', 'restart'}:
            start(root, options.dev)
        elif options.command == 'status':
            state = read_state(root)
            if not state:
                print('Stopped')
                return 3
            label = 'Running' if ready(state['port']) else 'Starting/retrying'
            print(f"{label} ({state['mode']}), supervisor PID {state['pid']}, URL http://127.0.0.1:{state['port']}")
            if state.get('frontend_port'):
                print(f"Development UI: http://127.0.0.1:{state['frontend_port']}")
            print('Log: ' + str(root / 'logs/service.log'))
        elif options.command == 'stop-legacy':
            if read_state(root):
                raise RuntimeError('A managed service is running. Use ./stop.sh instead of legacy cleanup.')
            stop_legacy(root)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
