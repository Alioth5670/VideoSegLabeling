"""Run with: PYTHONPATH=backend venv-server/bin/python -m unittest discover -s backend/tests."""
import os
import tempfile
import unittest

# Never use real project files or the live account database in these tests.
_root = tempfile.TemporaryDirectory()
os.environ['PROJECTS_DIR'] = _root.name
os.environ['SAM_BACKEND'] = 'mock'

from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import account_store, sam_service, video_service, export_jobs



class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(export_jobs.shutdown)
        cls.legacy = video_service.create_project('Existing project')
        cls.admin = TestClient(app)
        assert cls.admin.post('/api/auth/setup', json={'username': 'admin', 'password': 'admin-password'}).status_code == 200
        assert cls.admin.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-password'}).status_code == 200
        cls.user_id = cls.admin.post('/api/auth/users', json={'username': 'worker', 'password': 'worker-password'}).json()['id']
        cls.worker = TestClient(app)
        cls.worker.post('/api/auth/login', json={'username': 'worker', 'password': 'worker-password'})
        cls.project = cls.worker.post('/api/projects', json={'name': 'Private worker data'}).json()

    def test_bootstrap_and_isolation(self):
        self.assertEqual(self.admin.post('/api/auth/setup', json={'username': 'other', 'password': 'other-password'}).status_code, 409)
        self.assertEqual(self.admin.get('/api/projects').json()['projects'][0]['project_id'], self.legacy['project_id'])
        self.assertEqual(self.worker.get('/api/projects', params={'q': 'Private'}).json()['total'], 1)
        self.assertEqual(self.worker.get('/api/projects', params={'q': 'Existing'}).json()['total'], 0)
        self.assertEqual(self.worker.get('/api/projects', params={'offset': 1}).json()['projects'], [])
        root = '/api/projects/' + self.legacy['project_id']
        for suffix in ['', '/annotations', '/frames/0', '/masks/1/0', '/download/project.json']:
            self.assertEqual(self.worker.get(root + suffix).status_code, 404)
        for suffix in ['/export', '/sam/session', '/objects']:
            self.assertEqual(self.worker.post(root + suffix, json={}).status_code, 404)
        self.assertEqual(self.admin.get('/api/projects/' + self.project['project_id']).status_code, 200)
        self.assertEqual(self.worker.get('/api/projects/' + self.project['project_id'], params={'video_id': '../../other'}).status_code, 404)
        self.assertEqual(self.worker.post('/api/auth/users', json={'username': 'bad', 'password': 'long-password'}).status_code, 403)
        self.assertEqual(self.worker.post('/api/sam/device', json={'device': 'cpu'}).status_code, 403)
        self.assertEqual(self.worker.post('/api/projects', json={'name': 'bad', 'project_dir': '/tmp/unauthorized'}).status_code, 403)

    def test_account_role_flags_are_json_booleans(self):
        for client, expected in ((self.worker, False), (self.admin, True)):
            user = client.get('/api/auth/me').json()['user']
            self.assertIs(user['admin'], expected)
            self.assertIs(user['active'], True)
            stored = account_store.user(user['id'])
            self.assertIs(stored['admin'], expected)
            self.assertIs(stored['active'], True)
        users = self.admin.get('/api/auth/users').json()['users']
        for user in users:
            self.assertIs(type(user['admin']), bool)
            self.assertIs(type(user['active']), bool)
        browser = TestClient(app)
        self.addCleanup(browser.close)
        response = browser.post('/api/auth/login', json={'username': 'worker', 'password': 'worker-password'})
        self.assertIs(response.json()['user']['admin'], False)
        self.assertIs(response.json()['user']['active'], True)

    def test_change_own_password_checks_current_password_and_keeps_data(self):
        self.admin.post('/api/auth/users', json={'username': 'self_change', 'password': 'old123'})
        first, second, anonymous = TestClient(app), TestClient(app), TestClient(app)
        for client in (first, second, anonymous):
            self.addCleanup(client.close)
        for client in (first, second):
            self.assertEqual(client.post('/api/auth/login', json={'username': 'self_change', 'password': 'old123'}).status_code, 200)
        project = first.post('/api/projects', json={'name': 'Own password change data'}).json()
        project_id = project['project_id']
        before = video_service.project_json_path(project_id).read_bytes()
        frames = str(video_service.project_path(project_id) / 'frames')
        session = sam_service.start_video_session(project_id, '', frames)
        payload = {'current_password': 'old123', 'new_password': 'new456'}
        self.assertEqual(anonymous.post('/api/auth/password', json=payload).status_code, 401)
        wrong = first.post('/api/auth/password', json={'current_password': 'bad123', 'new_password': 'new456'})
        self.assertEqual(wrong.status_code, 400)
        self.assertIn('当前密码', wrong.json()['detail'])
        self.assertEqual(first.post('/api/auth/password', json={'current_password': 'old123', 'new_password': '12345'}).status_code, 422)
        self.assertEqual(first.post('/api/auth/password', json={**payload, 'user_id': self.user_id}).status_code, 422)
        for client in (first, second):
            self.assertEqual(client.get('/api/auth/me').status_code, 200)
        changed = first.post('/api/auth/password', json=payload)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertIn('Max-Age=0', changed.headers['set-cookie'])
        for client in (first, second):
            self.assertEqual(client.get('/api/auth/me').status_code, 401)
        self.assertEqual(first.post('/api/auth/login', json={'username': 'self_change', 'password': 'old123'}).status_code, 401)
        self.assertEqual(first.post('/api/auth/login', json={'username': 'self_change', 'password': 'new456'}).status_code, 200)
        self.assertEqual(first.get('/api/projects/' + project_id).status_code, 200)
        self.assertEqual(video_service.project_json_path(project_id).read_bytes(), before)
        self.assertEqual(sam_service.find_video_session(project_id, frames)['session_id'], session)
        self.assertEqual(self.worker.get('/api/auth/me').status_code, 200)
        self.assertEqual(self.admin.get('/api/auth/me').status_code, 200)

    def test_change_own_password_works_for_admin(self):
        account_store.create_user('self_change_admin', 'old123', admin=True)
        client = TestClient(app)
        self.addCleanup(client.close)
        client.post('/api/auth/login', json={'username': 'self_change_admin', 'password': 'old123'})
        self.assertEqual(client.post('/api/auth/password', json={'current_password': 'old123', 'new_password': 'new456'}).status_code, 200)
        self.assertEqual(client.get('/api/auth/me').status_code, 401)
        login = client.post('/api/auth/login', json={'username': 'self_change_admin', 'password': 'new456'})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()['user']['admin'])

    def test_management_lists_and_account_scopes(self):
        worker_id = self.worker.get('/api/auth/me').json()['user']['id']
        admin_id = self.admin.get('/api/auth/me').json()['user']['id']
        all_projects = self.admin.get('/api/projects', params={'all_accounts': True}).json()
        self.assertGreaterEqual(all_projects['total'], 2)
        self.assertIn(worker_id, {row['owner_id'] for row in all_projects['projects']})
        filtered = self.admin.get('/api/projects', params={'all_accounts': True, 'owner_id': worker_id}).json()
        self.assertTrue(all(row['owner_id'] == worker_id and row['owner_username'] == 'worker' for row in filtered['projects']))
        own = self.worker.get('/api/projects').json()
        self.assertTrue(all(row['owner_id'] == worker_id for row in own['projects']))
        self.assertEqual(self.worker.get('/api/projects', params={'owner_id': admin_id}).status_code, 403)
        self.assertEqual(self.worker.get('/api/projects', params={'all_accounts': True}).status_code, 403)
        self.assertEqual(self.admin.get('/api/projects/not-a-project').status_code, 404)

    def test_management_create_for_user_and_rename(self):
        worker_id = self.worker.get('/api/auth/me').json()['user']['id']
        admin_id = self.admin.get('/api/auth/me').json()['user']['id']
        created = self.admin.post('/api/projects', json={'name': 'Managed project', 'owner_id': worker_id})
        self.assertEqual(created.status_code, 200, created.text)
        project = created.json()
        root = '/api/projects/' + project['project_id']
        stale = video_service.load_project(project['project_id'])
        renamed = self.worker.patch(root, json={'name': '  Managed renamed  '})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()['name'], 'Managed renamed')
        self.assertEqual(self.admin.get(root).json()['project']['name'], 'Managed renamed')
        video_service.save_project(project['project_id'], stale)
        self.assertEqual(self.worker.get(root).json()['project']['name'], 'Managed renamed')
        self.worker.post('/api/projects', json={'name': 'Management duplicate'})
        self.assertEqual(self.admin.patch(root, json={'name': ' MANAGEMENT DUPLICATE '}).status_code, 409)
        self.assertEqual(self.worker.patch(root, json={'name': '  '}).status_code, 422)
        self.assertEqual(self.worker.post('/api/projects', json={'name': 'Forbidden account', 'owner_id': admin_id}).status_code, 403)
        self.assertEqual(self.worker.patch('/api/projects/' + self.legacy['project_id'], json={'name': 'Forbidden rename'}).status_code, 404)

    def test_management_transfer_checks_roles_and_name_conflicts(self):
        from fastapi.testclient import TestClient
        target_id = self.admin.post('/api/auth/users', json={'username': 'management_target', 'password': 'target-password'}).json()['id']
        target = TestClient(app)
        self.addCleanup(target.close)
        target.post('/api/auth/login', json={'username': 'management_target', 'password': 'target-password'})
        project = self.worker.post('/api/projects', json={'name': 'Transfer managed project'}).json()
        root = '/api/projects/' + project['project_id']
        self.assertEqual(self.worker.post(root + '/transfer', json={'owner_id': target_id}).status_code, 403)
        conflicting = target.post('/api/projects', json={'name': 'Transfer managed project'}).json()
        session = sam_service.start_video_session(project['project_id'], '', '')
        self.assertEqual(self.admin.post(root + '/transfer', json={'owner_id': target_id}).status_code, 409)
        self.assertEqual(self.worker.get(root).status_code, 200)
        self.assertIn(session, sam_service._sessions)
        target.patch('/api/projects/' + conflicting['project_id'], json={'name': 'Other target name'})
        transferred = self.admin.post(root + '/transfer', json={'owner_id': target_id})
        self.assertEqual(transferred.status_code, 200, transferred.text)
        self.assertNotIn(session, sam_service._sessions)
        self.assertEqual(self.worker.get(root).status_code, 404)
        self.assertEqual(self.worker.delete(root).status_code, 404)
        self.assertEqual(target.get(root).status_code, 200)
        self.assertEqual(self.admin.get(root).status_code, 200)
        self.admin.patch('/api/auth/users/' + target_id, json={'active': False})
        another = self.worker.post('/api/projects', json={'name': 'Cannot transfer to disabled'}).json()
        self.assertEqual(self.admin.post('/api/projects/' + another['project_id'] + '/transfer', json={'owner_id': target_id}).status_code, 400)
        self.assertEqual(self.admin.post('/api/projects', json={'name': 'Cannot create for disabled', 'owner_id': target_id}).status_code, 400)

    def test_management_missing_project_files_can_be_recycled(self):
        import shutil
        for missing_directory in (False, True):
            name = 'Missing directory entry' if missing_directory else 'Missing metadata entry'
            project = self.worker.post('/api/projects', json={'name': name}).json()
            project_id = project['project_id']
            root = '/api/projects/' + project_id
            folder = video_service.project_path(project_id)
            metadata = (folder / 'project.json').read_text()
            if missing_directory:
                shutil.rmtree(folder)
            else:
                (folder / 'project.json').unlink()
            rows = self.worker.get('/api/projects', params={'q': name}).json()['projects']
            self.assertEqual(rows[0]['data_status'], 'missing')
            self.assertTrue(rows[0]['missing_reason'])
            self.assertEqual(self.worker.get(root).status_code, 404)
            self.assertEqual(self.worker.delete(root).status_code, 200)
            self.assertEqual(self.worker.get('/api/projects', params={'q': name}).json()['total'], 0)
            deleted = self.worker.get('/api/projects', params={'q': name, 'deleted': True}).json()['projects']
            self.assertEqual(deleted[0]['data_status'], 'missing')
            self.assertEqual(self.worker.post(root + '/restore').status_code, 404)
            self.assertFalse((folder / 'project.json').exists())
            if missing_directory:
                self.assertFalse(folder.exists())
            # Files may be temporarily unavailable (for example, an offline mount).
            # Restoring the actual files makes the retained record usable again.
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'project.json').write_text(metadata)
            restored_files = self.worker.get('/api/projects', params={'q': name, 'deleted': True}).json()['projects']
            self.assertEqual(restored_files[0]['data_status'], 'available')
            self.assertEqual(self.worker.post(root + '/restore').status_code, 200)
            self.assertEqual(self.worker.get(root).json()['project']['project_id'], project_id)

    def test_management_recycle_and_restore_preserve_files(self):
        project = self.worker.post('/api/projects', json={'name': 'Recycle managed project'}).json()
        project_id = project['project_id']
        root = '/api/projects/' + project_id
        file = video_service.project_path(project_id) / 'sentinel.txt'
        file.write_text('keep project data')
        self.assertEqual(self.worker.delete(root).status_code, 200)
        self.assertEqual(file.read_text(), 'keep project data')
        self.assertEqual(self.worker.get(root).status_code, 404)
        self.assertEqual(self.admin.get(root).status_code, 404)
        self.assertEqual(self.worker.get('/api/projects', params={'q': 'Recycle managed project'}).json()['total'], 0)
        deleted = self.worker.get('/api/projects', params={'q': 'Recycle managed project', 'deleted': True}).json()
        self.assertEqual(deleted['total'], 1)
        self.assertEqual(deleted['projects'][0]['project_id'], project_id)
        replacement = self.worker.post('/api/projects', json={'name': 'Recycle managed project'}).json()
        self.assertEqual(self.worker.post(root + '/restore').status_code, 409)
        self.worker.patch('/api/projects/' + replacement['project_id'], json={'name': 'Replacement managed project'})
        self.assertEqual(self.admin.post(root + '/restore').status_code, 200)
        self.assertEqual(self.worker.get(root).status_code, 200)
        self.assertEqual(file.read_text(), 'keep project data')
        self.assertEqual(self.worker.delete('/api/projects/' + self.legacy['project_id']).status_code, 404)
        self.assertEqual(self.admin.delete(root).status_code, 200)
        self.assertEqual(self.worker.post(root + '/restore').status_code, 200)

    def test_management_recycle_waits_for_inference(self):
        import threading
        project = self.worker.post('/api/projects', json={'name': 'Busy managed project'}).json()
        project_id = project['project_id']
        root = '/api/projects/' + project_id
        session = sam_service.start_video_session(project_id, '', '')
        locked = threading.Event()
        release = threading.Event()
        def hold():
            with sam_service._inference_lock:
                locked.set()
                release.wait(5)
        thread = threading.Thread(target=hold)
        thread.start()
        locked.wait(5)
        try:
            self.assertEqual(self.worker.delete(root).status_code, 409)
            self.assertEqual(self.worker.get(root).status_code, 200)
        finally:
            release.set()
            thread.join()
        self.assertEqual(self.worker.delete(root).status_code, 200)
        self.assertNotIn(session, sam_service._sessions)

    def test_owned_annotation_workflow(self):
        import cv2
        import numpy as np
        from pathlib import Path
        path = Path(_root.name) / 'sample.avi'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 5, (32, 32))
        for _ in range(3):
            writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
        writer.release()
        root = '/api/projects/' + self.project['project_id']
        with path.open('rb') as source:
            response = self.worker.post(root + '/video', files={'video': ('sample.avi', source, 'video/x-msvideo')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.worker.get(root).status_code, 200)
        self.assertEqual(self.worker.get(root + '/frames/0').status_code, 200)
        session = self.worker.post(root + '/sam/session').json()['session_id']
        segmented = self.worker.post(root + '/sam/segment', json={
            'session_id': session, 'frame_index': 0, 'box': [4, 4, 20, 20], 'category': 'test'})
        self.assertEqual(segmented.status_code, 200, segmented.text)
        self.assertTrue(segmented.json()['objects'])
        self.assertEqual(self.worker.get(root + '/frames/0/overlay').status_code, 200)
        import json
        propagated = self.worker.post(root + '/sam/propagate', json={
            'session_id': session, 'object_ids': [1], 'start_frame': 0, 'end_frame': 2, 'direction': 'forward'})
        self.assertEqual(propagated.status_code, 200, propagated.text)
        events = [json.loads(line) for line in propagated.text.splitlines()]
        self.assertEqual(sum(event['type'] == 'frame' for event in events), 3)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(events[-1]['frame_count'], 3)
        self.assertEqual(events[-1]['frames'], [])
        summary = self.worker.get(root, params={'summary': True}).json()['annotations']
        self.assertEqual(summary['annotated_frames'], [0, 1, 2])
        self.assertNotIn('frames', summary)
        exported = self.worker.post(root + '/export', json={'format': 'project_json'})
        self.assertEqual(exported.status_code, 202, exported.text)
        task = exported.json()
        self.assertEqual(task['status'], 'queued')
        status_url = root + '/export/' + task['job_id']
        self.assertEqual(self.admin.get(status_url).status_code, 200)
        # Other project APIs remain usable while the export runs in a subprocess.
        self.assertEqual(self.worker.get(root + '/frames/0').status_code, 200)
        import time
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            task = self.worker.get(status_url).json()
            if task['status'] in {'completed', 'failed'}:
                break
            time.sleep(0.05)
        self.assertEqual(task['status'], 'completed', task)
        self.assertEqual(task['progress'], 100)
        url = task['download_url']
        self.assertEqual(self.worker.get(url).status_code, 200)
        self.assertEqual(self.admin.get(url).status_code, 200)
        self.assertEqual(self.worker.post(root + '/sam/session').json()['session_id'], session)
        self.assertEqual(self.worker.post(root + '/sam/session/close', json={'session_id': session}).status_code, 200)
        next_session = self.worker.post(root + '/sam/session').json()['session_id']
        self.assertNotEqual(next_session, session)


    def make_session_project(self, name):
        import numpy as np
        from PIL import Image
        project = self.worker.post('/api/projects', json={'name': name}).json()
        project_id = project['project_id']
        data = video_service.load_project(project_id)
        data['videos'] = []
        for video_id in ('video-a', 'video-b'):
            base = video_service.project_path(project_id) / 'videos' / video_id
            (base / 'frames').mkdir(parents=True)
            Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(base / 'frames/000000.jpg')
            data['videos'].append({'video_id': video_id, 'name': video_id, 'storage_dir': f'videos/{video_id}',
                'video_path': f'videos/{video_id}/input.avi', 'frame_count': 1, 'width': 16, 'height': 16})
        data['active_video_id'] = 'video-a'
        video_service.save_project(project_id, data)
        return project_id, '/api/projects/' + project_id

    def test_gpu_admin_endpoints_require_admin_and_persist_settings(self):
        from pathlib import Path
        from dataclasses import replace
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.services.sam_pool import SAMPool
        with tempfile.TemporaryDirectory() as root:
            config = replace(sam_service.config, projects_dir=Path(root), sam_backend='mock')
            isolated = SAMPool(config, SimpleNamespace())
            self.addCleanup(isolated.shutdown)
            with patch('app.api.sam.sam_service', isolated):
                self.assertEqual(self.worker.get('/api/sam/admin').status_code, 403)
                initial = self.admin.get('/api/sam/admin')
                self.assertEqual(initial.status_code, 200, initial.text)
                values = initial.json()['settings']
                self.assertEqual(self.worker.put('/api/sam/admin/settings', json=values).status_code, 403)
                self.assertFalse(isolated._settings_path.exists())
                for invalid in ({**values, 'sam_gpu_max_utilization': -1}, {**values, 'unknown': 1}):
                    self.assertEqual(self.admin.put('/api/sam/admin/settings', json=invalid).status_code, 422)
                values.update(sam_gpu_devices='0, 2,0', sam_gpu_min_free_mb=23000)
                saved = self.admin.put('/api/sam/admin/settings', json=values)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()['settings']['sam_gpu_devices'], '0,2')
                self.assertTrue(isolated._settings_path.exists())
                restored = SAMPool(config, SimpleNamespace())
                self.addCleanup(restored.shutdown)
                self.assertEqual(restored.config.sam_gpu_min_free_mb, 23000)
                self.assertEqual(restored.config.sam_gpu_devices, '0,2')
                self.assertEqual(self.worker.post('/api/sam/admin/sessions/unknown/release', json={'force': True}).status_code, 403)
                self.assertEqual(self.admin.post('/api/sam/admin/sessions/unknown/release', json={'force': True}).status_code, 404)

    def test_gpu_pool_api_assigns_per_account_and_reports_capacity(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.services.sam_pool import GPUCapacityError
        worker_project, worker_root = self.make_session_project('Worker GPU allocation')
        # The administrator can label this project using its own isolated session.
        devices = [{'id': f'GPU-api-{i}', 'index': i, 'label': f'GPU {i}',
                    'available': True, 'free_memory_mb': 24000} for i in range(2)]
        def spawn(lease):
            lease.process = SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda timeout: 0)
        try:
            with patch.object(sam_service, '_active_backend', 'sam3_video'), \
                 patch.object(sam_service, '_spawn', side_effect=spawn), \
                 patch.object(sam_service, '_rpc', return_value='native-api'), \
                 patch.object(sam_service, '_start_reaper'), \
                 patch('app.services.sam_pool.discover_gpus', return_value=devices):
                worker = self.worker.post(worker_root + '/sam/session', params={'video_id': 'video-a'})
                admin = self.admin.post(worker_root + '/sam/session', params={'video_id': 'video-a'})
                self.assertEqual(worker.status_code, 200, worker.text)
                self.assertEqual(admin.status_code, 200, admin.text)
                self.assertNotEqual(worker.json()['session_id'], admin.json()['session_id'])
                self.assertNotEqual(worker.json()['device'], admin.json()['device'])
                for client, result in ((self.worker, worker), (self.admin, admin)):
                    current = client.get(worker_root + '/sam/session', params={'video_id': 'video-a'}).json()
                    self.assertEqual(current['session']['session_id'], result.json()['session_id'])
                    self.assertEqual(current['device'], result.json()['device'])
                resources = self.worker.get('/api/sam/resources')
                self.assertEqual(resources.status_code, 200)
                self.assertEqual(resources.json()['free'], 0)
                self.assertNotIn('owner_id', resources.text)
                with patch.object(sam_service, 'start_video_session', side_effect=GPUCapacityError('资源忙')):
                    blocked = self.worker.post(worker_root + '/sam/session', params={'video_id': 'video-a'})
                    self.assertEqual(blocked.status_code, 409)
                self.assertEqual(self.worker.post(worker_root + '/sam/session/close', json={'session_id': worker.json()['session_id']}).status_code, 200)
                self.assertEqual(self.admin.post(worker_root + '/sam/session/close', json={'session_id': admin.json()['session_id']}).status_code, 200)
        finally:
            with sam_service._pool_lock:
                for lease in list(sam_service._leases.values()):
                    sam_service._dispose(lease)

    def test_segment_failure_logs_full_traceback(self):
        from unittest.mock import patch
        project_id, root = self.make_session_project('Segmentation failure logging')
        session = self.worker.post(root + '/sam/session', params={'video_id': 'video-a'}).json()['session_id']
        message = 'Expected all tensors to be on the same device, but got mat2 is on cpu'
        with patch.object(sam_service, 'segment_frame', side_effect=RuntimeError(message)) as segment:
            with self.assertLogs('app.api.sam', level='ERROR') as captured:
                response = self.worker.post(root + '/sam/segment', params={'video_id': 'video-a'}, json={
                    'session_id': session, 'frame_index': 0, 'box': [2, 2, 10, 10]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], message)
        self.assertEqual(segment.call_count, 1)
        self.assertIsNotNone(captured.records[0].exc_info)
        self.assertIn(project_id, captured.output[0])
        self.assertIn('Traceback', captured.output[0])

    def test_session_survives_browsing_until_explicit_new_session(self):
        project_id, root = self.make_session_project('Session navigation test')
        first = self.worker.post(root + '/sam/session', params={'video_id': 'video-a'}).json()['session_id']
        response = self.worker.post(root + '/sam/segment', params={'video_id': 'video-a'}, json={
            'session_id': first, 'frame_index': 0, 'box': [2, 2, 10, 10]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session']['object_ids'], [1])
        self.worker.post(root + '/videos/video-b/activate')
        self.assertIsNone(self.worker.get(root + '/sam/session', params={'video_id': 'video-b'}).json()['session'])
        self.worker.post(root + '/videos/video-a/activate')
        recovered = self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session']
        self.assertEqual(recovered, {'session_id': first, 'object_ids': [1]})
        self.assertEqual(self.worker.post(root + '/sam/session', params={'video_id': 'video-a'}).json()['session_id'], first)
        invalid = self.worker.post(root + '/sam/segment', params={'video_id': 'video-b'}, json={
            'session_id': first, 'frame_index': 0, 'box': [2, 2, 10, 10]})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.worker.post(root + '/sam/session/reset', params={'video_id': 'video-a'}, json={'session_id': first}).status_code, 200)
        reset = self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session']
        self.assertEqual(reset, {'session_id': first, 'object_ids': []})
        second = self.worker.post(root + '/sam/session', params={'video_id': 'video-b'}).json()['session_id']
        self.assertNotEqual(first, second)
        self.assertNotIn(first, sam_service._sessions)
        self.assertIsNone(self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session'])
        self.assertEqual(len(sam_service._sessions), 1)

    def test_propagation_stop_uses_original_video_while_browsing(self):
        import json
        import threading
        import time
        from unittest.mock import patch
        from concurrent.futures import ThreadPoolExecutor
        project_id, root = self.make_session_project('Propagation navigation test')
        session = self.worker.post(root + '/sam/session', params={'video_id': 'video-a'}).json()['session_id']
        started = threading.Event()
        def slow(*args, should_cancel=None, **kwargs):
            with sam_service._inference_lock:
                started.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and not should_cancel():
                    threading.Event().wait(.01)
            return []
        with patch.object(sam_service, 'propagate_in_video', side_effect=slow):
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.worker.post, root + '/sam/propagate', params={'video_id': 'video-a'}, json={
                    'session_id': session, 'object_ids': [1], 'start_frame': 0, 'end_frame': 0, 'direction': 'forward'})
                self.assertTrue(started.wait(3))
                self.assertEqual(self.worker.post(root + '/videos/video-b/activate').status_code, 200)
                self.assertIsNone(self.worker.get(root + '/sam/session', params={'video_id': 'video-b'}).json()['session'])
                recovered = self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session']
                self.assertEqual(recovered['session_id'], session)
                stopped = self.worker.post(root + '/sam/propagate/cancel', params={'video_id': 'video-a'}, json={'session_id': session})
                self.assertTrue(stopped.json()['cancelled'])
                events = [json.loads(line) for line in result.result(timeout=6).text.splitlines()]
                self.assertEqual(events[-1]['type'], 'cancelled')
        self.assertIn(session, sam_service._sessions)
        self.assertEqual(self.worker.get(root + '/sam/session', params={'video_id': 'video-a'}).json()['session']['session_id'], session)

    def test_unauthenticated_and_csrf(self):
        client = TestClient(app)
        self.assertEqual(client.get('/api/projects').status_code, 401)
        self.assertEqual(client.get('/projects/.accounts.sqlite3').status_code, 404)
        self.assertEqual(client.get('/projects/' + self.legacy['project_id'] + '/project.json').status_code, 404)
        self.assertEqual(client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong-password'}).status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-password'}, headers={'Origin': 'https://attacker.example'}).status_code, 403)
        response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-password'})
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        client.post('/api/auth/logout')
        self.assertEqual(client.get('/api/auth/me').status_code, 401)

    def test_password_minimum_and_admin_reset_revoke_only_target_logins(self):
        from app.api.auth import Credentials
        self.assertEqual(Credentials(username='six', password='123456').password, '123456')
        self.assertEqual(self.admin.post('/api/auth/users', json={'username': 'too_short', 'password': '12345'}).status_code, 422)
        created = self.admin.post('/api/auth/users', json={'username': 'reset_target', 'password': 'old123'})
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()['id']
        first, second = TestClient(app), TestClient(app)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        for client in (first, second):
            self.assertEqual(client.post('/api/auth/login', json={'username': 'reset_target', 'password': 'old123'}).status_code, 200)
        project = first.post('/api/projects', json={'name': 'Password reset data'}).json()
        path = video_service.project_path(project['project_id']) / 'annotations-sentinel.txt'
        path.write_text('keep annotations')
        frames = str(video_service.project_path(project['project_id']) / 'frames')
        session = sam_service.start_video_session(project['project_id'], '', frames)
        url = '/api/auth/users/' + user_id + '/password'
        self.assertEqual(first.post(url, json={'password': 'new456'}).status_code, 403)
        self.assertEqual(self.admin.post(url, json={'password': '12345'}).status_code, 422)
        self.assertEqual(first.get('/api/auth/me').status_code, 200)
        response = self.admin.post(url, json={'password': 'new456'})
        self.assertEqual(response.status_code, 200, response.text)
        for client in (first, second):
            self.assertEqual(client.get('/api/auth/me').status_code, 401)
        self.assertEqual(first.post('/api/auth/login', json={'username': 'reset_target', 'password': 'old123'}).status_code, 401)
        self.assertEqual(first.post('/api/auth/login', json={'username': 'reset_target', 'password': 'new456'}).status_code, 200)
        self.assertEqual(first.get('/api/projects/' + project['project_id']).status_code, 200)
        self.assertEqual(path.read_text(), 'keep annotations')
        self.assertEqual(sam_service.find_video_session(project['project_id'], frames)['session_id'], session)
        self.assertEqual(self.worker.get('/api/auth/me').status_code, 200)
        self.assertEqual(self.admin.get('/api/auth/me').status_code, 200)
        users = self.admin.get('/api/auth/users').json()['users']
        self.assertTrue(all('password' not in user for user in users))
        self.assertEqual(self.admin.post('/api/auth/users/missing/password', json={'password': 'new456'}).status_code, 404)
        self.assertEqual(self.admin.patch('/api/auth/users/missing', json={'active': False}).status_code, 404)
        self.admin.patch('/api/auth/users/' + user_id, json={'active': False})
        self.assertEqual(self.admin.post(url, json={'password': 'next78'}).status_code, 200)
        self.assertEqual(first.post('/api/auth/login', json={'username': 'reset_target', 'password': 'next78'}).status_code, 401)
        self.admin.patch('/api/auth/users/' + user_id, json={'active': True})
        self.assertEqual(first.post('/api/auth/login', json={'username': 'reset_target', 'password': 'next78'}).status_code, 200)

    def test_password_reset_allows_admin_to_change_own_password(self):
        account_store.create_user('reset_admin', 'admin1', admin=True)
        client = TestClient(app)
        self.addCleanup(client.close)
        login = client.post('/api/auth/login', json={'username': 'reset_admin', 'password': 'admin1'})
        user_id = login.json()['user']['id']
        self.assertEqual(client.post('/api/auth/users/' + user_id + '/password', json={'password': 'admin2'}).status_code, 200)
        self.assertEqual(client.get('/api/auth/me').status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={'username': 'reset_admin', 'password': 'admin1'}).status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={'username': 'reset_admin', 'password': 'admin2'}).status_code, 200)

    def test_permanent_delete_requires_recycle_confirmation_and_owner(self):
        from app.utils.project_registry import load_project_paths
        for actor, suffix in ((self.worker, 'owner'), (self.admin, 'admin')):
            name = f'Permanent deletion {suffix}'
            project = self.worker.post('/api/projects', json={'name': name}).json()
            project_id = project['project_id']
            root = '/api/projects/' + project_id
            folder = video_service.project_path(project_id)
            (folder / 'masks').mkdir()
            (folder / 'masks/data.txt').write_text('test annotation data')
            payload = {'confirmation_name': name}
            self.assertEqual(actor.request('DELETE', root + '/permanent', json=payload).status_code, 400)
            self.assertTrue(folder.exists())
            self.assertEqual(self.worker.delete(root).status_code, 200)
            self.assertEqual(actor.request('DELETE', root + '/permanent', json={'confirmation_name': 'wrong'}).status_code, 400)
            self.assertTrue(folder.exists())
            response = actor.request('DELETE', root + '/permanent', json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(folder.exists())
            self.assertIsNone(account_store.project_record(project_id, include_deleted=True))
            self.assertNotIn(project_id, load_project_paths(video_service.projects_dir))
            self.assertEqual(self.worker.post(root + '/restore').status_code, 404)
        foreign = self.admin.post('/api/projects', json={'name': 'Protected other owner deletion'}).json()
        foreign_root = '/api/projects/' + foreign['project_id']
        self.admin.delete(foreign_root)
        self.assertEqual(self.worker.request('DELETE', foreign_root + '/permanent', json={'confirmation_name': foreign['name']}).status_code, 404)
        self.assertTrue(video_service.project_path(foreign['project_id']).exists())

    def test_permanent_delete_cleans_missing_project_index(self):
        import shutil
        from app.utils.project_registry import load_project_paths
        project = self.worker.post('/api/projects', json={'name': 'Permanent missing index'}).json()
        project_id = project['project_id']
        root = '/api/projects/' + project_id
        folder = video_service.project_path(project_id)
        shutil.rmtree(folder)
        self.assertEqual(self.worker.delete(root).status_code, 200)
        response = self.worker.request('DELETE', root + '/permanent', json={'confirmation_name': project['name']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(folder.exists())
        self.assertIsNone(account_store.project_record(project_id, include_deleted=True))
        self.assertNotIn(project_id, load_project_paths(video_service.projects_dir))

    def test_project_creation_rejects_duplicate_names(self):
        from app.utils.project_registry import registry_path
        name = 'Project unique name'
        created = self.worker.post('/api/projects', json={'name': f'  {name}  '})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['name'], name)
        before = registry_path(video_service.projects_dir).read_bytes()
        for duplicate in [name, f' {name} ', name.upper()]:
            response = self.worker.post('/api/projects', json={'name': duplicate})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn('同名', response.json()['detail'])
        self.assertEqual(registry_path(video_service.projects_dir).read_bytes(), before)
        self.assertEqual(self.worker.post('/api/projects', json={'name': '   '}).status_code, 422)
        # Names are private to the account, so another owner may use the same name.
        self.assertEqual(self.admin.post('/api/projects', json={'name': name}).status_code, 200)

    def test_project_creation_serializes_duplicate_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        barrier = threading.Barrier(2)
        def create():
            client = TestClient(app)
            client.cookies.update(self.worker.cookies)
            try:
                barrier.wait(timeout=5)
                return client.post('/api/projects', json={'name': 'Concurrent project'}).status_code
            finally:
                client.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(results), [200, 409])

    def test_revocation_and_session_scope(self):
        with account_store.connect() as db:
            row = db.execute('SELECT password FROM users WHERE username=?', ('worker',)).fetchone()
            self.assertNotEqual(row['password'], 'worker-password')
        sam_service._sessions['foreign'] = {'project_id': self.legacy['project_id']}
        with self.assertRaises(ValueError):
            sam_service.reset_session(self.project['project_id'], 'foreign')
        self.assertIn('foreign', sam_service._sessions)
        self.admin.patch('/api/auth/users/' + self.user_id, json={'active': False})
        self.assertEqual(self.worker.get('/api/projects').status_code, 401)
        self.assertEqual(self.worker.post('/api/auth/login', json={'username': 'worker', 'password': 'worker-password'}).status_code, 401)
        self.admin.patch('/api/auth/users/' + self.user_id, json={'active': True})
        self.worker.post('/api/auth/login', json={'username': 'worker', 'password': 'worker-password'})


if __name__ == '__main__':
    unittest.main()
