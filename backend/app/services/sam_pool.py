"""One account / one session / one isolated GPU process, allocated on demand."""
import fcntl
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from multiprocessing import Pipe
from pathlib import Path
from typing import Any

from app.services.gpu_resources import discover_gpus, GPUResourceError
from app.services.sam_service import SAMService
from app.services.gpu_settings import GPUSettings, load_gpu_settings, save_gpu_settings

logger = logging.getLogger(__name__)


class GPUCapacityError(RuntimeError):
    pass


@dataclass
class Lease:
    session_id: str
    owner_id: str
    project_id: str
    frames_dir: str
    gpu: dict
    file_lock: Any
    lock: Any = field(default_factory=threading.Lock)
    process: Any = None
    connection: Any = None
    cancel: Any = None
    native_id: str | None = None
    object_ids: list[int] = field(default_factory=list)
    backend: str = ''
    last_used: float = field(default_factory=time.monotonic)


class SAMPool(SAMService):
    def __init__(self, config, store):
        self._settings_path = config.projects_dir / '.gpu-settings.json'
        values = load_gpu_settings(self._settings_path, config)
        config = replace(config, **values.model_dump())
        super().__init__(config, store)
        self._pool_lock = threading.RLock()
        self._leases: dict[str, Lease] = {}
        self._stopping = threading.Event()
        self._reaper = None

    def admin_settings(self) -> dict:
        with self._pool_lock:
            return GPUSettings.from_config(replace(self.config, sam_backend=self._active_backend)).model_dump()

    def update_admin_settings(self, values: GPUSettings) -> dict:
        with self._pool_lock:
            changed_mode = (values.sam_gpu_pool != self.config.sam_gpu_pool or
                            values.sam_backend != self._active_backend)
            if changed_mode and (self._leases or self._sessions):
                raise GPUCapacityError('切换模型或 GPU 池模式前，请先释放全部 session。')
            if changed_mode and self._model is not None:
                raise GPUCapacityError('旧模式已在主进程加载模型，请先重启后端，再切换 GPU 池模式。')
            if not self._inference_lock.acquire(blocking=False):
                raise GPUCapacityError('模型正在推理，请稍后保存配置。')
            try:
                # Persist first: a write failure must leave live settings unchanged.
                save_gpu_settings(self._settings_path, values)
                self.config = replace(self.config, **values.model_dump())
                self._active_backend = values.sam_backend
                self._fallback_error = None
            finally:
                self._inference_lock.release()
            return self.admin_settings()

    def admin_snapshot(self) -> dict:
        with self._pool_lock:
            config = self.config
            sessions = [{
                'session_id': lease.session_id, 'owner_id': lease.owner_id,
                'project_id': lease.project_id, 'gpu_id': lease.gpu['id'], 'device': lease.gpu['label'],
                'backend': lease.backend, 'busy': lease.lock.locked(), 'ready': lease.native_id is not None,
                'idle_seconds': max(0, int(time.monotonic() - lease.last_used)),
            } for lease in self._leases.values()]
            sessions.extend({
                'session_id': session_id, 'owner_id': session.get('owner_id', ''),
                'project_id': session['project_id'], 'gpu_id': 'legacy',
                'device': '模拟模式（不占用 GPU）' if self._active_backend == 'mock' else self._active_device,
                'backend': self._active_backend, 'busy': False, 'ready': True, 'idle_seconds': 0,
            } for session_id, session in list(self._sessions.items()))
            values = self.admin_settings()
        error = None
        try:
            devices = discover_gpus(replace(config, sam_gpu_devices=''))
        except GPUResourceError as exc:
            devices, error = [], str(exc)
        allowed = {part for part in config.sam_gpu_devices.split(',') if part}
        occupied = {session['gpu_id'] for session in sessions}
        for gpu in devices:
            gpu['allowed'] = not allowed or str(gpu['index']) in allowed or gpu['id'] in allowed
            gpu['reserved'] = gpu['id'] in occupied
            gpu['available'] = gpu['available'] and gpu['allowed'] and not gpu['reserved']
        return {'settings': values, 'devices': devices, 'sessions': sessions, 'discovery_error': error}

    def admin_release_session(self, session_id: str, *, force: bool = False):
        with self._pool_lock:
            lease = self._leases.get(session_id)
            if lease is None:
                session = self._sessions.get(session_id)
                if session is None:
                    raise ValueError('Session 已释放，请刷新列表。')
                try:
                    self.close_session(session['project_id'], session_id)
                except RuntimeError as exc:
                    raise GPUCapacityError(str(exc)) from exc
                return
            acquired = lease.lock.acquire(blocking=False)
            if not acquired and not force:
                raise GPUCapacityError('此 session 正在加载或推理；如需中止，请使用强制释放。')
            try:
                self._dispose(lease)
            finally:
                if acquired:
                    lease.lock.release()

    def _pooled(self):
        return self.config.sam_gpu_pool and self._active_backend != 'mock'

    def device_name(self):
        return '自动分配 GPU' if self._pooled() else super().device_name()

    def load_model(self):
        # Parent never imports/initializes CUDA in pool mode.
        if not self._pooled():
            return super().load_model()

    def available_devices(self):
        if self._active_backend == 'mock':
            return [{'id': 'cpu', 'label': 'Mock · 不占用 GPU', 'available': True}]
        if not self._pooled():
            return super().available_devices()
        try:
            devices = discover_gpus(self.config)
        except GPUResourceError as exc:
            return [{'id': 'auto', 'label': str(exc), 'available': False}]
        with self._pool_lock:
            reserved = {lease.gpu['id'] for lease in self._leases.values()}
        for device in devices:
            device['available'] = device['available'] and device['id'] not in reserved
            device['reserved'] = device['id'] in reserved
        return devices

    def set_device(self, device):
        if self._pooled():
            raise ValueError('GPU 池自动分配设备，请通过 SAM_GPU_DEVICES 配置可用显卡。')
        return super().set_device(device)

    def set_backend(self, backend):
        with self._pool_lock:
            if self._leases:
                raise ValueError('仍有账户占用 GPU session，请先释放后再切换模型。')
            return super().set_backend(backend)

    def _start_reaper(self):
        if self._reaper is None:
            self._reaper = threading.Thread(target=self._reap_loop, daemon=True, name='sam-idle-reaper')
            self._reaper.start()

    def _reap_loop(self):
        while not self._stopping.wait(15):
            self.reap_idle()

    def reap_idle(self):
        with self._pool_lock:
            for lease in list(self._leases.values()):
                expired = time.monotonic() - lease.last_used >= self.config.sam_session_idle_seconds
                dead = lease.process is not None and lease.process.poll() is not None
                if (expired or dead) and lease.lock.acquire(blocking=False):
                    try:
                        self._dispose(lease)
                    finally:
                        lease.lock.release()

    def _dispose(self, lease):
        # Pool lock is held; normal calls also hold the lease lock. Shutdown
        # may interrupt inference. Free the reservation only after process exit.
        process = lease.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for connection in (lease.connection, lease.cancel):
            if connection is not None:
                connection.close()
        lease.file_lock.close()
        removed = self._leases.pop(lease.session_id, None)
        if removed is not None:
            logger.info('Released SAM GPU session=%s device=%s', lease.session_id, lease.gpu['id'])

    def _reserve_gpu(self):
        reserved = {lease.gpu['id'] for lease in self._leases.values()}
        directory = Path(self.config.sam_gpu_lock_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for gpu in sorted(discover_gpus(self.config), key=lambda row: (-row['free_memory_mb'], row['index'])):
            if not gpu['available'] or gpu['id'] in reserved:
                continue
            handle = (directory / (gpu['id'] + '.lock')).open('a')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            return gpu, handle
        raise GPUCapacityError('暂无空闲 GPU，请稍后重试或释放自己的 session；不会抢占其他用户的任务。')

    def _spawn(self, lease):
        parent, child = Pipe(duplex=True)
        cancel_parent, cancel_child = Pipe(duplex=True)
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': lease.gpu['id'], 'SAM_DEVICE': 'cuda:0',
               'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
               'RANK': '0', 'LOCAL_RANK': '0', 'WORLD_SIZE': '1', 'IS_MAIN_PROCESS': '1',
               'VSL_PARENT_PID': str(os.getpid())}
        backend = str(Path(__file__).resolve().parents[2])
        env['PYTHONPATH'] = backend + os.pathsep + env.get('PYTHONPATH', '')
        try:
            lease.process = subprocess.Popen(
                [sys.executable, '-m', 'app.services.sam_worker', str(child.fileno()), str(cancel_child.fileno())],
                env=env, pass_fds=(child.fileno(), cancel_child.fileno()), cwd=backend)
            lease.connection, lease.cancel = parent, cancel_parent
            parent.send({'config': self.config})
        except BaseException:
            parent.close()
            cancel_parent.close()
            raise
        finally:
            child.close()
            cancel_child.close()

    def _rpc(self, lease, operation, *args, on_frame=None, should_cancel=None, **kwargs):
        request_id = uuid.uuid4().hex
        lease.connection.send({'operation': operation, 'args': args, 'kwargs': kwargs, 'request_id': request_id})
        deadline = time.monotonic() + self.config.sam_worker_timeout_seconds
        sent_cancel = False
        while True:
            if should_cancel and should_cancel() and not sent_cancel:
                lease.cancel.send(request_id)
                sent_cancel = True
            if not lease.connection.poll(0.2):
                if lease.process.poll() is not None:
                    raise RuntimeError('GPU 推理进程已退出，请重新启动 session。')
                if time.monotonic() > deadline:
                    raise RuntimeError('GPU 推理进程响应超时，已释放 session，请重新启动。')
                continue
            message = lease.connection.recv()
            deadline = time.monotonic() + self.config.sam_worker_timeout_seconds
            if message['type'] == 'frame':
                if on_frame:
                    on_frame(message['value'])
            elif message['type'] == 'error':
                raise RuntimeError(message['detail'])
            else:
                lease.backend = message['backend']
                return message['value']

    def start_video_session(self, project_id, video_path, frames_dir, owner_id=None):
        if not self._pooled():
            session_id = super().start_video_session(project_id, video_path, frames_dir)
            self._sessions[session_id]['owner_id'] = owner_id or project_id
            return session_id
        owner_id = owner_id or project_id
        with self._pool_lock:
            if self._stopping.is_set():
                raise RuntimeError('服务正在停止')
            for old in list(self._leases.values()):
                if old.owner_id != owner_id:
                    continue
                if old.project_id == project_id and old.frames_dir == frames_dir and old.native_id and old.process.poll() is None:
                    old.last_used = time.monotonic()
                    return old.session_id
                if not old.lock.acquire(blocking=False):
                    raise GPUCapacityError('当前账户正在推理，请先停止任务再启动其他视频。')
                try:
                    self._dispose(old)
                finally:
                    old.lock.release()
            gpu, handle = self._reserve_gpu()
            lease = Lease(uuid.uuid4().hex, owner_id, project_id, frames_dir, gpu, handle, backend=self._active_backend)
            lease.lock.acquire()
            self._leases[lease.session_id] = lease
            self._start_reaper()
        try:
            with self._pool_lock:
                if self._stopping.is_set():
                    raise RuntimeError('服务正在停止')
                if self._leases.get(lease.session_id) is not lease:
                    raise RuntimeError('Session 已由管理员释放')
                self._spawn(lease)
            native_id = self._rpc(lease, 'start_video_session', project_id, video_path, frames_dir)
            with self._pool_lock:
                if self._leases.get(lease.session_id) is not lease:
                    raise RuntimeError('Session 已由管理员释放')
                lease.native_id = native_id
                lease.last_used = time.monotonic()
                return lease.session_id
        except BaseException:
            with self._pool_lock:
                self._dispose(lease)
            raise
        finally:
            lease.lock.release()

    def find_video_session(self, project_id, frames_dir, owner_id=None):
        if not self._pooled():
            return super().find_video_session(project_id, frames_dir)
        with self._pool_lock:
            for lease in self._leases.values():
                if (lease.project_id == project_id and lease.frames_dir == frames_dir and lease.native_id and
                        (owner_id is None or lease.owner_id == owner_id) and lease.process.poll() is None):
                    return {'session_id': lease.session_id, 'object_ids': list(lease.object_ids),
                            'device': lease.gpu['label'], 'backend': lease.backend}
        return None

    def check_video_session(self, project_id, session_id, frames_dir):
        if not self._pooled():
            return super().check_video_session(project_id, session_id, frames_dir)
        with self._pool_lock:
            lease = self._leases.get(session_id)
            if not lease or lease.project_id != project_id or lease.frames_dir != frames_dir:
                raise ValueError('Session 已释放或不属于此视频，请重新启动 session。')

    @contextmanager
    def _operation(self, project_id, session_id):
        with self._pool_lock:
            lease = self._leases.get(session_id)
            if lease is None or lease.project_id != project_id:
                raise ValueError('Session 已释放或不属于此项目，请重新启动 session。')
            if not lease.lock.acquire(blocking=False):
                raise GPUCapacityError('此 session 正在推理，请等待或停止传播。')
        try:
            yield lease
        except BaseException:
            # A failed refinement may leave model state partially mutated.
            with self._pool_lock:
                self._dispose(lease)
            raise
        finally:
            lease.last_used = time.monotonic()
            lease.lock.release()

    def segment_frame(self, project_id, session_id, **kwargs):
        if not self._pooled():
            return super().segment_frame(project_id, session_id, **kwargs)
        with self._operation(project_id, session_id) as lease:
            results = self._rpc(lease, 'segment_frame', project_id, lease.native_id, **kwargs)
            lease.object_ids = sorted(set(lease.object_ids) | {int(item['object_id']) for item in results})
            return results

    def propagate_in_video(self, project_id, session_id, object_ids, start_frame, end_frame, direction,
                           video_id=None, on_frame=None, should_cancel=None):
        if not self._pooled():
            return super().propagate_in_video(project_id, session_id, object_ids, start_frame, end_frame,
                                              direction, video_id, on_frame, should_cancel)
        with self._operation(project_id, session_id) as lease:
            return self._rpc(lease, 'propagate_in_video', project_id, lease.native_id, object_ids,
                             start_frame, end_frame, direction, video_id, on_frame=on_frame, should_cancel=should_cancel)

    def remove_object(self, project_id, session_id, object_id):
        if not self._pooled():
            return super().remove_object(project_id, session_id, object_id)
        with self._operation(project_id, session_id) as lease:
            self._rpc(lease, 'remove_object', project_id, lease.native_id, object_id)
            lease.object_ids = [value for value in lease.object_ids if value != object_id]

    def reset_session(self, project_id, session_id):
        if not self._pooled():
            return super().reset_session(project_id, session_id)
        with self._operation(project_id, session_id) as lease:
            self._rpc(lease, 'reset_session', project_id, lease.native_id)
            lease.object_ids = []

    def close_session(self, project_id, session_id):
        if not self._pooled():
            return super().close_session(project_id, session_id)
        with self._pool_lock:
            lease = self._leases.get(session_id)
            if lease is None:
                return
            if lease.project_id != project_id:
                raise ValueError('Session does not belong to this project')
            if not lease.lock.acquire(blocking=False):
                raise GPUCapacityError('请先停止当前传播，再释放 GPU。')
            try:
                self._dispose(lease)
            finally:
                lease.lock.release()

    def close_project_sessions(self, project_id):
        if not self._pooled():
            return super().close_project_sessions(project_id)
        with self._pool_lock:
            leases = [lease for lease in self._leases.values() if lease.project_id == project_id]
            locked = []
            try:
                for lease in leases:
                    if not lease.lock.acquire(blocking=False):
                        raise GPUCapacityError('项目仍在推理，请先停止任务。')
                    locked.append(lease)
                for lease in leases:
                    self._dispose(lease)
            finally:
                for lease in locked:
                    lease.lock.release()

    def shutdown(self):
        self._stopping.set()
        with self._pool_lock:
            # Shutdown can interrupt inference; parent operations will fail cleanly.
            for lease in list(self._leases.values()):
                self._dispose(lease)
