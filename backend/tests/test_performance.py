import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.config import Settings
from app.services.annotation_store import AnnotationStore
from app.services.export_service import ExportService
from app.services.frame_loader import LazyFrameLoader
from app.services.sam_service import SAMService
from app.utils.rle import encode_rle


# This module-level source is substituted by SAMService only during init_state.
def load_resource_as_video_frames(**kwargs):
    raise AssertionError('Eager loader must not be called')


class FakeModel:
    image_size = 16
    image_mean = (0.5, 0.5, 0.5)
    image_std = (0.5, 0.5, 0.5)

    def init_state(self, resource_path, offload_video_to_cpu, async_loading_frames, offload_state_to_cpu=False):
        images, height, width = load_resource_as_video_frames(resource_path=resource_path)
        self.loader = images
        self.offloaded = offload_state_to_cpu
        return {'feature_cache': {}, 'images': images}


class FakePredictor:
    def __init__(self):
        self.model = FakeModel()
        self._all_inference_states = {}
        self.closed = []

    def handle_request(self, request):
        if request['type'] == 'close_session':
            self.closed.append(request['session_id'])
            self._all_inference_states.pop(request['session_id'], None)
        elif request['type'] == 'reset_session':
            self._all_inference_states[request['session_id']]['state']['feature_cache'].clear()
        return {}


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'p'
        self.project.mkdir()
        self.meta = {'project_id': 'p', 'name': 'test', 'videos': [], 'active_video_id': None,
                     'width': 24, 'height': 20, 'frame_count': 3}
        (self.project / 'project.json').write_text(json.dumps(self.meta))
        self.store = AnnotationStore(self.root)

    def annotation(self, frame=0, object_id=1):
        return {'object_id': object_id, 'track_id': object_id, 'frame_index': frame,
                'mask_path': f'masks/object_{object_id}/{frame:06d}.png',
                'bbox': [0, 0, 4, 4], 'area': 16, 'is_keyframe': True}

    def test_legacy_migration_incremental_writes_and_restart(self):
        legacy = {'project_id': 'p', 'objects': {'1': {'object_id': 1, 'category': 'old'}},
                  'frames': {'0': {'objects': {'1': {**self.annotation(), 'locked': True}}}},
                  'keyframes': [{'frame_index': 0, 'object_id': 1}], 'prompts': []}
        source = self.project / 'annotations.json'
        source.write_text(json.dumps(legacy))
        original = source.read_bytes()
        self.assertEqual(self.store.load('p')['objects']['1']['category'], 'old')
        with patch.object(self.store, 'load', side_effect=AssertionError('Hot path loaded full snapshot')):
            self.store.ensure_object('p', 1, 'changed')
            self.store.save_frame_object('p', 0, self.annotation(), True)
            self.store.save_frame_objects('p', 9, [self.annotation(9), self.annotation(9, 2)], False)
            self.store.add_prompt('p', {'frame_index': 9})
            self.assertTrue(self.store.frame_annotations('p', 0)['objects']['1']['locked'])
            self.assertEqual(self.store.nearest_object_mask('p', 1, 8)[0], 9)
        restarted = AnnotationStore(self.root)
        result = restarted.load('p')
        self.assertEqual(result['objects']['1']['category'], 'changed')
        self.assertEqual(restarted.summary('p')['annotated_frames'], [0, 9])
        self.assertEqual(len(result['keyframes']), 1)
        self.assertEqual(len(result['prompts']), 1)
        self.assertEqual(source.read_bytes(), original)
        restarted.delete_frame_object('p', 0, 1)
        self.assertEqual(restarted.summary('p')['annotated_frames'], [9])

    def test_frame_batch_rolls_back_on_invalid_object(self):
        self.store.init_annotations('p')
        with self.assertRaises(ValueError):
            self.store.save_frame_objects('p', 4, [self.annotation(4), {'object_id': 'invalid'}], True)
        self.assertEqual(self.store.frame_annotations('p', 4)['objects'], {})
        self.assertEqual(self.store.load('p')['keyframes'], [])

    def test_export_reuses_archive_and_invalidates_after_edit(self):
        self.store.ensure_object('p', 1, 'object')
        self.store.save_frame_object('p', 0, self.annotation(), True)
        mask = self.project / self.annotation()['mask_path']
        mask.parent.mkdir(parents=True)
        Image.fromarray(np.ones((20, 24), dtype=np.uint8) * 255).save(mask)
        service = ExportService(self.root, self.store)
        for format in ['project_json', 'mask_png', 'coco_video_json', 'all_videos_zip']:
            first = service.export('p', format)
            stamp = first.stat().st_mtime_ns
            with patch.object(service, '_export', side_effect=AssertionError('Rebuilt cached export')):
                self.assertEqual(service.export('p', format), first)
            self.assertEqual(first.stat().st_mtime_ns, stamp)
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    if name.endswith('.json'):
                        raw = archive.read(name)
                        json.loads(raw)
                        self.assertIn(b'\n  "', raw, f'{format}: {name} is not formatted')
                if format == 'mask_png':
                    self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
                if format == 'project_json':
                    self.assertIn('0', json.loads(archive.read('annotations.json'))['frames'])
        before = service.export('p', 'project_json')
        self.store.add_prompt('p', {'frame_index': 0, 'text': 'new'})
        after = service.export('p', 'project_json')
        self.assertNotEqual(before, after)
        with zipfile.ZipFile(after) as archive:
            self.assertEqual(json.loads(archive.read('annotations.json'))['prompts'][0]['text'], 'new')

    def test_rle_roundtrip_and_orientation(self):
        rng = np.random.default_rng(23)
        for mask in [np.zeros((0, 0), bool), np.zeros((5, 7), bool), np.ones((5, 7), bool),
                     rng.random((17, 23)) > .5, np.array([[0, 1], [0, 0], [1, 0]], bool)]:
            rle = encode_rle(mask)
            pixels = np.repeat(np.arange(len(rle['counts'])) % 2, rle['counts'])
            np.testing.assert_array_equal(pixels.reshape(mask.shape, order='F'), mask)
            self.assertEqual(rle['size'], list(mask.shape))

    def frames(self):
        directory = self.project / 'frames'
        directory.mkdir()
        for i in range(12):
            Image.fromarray(np.full((20, 24, 3), i * 10, dtype=np.uint8)).save(directory / f'{i:06d}.jpg')
        return directory

    def service(self):
        config = Settings(self.root, self.root, self.root, self.root, self.root, 'mock', 'float32', 'cpu',
                          sam_frame_cache_size=2, sam_feature_cache_size=2)
        return SAMService(config, self.store)

    def test_lazy_frames_bounded_cpu_cache_and_session_lifecycle(self):
        import torch
        directory = self.frames()
        loader = LazyFrameLoader(str(directory), 16, (.5, .5, .5), (.5, .5, .5), 2)
        self.assertEqual(len(loader.cache), 0)
        for i in [9, 0, 4, 9, 10]:
            self.assertEqual(loader[i].shape, (3, 16, 16))
            self.assertEqual(loader[i].device.type, 'cpu')
            self.assertLessEqual(len(loader.cache), 2)
        self.assertEqual(loader[torch.tensor([1, 2])].shape, (2, 3, 16, 16))
        service = self.service()
        service._active_backend = 'sam3_multiplex_video'
        service._model = FakePredictor()
        first = service.start_video_session('p', '', str(directory))
        self.assertEqual(len(service._model.model.loader.cache), 0)
        self.assertTrue(service._model.model.offloaded)
        self.assertEqual(service.start_video_session('p', '', str(directory)), first)
        state = service._model._all_inference_states[first]['state']
        state['feature_cache']['text'] = object()
        for i in range(12):
            state['feature_cache'][i] = object()
            service._trim_feature_cache(first)
        self.assertEqual(len([k for k in state['feature_cache'] if isinstance(k, int)]), 2)
        self.assertIn('text', state['feature_cache'])
        service.close_session('p', first)
        self.assertNotIn(first, service._model._all_inference_states)
        self.assertNotIn(first, service._sessions)
        second = service.start_video_session('p', '', str(directory))
        self.assertNotEqual(first, second)
        service.reset_session('p', second)
        self.assertIn(second, service._sessions)
        service.start_video_session('other', '', str(directory))
        self.assertIn(second, service._model.closed)
        self.assertEqual(len(service._sessions), 1)
        self.assertEqual(len(service._model._all_inference_states), 1)

    def test_inference_rejects_overlap_and_offloads_tracker_states(self):
        service = self.service()
        acquired = threading.Event()
        release = threading.Event()
        def hold():
            with service._inference_lock:
                acquired.set()
                release.wait(5)
        thread = threading.Thread(target=hold)
        thread.start()
        acquired.wait(5)
        try:
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                service.start_video_session('p', '', '')
        finally:
            release.set()
            thread.join()
        received = []
        def init_state(offload_state_to_cpu=False):
            received.append(offload_state_to_cpu)
        tracker = SimpleNamespace(init_state=init_state)
        service._model = SimpleNamespace(model=SimpleNamespace(tracker=tracker))
        service._configure_state_offload()
        tracker.init_state()
        self.assertEqual(received, [True])

    def test_streaming_mock_does_not_accumulate_mask_arrays(self):
        directory = self.frames()
        mask = self.project / self.annotation()['mask_path']
        mask.parent.mkdir(parents=True)
        Image.fromarray(np.ones((20, 24), dtype=np.uint8) * 255).save(mask)
        self.store.ensure_object('p', 1, 'test')
        self.store.save_frame_object('p', 0, self.annotation(), True)
        service = self.service()
        session = service.start_video_session('p', '', str(directory))
        seen = []
        result = service.propagate_in_video('p', session, [1], 0, 9, 'forward',
            on_frame=lambda frame: seen.append(frame['frame_index']))
        self.assertEqual(seen, list(range(10)))
        self.assertEqual(result, [{'frame_index': i} for i in range(10)])

    def test_real_stream_closes_generator_and_keeps_only_frame_indices(self):
        service = self.service()
        service._active_backend = 'sam3_video'
        closed = []
        def stream(request):
            try:
                for index in range(12):
                    yield {'frame_index': index, 'outputs': {'out_obj_ids': np.array([1]),
                           'out_binary_masks': np.ones((1, 4, 5), dtype=bool)}}
            finally:
                closed.append(True)
        service._model = SimpleNamespace(handle_stream_request=stream, _all_inference_states={})
        result = []
        seen = []
        service._consume_real_propagation_stream({'session_id': 'test'}, 0, 11, None,
            lambda frame: seen.append(frame['frame_index']), result, False, should_cancel=lambda: len(seen) >= 3)
        self.assertEqual(closed, [True])
        self.assertEqual(result, [{'frame_index': i} for i in range(3)])

    def test_oom_releases_real_session_without_changing_to_mock(self):
        directory = self.frames()
        service = self.service()
        service._active_backend = 'sam3_video'
        service._model = FakePredictor()
        session = service.start_video_session('p', '', str(directory))
        with patch.object(service, '_real_segment', side_effect=RuntimeError('CUDA out of memory')):
            with self.assertRaisesRegex(RuntimeError, 'session was released'):
                service.segment_frame('p', session, 0, str(directory / '000000.jpg'), 1)
        self.assertEqual(service._sessions, {})
        self.assertEqual(service._model._all_inference_states, {})
        self.assertEqual(service.backend_name(), 'sam3_video')
