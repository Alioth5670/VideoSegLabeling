"""Bounded export queue. CPU and archive work runs in a fresh Python process."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from app.utils.project_registry import project_root

FORMATS = {'project_json', 'mask_png', 'coco_video_json', 'all_videos_zip'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def write_status(path: Path, data: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class ExportJobs:
    def __init__(self, projects_dir: Path, max_pending: int = 8):
        self.projects_dir = projects_dir.resolve()
        self.max_pending = max_pending
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='export-coordinator')
        self._lock = threading.RLock()
        self._jobs: dict[str, tuple[str, Path]] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._closed = False

    def submit(self, project_id: str, export_format: str, video_id: str | None = None) -> dict:
        with self._lock:
            return self._submit(project_id, export_format, video_id)

    def _submit(self, project_id: str, export_format: str, video_id: str | None = None) -> dict:
        if export_format not in FORMATS:
            raise ValueError('Unsupported export format')
        root = project_root(self.projects_dir, project_id)
        project = json.loads((root / 'project.json').read_text(encoding='utf-8'))
        if video_id:
            if not any(v.get('video_id') == video_id for v in project.get('videos', [])):
                raise ValueError('Video not found')
            project['active_video_id'] = video_id
            video = next(v for v in project['videos'] if v['video_id'] == video_id)
            for field in ('video_path', 'frames_dir', 'fps', 'width', 'height', 'frame_count', 'duration'):
                project[field] = video.get(field)
        video_id = project.get('active_video_id')
        with self._lock:
            if self._closed:
                raise RuntimeError('Export service is shutting down')
            pending = 0
            for existing_project, path in self._jobs.values():
                if not path.exists():
                    continue
                status = json.loads(path.read_text(encoding='utf-8'))
                if status['status'] in TERMINAL:
                    continue
                pending += 1
                if existing_project == project_id and status['format'] == export_format and status['video_id'] == video_id:
                    return status
            if pending >= self.max_pending:
                raise RuntimeError('Export queue is full; retry after a task finishes')
            job_id = uuid.uuid4().hex
            folder = root / 'exports' / 'jobs'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{job_id}.json'
            task = {'job_id': job_id, 'project_id': project_id, 'format': export_format,
                    'video_id': video_id, 'status': 'queued', 'progress': 0,
                    'stage': '等待导出', 'created_at': time.time(), 'download_url': None,
                    'error': None}
            write_status(path, task)
            spec = path.with_suffix('.task.json')
            spec.write_text(json.dumps({'projects_dir': str(self.projects_dir), 'project': project,
                                        'status_path': str(path), 'format': export_format}), encoding='utf-8')
            if len(self._jobs) >= 200:
                for old_id, (_, old_path) in list(self._jobs.items()):
                    if not old_path.exists() or json.loads(old_path.read_text(encoding='utf-8'))['status'] in TERMINAL:
                        self._jobs.pop(old_id)
                        if len(self._jobs) < 200:
                            break
            self._jobs[job_id] = (project_id, path)
            self._executor.submit(self._run, job_id, path, spec)
            return task

    def get(self, project_id: str, job_id: str) -> dict:
        if not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise FileNotFoundError(job_id)
        path = project_root(self.projects_dir, project_id) / 'exports' / 'jobs' / f'{job_id}.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['project_id'] != project_id:
            raise FileNotFoundError(job_id)
        # A restarted backend cannot resume an interrupted coordinator task.
        with self._lock:
            known = job_id in self._jobs
        if not known and data['status'] not in TERMINAL:
            data.update(status='failed', error='后端已重启，请重新导出', stage='任务已中断')
        return data

    def _run(self, job_id: str, path: Path, spec: Path) -> None:
        try:
            with self._lock:
                if self._closed or job_id not in self._jobs:
                    return
                backend = Path(__file__).resolve().parents[2]
                log = path.with_suffix('.log')
                with log.open('wb') as errors:
                    process = subprocess.Popen([sys.executable, '-m', 'app.services.export_worker', str(spec)],
                                               cwd=backend, stdout=subprocess.DEVNULL, stderr=errors,
                                               env={**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
                self._processes[job_id] = process
            code = process.wait()
            with self._lock:
                if self._closed:
                    return
            status = json.loads(path.read_text(encoding='utf-8'))
            if code != 0 or status['status'] not in TERMINAL:
                status.update(status='failed', stage='导出失败', error='导出子进程异常退出，请重试')
                write_status(path, status)
        except Exception as exc:
            if path.exists():
                status = json.loads(path.read_text(encoding='utf-8'))
                status.update(status='failed', stage='导出失败', error=str(exc))
                write_status(path, status)
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
            spec.unlink(missing_ok=True)

    @contextmanager
    def project_deletion(self, project_id: str):
        with self._lock:
            matching = [(job_id, path) for job_id, (owner, path) in self._jobs.items() if owner == project_id]
            for job_id, path in matching:
                if job_id in self._processes:
                    raise RuntimeError('项目仍有导出任务，请等待导出结束后再彻底删除')
                if path.exists() and json.loads(path.read_text(encoding='utf-8'))['status'] not in TERMINAL:
                    raise RuntimeError('项目仍有导出任务，请等待导出结束后再彻底删除')
            yield
            for job_id, _ in matching:
                self._jobs.pop(job_id, None)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        self._executor.shutdown(wait=True, cancel_futures=True)
        for _, path in self._jobs.values():
            path.with_suffix('.task.json').unlink(missing_ok=True)
            if not path.exists():
                continue
            status = json.loads(path.read_text(encoding='utf-8'))
            if status['status'] not in TERMINAL:
                status.update(status='cancelled', stage='任务已中断', error='后端已停止，请重新导出')
                write_status(path, status)
