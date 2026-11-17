"""GPU scheduling tests use fake telemetry/workers and temporary lock files."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app.config import Settings
from app.services.gpu_resources import discover_gpus, GPUResourceError
from app.services.sam_pool import SAMPool, GPUCapacityError


class Process:
    def __init__(self):
        self.exited = False

    def poll(self):
        return 0 if self.exited else None

    def terminate(self):
        self.exited = True

    def wait(self, timeout=None):
        return 0


class Pool(SAMPool):
    """Keep real reservations and locking, substituting inference only."""
    def _start_reaper(self):
        pass

    def _spawn(self, lease):
        lease.process = Process()

    def _rpc(self, lease, operation, *args, **kwargs):
        if operation == 'start_video_session':
            return 'native-' + lease.session_id
        if operation == 'segment_frame':
            return [{'object_id': 3}]
        return []


class GPUPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = Settings(root, root, root, root / 'sam.pt', root / 'sam31.pt',
                               'sam3_multiplex_video', 'bfloat16', 'cuda:0', sam_gpu_lock_dir=str(root / 'locks'))
        self.devices = [{'id': f'GPU-{index}', 'index': index, 'label': f'GPU {index}',
                         'available': True, 'free_memory_mb': 24000} for index in range(2)]
        self.discovery = patch('app.services.sam_pool.discover_gpus', side_effect=lambda _: [dict(gpu) for gpu in self.devices])
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        self.pool = self.make_pool()

    def make_pool(self):
        pool = Pool(self.config, SimpleNamespace())
        self.addCleanup(pool.shutdown)
        return pool

    def start(self, owner='a', video='frames-a', project='project-a', pool=None):
        return (pool or self.pool).start_video_session(project, '', video, owner_id=owner)

    def test_startup_and_health_do_not_load_model(self):
        with patch('app.services.sam_service.SAMService.load_model', side_effect=AssertionError('CUDA initialized')):
            self.pool.load_model()
            self.assertEqual(len(self.pool.available_devices()), 2)
        self.assertIsNone(self.pool._model)
        self.assertEqual(self.pool._leases, {})

    def test_two_accounts_get_distinct_cards_third_is_rejected(self):
        a, b = self.start(), self.start('b', project='project-b')
        self.assertNotEqual(self.pool._leases[a].gpu['id'], self.pool._leases[b].gpu['id'])
        with self.assertRaises(GPUCapacityError):
            self.start('c')
        self.assertEqual(len(self.pool._leases), 2)
        self.assertEqual(sum(device['available'] for device in self.pool.available_devices()), 0)

    def test_account_reuses_session_and_new_video_only_replaces_its_own(self):
        a, b = self.start(), self.start('b', project='project-b')
        self.assertEqual(self.start(), a)
        old = self.pool._leases[a].process
        new = self.start(video='frames-new')
        self.assertNotEqual(new, a)
        self.assertTrue(old.exited)
        self.assertIn(b, self.pool._leases)
        self.assertEqual(len(self.pool._leases), 2)

    def test_busy_account_cannot_replace_close_or_expire_active_session(self):
        a = self.start()
        lease = self.pool._leases[a]
        lease.last_used = 0
        lease.lock.acquire()
        self.addCleanup(lease.lock.release)
        with self.assertRaises(GPUCapacityError):
            self.start(video='new')
        with self.assertRaises(GPUCapacityError):
            self.pool.close_session('project-a', a)
        self.pool.reap_idle()
        self.assertIn(a, self.pool._leases)

    def test_idle_release_releases_process_and_card(self):
        a = self.start()
        process = self.pool._leases[a].process
        self.pool._leases[a].last_used = time.monotonic() - 601
        self.pool.reap_idle()
        self.assertTrue(process.exited)
        self.assertIsNone(self.pool.find_video_session('project-a', 'frames-a'))
        self.assertEqual(len(self.pool._leases), 0)
        self.assertTrue(self.start('b'))

    def test_failed_load_and_failed_inference_release_reservation(self):
        with patch.object(self.pool, '_rpc', side_effect=RuntimeError('CUDA out of memory')):
            with self.assertRaises(RuntimeError):
                self.start()
        self.assertFalse(self.pool._leases)
        a = self.start()
        with patch.object(self.pool, '_rpc', side_effect=RuntimeError('failed refinement')):
            with self.assertRaises(RuntimeError):
                self.pool.segment_frame('project-a', a, frame_index=0)
        self.assertFalse(self.pool._leases)

    def test_locks_prevent_double_allocation_between_pool_instances(self):
        self.start()
        self.start('b')
        other = self.make_pool()
        with self.assertRaises(GPUCapacityError):
            self.start('c', pool=other)
        self.pool.shutdown()
        self.assertTrue(self.start('c', pool=other))

    def test_other_card_can_infer_while_first_card_is_busy(self):
        a, b = self.start(), self.start('b', project='project-b')
        lease = self.pool._leases[a]
        lease.lock.acquire()
        try:
            self.assertEqual(self.pool.segment_frame('project-b', b, frame_index=0), [{'object_id': 3}])
        finally:
            lease.lock.release()
        self.assertEqual(self.pool._leases[b].object_ids, [3])

    def test_wrong_project_and_owner_do_not_access_a_session(self):
        a = self.start()
        with self.assertRaises(ValueError):
            self.pool.segment_frame('other-project', a, frame_index=0)
        self.assertIsNone(self.pool.find_video_session('project-a', 'frames-a', owner_id='other-owner'))
        self.assertIsNotNone(self.pool.find_video_session('project-a', 'frames-a', owner_id='a'))
        self.assertIn(a, self.pool._leases)

    def test_concurrent_starts_reserve_distinct_gpus_before_loading(self):
        barrier = threading.Barrier(2)
        errors = []
        original = self.pool._rpc
        def load(lease, *args, **kwargs):
            barrier.wait(timeout=5)
            return original(lease, *args, **kwargs)
        def start(owner):
            try:
                self.start(owner)
            except Exception as exc:
                errors.append(exc)
        with patch.object(self.pool, '_rpc', side_effect=load):
            threads = [threading.Thread(target=start, args=(owner,)) for owner in ('a', 'b')]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=6)
        self.assertEqual(errors, [])
        self.assertEqual({lease.gpu['id'] for lease in self.pool._leases.values()}, {'GPU-0', 'GPU-1'})

    def test_driver_query_filters_external_processes_and_metrics(self):
        rows = ('0, GPU-a, RTX, 24000, 23900, 100, 0, Disabled\n'
                '1, GPU-b, RTX, 24000, 23900, 100, 0, Disabled\n'
                '2, GPU-c, RTX, 24000, 23900, 100, 95, Disabled\n'
                '3, GPU-d, RTX, 24000, 9000, 15000, 0, Disabled\n'
                '4, GPU-e, RTX, 24000, 23900, 100, 0, Enabled\n')
        def run(command, **kwargs):
            return SimpleNamespace(stdout='GPU-b, 1234\n' if 'compute-apps' in command[1] else rows)
        with patch('app.services.gpu_resources.subprocess.run', side_effect=run):
            devices = discover_gpus(self.config)
            self.assertEqual([gpu['id'] for gpu in devices if gpu['available']], ['GPU-a'])
            devices = discover_gpus(replace(self.config, sam_gpu_devices='1,GPU-c'))
            self.assertEqual([gpu['id'] for gpu in devices], ['GPU-b', 'GPU-c'])

    def test_unknown_driver_metrics_and_query_failure_fail_closed(self):
        with patch('app.services.gpu_resources.subprocess.run', return_value=SimpleNamespace(stdout='0, GPU-a, RTX, 24000, N/A, 0, N/A, Disabled\n')):
            self.assertEqual(discover_gpus(self.config), [])
        with patch('app.services.gpu_resources.subprocess.run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 5)):
            with self.assertRaises(GPUResourceError):
                discover_gpus(self.config)

    def test_admin_settings_persist_and_restore_without_changing_environment(self):
        from app.services.gpu_settings import GPUSettings
        values = GPUSettings.from_config(self.config).model_copy(update={
            'sam_gpu_devices': '0', 'sam_gpu_min_free_mb': 18000, 'sam_session_idle_seconds': 120})
        self.pool.update_admin_settings(values)
        restored = self.make_pool()
        self.assertEqual(restored.admin_settings(), values.model_dump())
        self.assertEqual(self.config.sam_gpu_min_free_mb, 12000)
        self.assertEqual(restored.config.sam_gpu_min_free_mb, 18000)

    def test_admin_can_update_policy_but_not_replace_backend_with_live_sessions(self):
        from app.services.gpu_settings import GPUSettings
        a = self.start()
        values = GPUSettings.from_config(self.config)
        changed = values.model_copy(update={'sam_gpu_devices': '1', 'sam_session_idle_seconds': 120})
        self.pool.update_admin_settings(changed)
        self.assertIn(a, self.pool._leases)
        with self.assertRaises(GPUCapacityError):
            self.pool.update_admin_settings(changed.model_copy(update={'sam_backend': 'mock'}))
        self.assertEqual(self.pool.backend_name(), 'sam3_multiplex_video')

    def test_failed_settings_write_leaves_live_policy_unchanged(self):
        from app.services.gpu_settings import GPUSettings
        before = self.pool.admin_settings()
        values = GPUSettings.from_config(self.config).model_copy(update={'sam_session_idle_seconds': 120})
        with patch('app.services.sam_pool.save_gpu_settings', side_effect=PermissionError('read only')):
            with self.assertRaises(PermissionError):
                self.pool.update_admin_settings(values)
        self.assertEqual(self.pool.admin_settings(), before)

    def test_admin_release_requires_explicit_force_for_busy_session(self):
        a, b = self.start(), self.start('b')
        lease = self.pool._leases[a]
        lease.lock.acquire()
        try:
            with self.assertRaises(GPUCapacityError):
                self.pool.admin_release_session(a)
            self.assertIn(a, self.pool._leases)
            self.pool.admin_release_session(a, force=True)
            self.assertTrue(lease.process.exited)
            self.assertNotIn(a, self.pool._leases)
            self.assertIn(b, self.pool._leases)
        finally:
            lease.lock.release()

    def test_admin_snapshot_includes_all_cards_and_owners(self):
        from app.services.gpu_settings import GPUSettings
        a = self.start()
        self.pool.update_admin_settings(GPUSettings.from_config(self.config).model_copy(update={'sam_gpu_devices': '0'}))
        snapshot = self.pool.admin_snapshot()
        self.assertEqual(len(snapshot['devices']), 2)
        self.assertTrue(snapshot['devices'][0]['allowed'])
        self.assertFalse(snapshot['devices'][1]['allowed'])
        self.assertEqual(snapshot['sessions'][0]['owner_id'], 'a')
        self.assertEqual(snapshot['sessions'][0]['session_id'], a)

    def test_admin_force_release_during_load_does_not_return_stale_session(self):
        def load(lease, *args, **kwargs):
            self.pool.admin_release_session(lease.session_id, force=True)
            return 'native-removed'
        with patch.object(self.pool, '_rpc', side_effect=load):
            with self.assertRaisesRegex(RuntimeError, '管理员释放'):
                self.start()
        self.assertFalse(self.pool._leases)

    def test_settings_validation_rejects_unknown_keys_and_invalid_numbers(self):
        from app.services.gpu_settings import GPUSettings
        from pydantic import ValidationError
        values = GPUSettings.from_config(self.config).model_dump()
        for overrides in ({'sam_gpu_max_utilization': 101}, {'sam_session_idle_seconds': 0},
                          {'sam_gpu_pool': 'true'}, {'sam_gpu_devices': '../../data'},
                          {'sam_gpu_lock_dir': '/tmp/other'}, {'sam_gpu_min_free_mb': 1.5}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                GPUSettings(**(values | overrides))
        self.assertEqual(GPUSettings(**(values | {'sam_gpu_devices': '0, 2,0'})).sam_gpu_devices, '0,2')


class WorkerProtocolTests(unittest.TestCase):
    def test_stream_cancel_is_scoped_to_request_and_next_operation_succeeds(self):
        from multiprocessing import Pipe
        from app.services.sam_worker import serve
        parent, child = Pipe()
        cancel_parent, cancel_child = Pipe()
        seen = []
        class Service:
            def backend_name(self):
                return 'sam3_video'
            def propagate_in_video(self, on_frame, should_cancel):
                for frame in range(50):
                    if should_cancel():
                        break
                    on_frame({'frame_index': frame, 'objects': []})
                    time.sleep(0.005)
                return []
            def reset_session(self):
                seen.append('reset')
        thread = threading.Thread(target=serve, args=(child, cancel_child, Service()), daemon=True)
        thread.start()
        parent.send({'operation': 'propagate_in_video', 'request_id': 'first'})
        self.assertTrue(parent.poll(2))
        self.assertEqual(parent.recv()['type'], 'frame')
        cancel_parent.send('first')
        count = 1
        while True:
            self.assertTrue(parent.poll(2))
            message = parent.recv()
            if message['type'] == 'result':
                break
            count += 1
        self.assertLess(count, 50)
        parent.send({'operation': 'reset_session', 'request_id': 'second'})
        self.assertTrue(parent.poll(2))
        self.assertEqual(parent.recv()['type'], 'result')
        self.assertEqual(seen, ['reset'])
        parent.close()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        cancel_parent.close()

    def test_actual_subprocess_has_only_assigned_gpu_and_can_be_released(self):
        # Exercise the real Popen/pass_fds/IPC path, replacing only model code.
        import os
        import sys
        script = '''
import os, sys
from multiprocessing.connection import Connection
c = Connection(int(sys.argv[1]))
cancel = Connection(int(sys.argv[2]))
config = c.recv()['config']
r = c.recv()
assert os.environ['CUDA_VISIBLE_DEVICES'] == 'GPU-test'
assert os.environ['SAM_DEVICE'] == 'cuda:0'
c.send({'type': 'result', 'value': 'native-test', 'backend': 'sam3_video'})
while True:
    r = c.recv()
'''
        with tempfile.TemporaryDirectory() as root:
            config = Settings(Path(root), Path(root), Path(root), Path(root), Path(root),
                              'sam3_video', 'bfloat16', 'cuda:0', sam_gpu_lock_dir=str(Path(root) / 'locks'))
            pool = SAMPool(config, SimpleNamespace())
            self.addCleanup(pool.shutdown)
            gpu = {'id': 'GPU-test', 'index': 0, 'label': 'Test GPU', 'available': True, 'free_memory_mb': 24000}
            popen = subprocess.Popen
            def fake_model(command, **kwargs):
                return popen([sys.executable, '-c', script, *command[-2:]], **kwargs)
            with patch('app.services.sam_pool.discover_gpus', return_value=[gpu]), patch('app.services.sam_pool.subprocess.Popen', side_effect=fake_model):
                session_id = pool.start_video_session('project', '', 'frames', owner_id='owner')
            lease = pool._leases[session_id]
            self.assertEqual(lease.native_id, 'native-test')
            self.assertIsNone(lease.process.poll())
            self.assertIsNone(pool._model)
            process = lease.process
            pool.close_session('project', session_id)
            self.assertIsNotNone(process.poll())
            self.assertEqual(pool._leases, {})
