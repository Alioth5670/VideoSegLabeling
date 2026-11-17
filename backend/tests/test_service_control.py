"""Service lifecycle tests launch only disposable CPU HTTP servers on random ports."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/service_control.py'
spec = importlib.util.spec_from_file_location('service_control', SCRIPT)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vsl-service-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'frontend/dist').mkdir(parents=True)
        (self.root / 'frontend/dist/index.html').write_text('test')
        (self.root / 'backend').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.env = {**os.environ, 'BACKEND_PORT': str(self.port)}
        server = '''
import http.server, json, os
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'initialized': True}).encode())
http.server.HTTPServer(('127.0.0.1', int(os.environ['BACKEND_PORT'])), Handler).serve_forever()
'''
        (self.root / 'server.py').write_text(server)
        # bash exec preserves process groups, as the actual backend launcher does.
        (self.root / 'start_backend.sh').write_text('#!/bin/bash\nexec "$TEST_PYTHON" "$TEST_ROOT/server.py"\n')
        self.env.update(TEST_PYTHON=sys.executable, TEST_ROOT=str(self.root))
        self.addCleanup(self.cleanup_service)

    def run_control(self, command, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), command, *args],
                              env=self.env, capture_output=True, text=True, timeout=40)

    def cleanup_service(self):
        self.run_control('stop')

    def test_background_start_duplicate_stop_and_status(self):
        started = self.run_control('start')
        self.assertEqual(started.returncode, 0, started.stderr)
        first = control.read_state(self.root)
        self.assertTrue(control.ready(self.port))
        again = self.run_control('start')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(control.read_state(self.root)['pid'], first['pid'])
        self.assertEqual(self.run_control('status').returncode, 0)
        stopped = self.run_control('stop')
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIsNone(control.read_state(self.root))
        self.assertFalse(control.ready(self.port))
        self.assertEqual(self.run_control('status').returncode, 3)
        self.assertEqual(self.run_control('stop').returncode, 0)

    def test_port_collision_does_not_kill_another_application(self):
        with socket.socket() as occupied:
            occupied.bind(('0.0.0.0', self.port))
            occupied.listen()
            result = self.run_control('start')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('in use', result.stderr)
            self.assertEqual(self.run_control('stop').returncode, 0)
            self.assertIsNone(control.read_state(self.root))
            occupied.getsockname()  # Listener is still ours and remains open.

    def test_stale_pid_metadata_cannot_stop_an_unrelated_process(self):
        (self.root / '.run').mkdir()
        state = {'pid': os.getpid(), 'identity': control.identity(os.getpid()), 'root': str(self.root)}
        (self.root / '.run/service.json').write_text(json.dumps(state))
        self.assertIsNone(control.read_state(self.root))
        self.assertEqual(self.run_control('stop').returncode, 0)

    def test_failed_backend_is_restarted_and_can_be_stopped(self):
        self.assertEqual(self.run_control('start').returncode, 0)
        state = control.read_state(self.root)
        backend = state['children']['start_backend.sh']
        os.kill(backend, signal.SIGKILL)
        deadline = time.monotonic() + 10
        restarted = None
        while time.monotonic() < deadline:
            current = control.read_state(self.root)
            restarted = current['children'].get('start_backend.sh') if current else None
            if restarted and restarted != backend and control.ready(self.port):
                break
            time.sleep(0.1)
        self.assertTrue(restarted)
        self.assertNotEqual(restarted, backend)
        self.assertTrue(control.ready(self.port))

    def test_restart_and_stop_clean_up_managed_children(self):
        self.env['TEST_CHILD_PID'] = str(self.root / 'child.pid')
        path = self.root / 'server.py'
        path.write_text("import subprocess, sys\nfrom pathlib import Path\n" +
                        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n" +
                        "Path(__import__('os').environ['TEST_CHILD_PID']).write_text(str(child.pid))\n" + path.read_text())
        self.assertEqual(self.run_control('start').returncode, 0)
        first = control.read_state(self.root)['pid']
        child = int((self.root / 'child.pid').read_text())
        self.assertIsNotNone(control.identity(child))
        restarted = self.run_control('restart')
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertNotEqual(control.read_state(self.root)['pid'], first)
        self.assertIsNone(control.identity(child))
        child = int((self.root / 'child.pid').read_text())
        self.assertEqual(self.run_control('stop').returncode, 0)
        self.assertIsNone(control.identity(child))

    def test_development_mode_runs_both_servers_without_tmux(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            frontend = sock.getsockname()[1]
        self.env['FRONTEND_PORT'] = str(frontend)
        (self.root / 'frontend/package.json').write_text('{}')
        (self.root / 'start_frontend.sh').write_text('#!/bin/bash\nexport BACKEND_PORT="$FRONTEND_PORT"\nexec "$TEST_PYTHON" "$TEST_ROOT/server.py"\n')
        result = self.run_control('start', '--dev')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = control.read_state(self.root)
        self.assertEqual(state['mode'], 'dev')
        self.assertEqual(len(state['children']), 2)
        self.assertTrue(control.ready(frontend))
        self.assertEqual(self.run_control('restart').returncode, 0)
        self.assertEqual(control.read_state(self.root)['mode'], 'dev')
        self.assertEqual(self.run_control('stop').returncode, 0)
        self.assertFalse(control.ready(frontend))

    def test_generated_systemd_unit_uses_foreground_and_quotes_paths(self):
        text = control.unit_text(Path('/tmp/space path/percent%'), 'test-user')
        self.assertIn('ExecStart="/tmp/space path/percent%%/start.sh" --foreground', text)
        self.assertIn('WorkingDirectory=/tmp/space path/percent%%\n', text)
        self.assertIn('KillMode=mixed', text)
        self.assertIn('User=test-user', text)
