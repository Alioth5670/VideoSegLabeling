import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.services.annotation_store import AnnotationStore
from app.services.export_jobs import ExportJobs
from app.services.export_service import ExportService


class ExportJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'p'
        self.project.mkdir()
        self.meta = {'project_id': 'p', 'name': 'test', 'videos': [], 'active_video_id': None}
        (self.project / 'project.json').write_text(json.dumps(self.meta))
        self.store = AnnotationStore(self.root)
        self.store.ensure_object('p', 1, 'test')
        for frame in range(5):
            annotation = {'object_id': 1, 'track_id': 1, 'frame_index': frame,
                          'mask_path': f'masks/object_1/{frame:06d}.png', 'bbox': [0, 0, 8, 8], 'area': 64}
            self.store.save_frame_object('p', frame, annotation, True)
            mask = self.project / annotation['mask_path']
            mask.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.ones((8, 8), dtype=np.uint8) * 255).save(mask)
        self.jobs = ExportJobs(self.root)
        self.addCleanup(self.jobs.shutdown)

    def wait_for_job(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = self.jobs.get('p', job_id)
            if status['status'] in {'completed', 'failed', 'cancelled'}:
                return status
            time.sleep(.03)
        self.fail('Background export timed out')

    def test_export_runs_in_separate_process_and_persists_result(self):
        pids = []
        real_launch = subprocess.Popen
        def launch(*args, **kwargs):
            process = real_launch(*args, **kwargs)
            pids.append(process.pid)
            return process
        with patch('app.services.export_jobs.subprocess.Popen', side_effect=launch):
            created = self.jobs.submit('p', 'coco_video_json')
            self.assertEqual(created['status'], 'queued')
            status = self.wait_for_job(created['job_id'])
        self.assertEqual(status['status'], 'completed', status)
        self.assertEqual(status['progress'], 100)
        self.assertEqual(len(pids), 1)
        self.assertNotEqual(pids[0], os.getpid())
        path = self.project / status['download_url'].split('/download/')[1]
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(len(json.loads(archive.read('coco_video.json'))['annotations']), 5)
        # A new coordinator can still read a completed job after a page/server restart.
        reader = ExportJobs(self.root)
        try:
            self.assertEqual(reader.get('p', created['job_id'])['download_url'], status['download_url'])
        finally:
            reader.shutdown()
        with self.assertRaises(FileNotFoundError):
            self.jobs.get('p', '../other')
        with self.assertRaises(FileNotFoundError):
            self.jobs.get('other', created['job_id'])

    def test_queue_is_bounded_and_duplicate_submission_reuses_job(self):
        self.jobs.max_pending = 1
        release = threading.Event()
        def blocked(*args):
            release.wait(5)
        try:
            with patch.object(self.jobs, '_run', side_effect=blocked):
                first = self.jobs.submit('p', 'mask_png')
                duplicate = self.jobs.submit('p', 'mask_png')
                self.assertEqual(duplicate['job_id'], first['job_id'])
                self.assertEqual(self.jobs.get('p', first['job_id'])['status'], 'queued')
                with self.assertRaisesRegex(RuntimeError, 'queue is full'):
                    self.jobs.submit('p', 'project_json')
        finally:
            release.set()

    def test_failure_has_message_without_download_url(self):
        (self.project / 'masks/object_1/000000.png').unlink()
        job = self.jobs.submit('p', 'coco_video_json')
        status = self.wait_for_job(job['job_id'])
        self.assertEqual(status['status'], 'failed')
        self.assertTrue(status['error'])
        self.assertIsNone(status['download_url'])
        self.assertLess(status['progress'], 100)

    def test_progress_reports_work_and_keeps_submitted_video(self):
        videos = [{'video_id': name, 'storage_dir': f'videos/{name}', 'name': name} for name in ('first', 'second')]
        self.meta.update(videos=videos, active_video_id='first')
        (self.project / 'project.json').write_text(json.dumps(self.meta))
        self.store.ensure_object('p', 1, 'first', video_id='first')
        self.store.ensure_object('p', 2, 'second', video_id='second')
        submitted = dict(self.meta)
        self.meta['active_video_id'] = 'second'
        (self.project / 'project.json').write_text(json.dumps(self.meta))
        reports = []
        output = ExportService(self.root).export('p', 'project_json', project_snapshot=submitted,
            progress=lambda value, stage: reports.append((value, stage)))
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(json.loads(archive.read('project.json'))['active_video_id'], 'first')
            self.assertEqual(list(json.loads(archive.read('annotations.json'))['objects']), ['1'])
        self.assertGreater(len(reports), 3)
        self.assertEqual([v for v, _ in reports], sorted(v for v, _ in reports))
        self.assertTrue(all(value < 100 for value, _ in reports))

    def test_interrupted_job_is_reported_after_restart(self):
        release = threading.Event()
        try:
            with patch.object(self.jobs, '_run', side_effect=lambda *args: release.wait(5)):
                task = self.jobs.submit('p', 'mask_png')
                restarted = ExportJobs(self.root)
                try:
                    status = restarted.get('p', task['job_id'])
                    self.assertEqual(status['status'], 'failed')
                    self.assertIn('重启', status['error'])
                finally:
                    restarted.shutdown()
        finally:
            release.set()

    def test_pending_exports_block_permanent_deletion(self):
        release = threading.Event()
        try:
            with patch.object(self.jobs, '_run', side_effect=lambda *args: release.wait(5)):
                self.jobs.submit('p', 'mask_png')
                with self.assertRaisesRegex(RuntimeError, '导出任务'):
                    with self.jobs.project_deletion('p'):
                        self.fail('Deletion guard allowed a queued export')
        finally:
            release.set()

    def test_deleted_projects_do_not_break_future_export_jobs(self):
        import shutil
        task = self.jobs.submit('p', 'project_json')
        self.assertEqual(self.wait_for_job(task['job_id'])['status'], 'completed')
        self.jobs._executor.submit(lambda: None).result(timeout=5)
        with self.jobs.project_deletion('p'):
            shutil.rmtree(self.project)
        self.assertNotIn(task['job_id'], self.jobs._jobs)
        other = self.root / 'q'
        other.mkdir()
        (other / 'project.json').write_text(json.dumps({'project_id': 'q', 'name': 'Other project', 'videos': []}))
        next_job = self.jobs.submit('q', 'project_json')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = self.jobs.get('q', next_job['job_id'])
            if status['status'] in {'completed', 'failed'}:
                break
            time.sleep(.03)
        self.assertEqual(status['status'], 'completed', status)
