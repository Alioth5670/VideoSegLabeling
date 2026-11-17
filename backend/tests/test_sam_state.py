"""Reproduce the reported KeyError using actual checked-in tracker methods on CPU."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from app.services.sam_state import preserve_prompt_cache


class TrackerCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        # Load just the two real methods, without loading SAM weights, requiring
        # CUDA, or importing the full model's optional GPU dependencies.
        path = Path(__file__).resolve().parents[2] / 'sam3/sam3/model/video_tracking_multiplex_demo.py'
        tree = ast.parse(path.read_text())
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        sources = [
            (classes['VideoTrackingMultiplexDemo'], '_clear_non_cond_mem_around_input'),
            (classes['Sam3VideoTrackingMultiplexDemo'], 'propagate_in_video'),
        ]
        methods = [deepcopy(next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name))
                   for owner, name in sources]
        assert len(methods) == 2
        for node in methods:
            node.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
        namespace = {'torch': torch, 'deepcopy': deepcopy, 'tqdm': lambda items, **kwargs: items}
        exec(compile(module, str(path), 'exec'), namespace)
        cls.real_clear = staticmethod(namespace['_clear_non_cond_mem_around_input'])
        cls.real_propagate = staticmethod(namespace['propagate_in_video'])

    def tracker(self):
        tracker = SimpleNamespace(clear_non_cond_mem_around_input=True, clear_non_cond_mem_for_multi_obj=True,
            memory_temporal_stride_for_eval=1, num_maskmem=7, recomputed=[])
        tracker._get_obj_num = lambda state: len(state['obj_ids'])
        tracker._clear_non_cond_mem_around_input = lambda state, frame: self.real_clear(tracker, state, frame)
        tracker._get_processing_order = lambda state, start, count, reverse: (
            range(start, start - count - 1, -1) if reverse else range(start, start + count + 1))
        tracker._get_orig_video_res_output = lambda state, masks: (masks, masks)
        def infer(**kwargs):
            frame = kwargs['frame_idx']
            tracker.recomputed.append(frame)
            output = self.output(frame)
            return output, output['pred_masks']
        tracker._run_single_frame_inference = infer
        def add_per_object(state, frame, output, key):
            for data in state['output_dict_per_obj'].values():
                data[key][frame] = output
        tracker._add_output_per_object = add_per_object
        return tracker

    @staticmethod
    def output(value):
        return {'pred_masks': np.full((1, 1, 2, 2), value, dtype=np.float32),
                'object_score_logits': np.ones((1, 1), dtype=np.float32)}

    def state(self, anchor=87, correction=91):
        outputs = {'cond_frame_outputs': {anchor: self.output(anchor)},
                   'non_cond_frame_outputs': {90: self.output(-90), correction: self.output(correction)}}
        return {'obj_ids': [1, 2], 'obj_id_to_idx': {1: 0, 2: 1},
                'output_dict': outputs,
                'output_dict_per_obj': {index: {key: dict(values) for key, values in outputs.items()} for index in (0, 1)},
                'consolidated_frame_inds': {'cond_frame_outputs': {anchor}, 'non_cond_frame_outputs': {correction}},
                'point_inputs_per_obj': {0: {anchor: object(), correction: object()}},
                'frames_already_tracked': {}}

    def test_original_tracker_reproduces_keyerror_91(self):
        tracker = self.tracker()
        with self.assertRaises(KeyError) as error:
            list(self.real_propagate(tracker, self.state(), 87, 5, False))
        self.assertEqual(error.exception.args, (91,))

    def test_guard_preserves_corrections_and_recomputes_ordinary_frames(self):
        tracker = self.tracker()
        state = self.state()
        correction = state['output_dict']['non_cond_frame_outputs'][91]
        self.assertTrue(preserve_prompt_cache(tracker))
        result = list(self.real_propagate(tracker, state, 87, 5, False))
        self.assertEqual([frame[0] for frame in result], [87, 88, 89, 90, 91, 92])
        self.assertEqual(tracker.recomputed, [88, 89, 90, 92])
        self.assertIs(state['output_dict']['non_cond_frame_outputs'][91], correction)
        self.assertIs(result[4][2], correction['pred_masks'])
        self.assertEqual(state['output_dict']['non_cond_frame_outputs'][90]['pred_masks'][0, 0, 0, 0], 90)
        # A second run and reverse propagation keep the correction usable too.
        self.assertEqual(len(list(self.real_propagate(tracker, state, 87, 5, False))), 6)
        reverse = list(self.real_propagate(tracker, state, 92, 5, True))
        self.assertEqual([frame[0] for frame in reverse], [92, 91, 90, 89, 88, 87])

    def test_guard_retains_per_object_views_without_cloning(self):
        tracker = self.tracker()
        state = self.state()
        per_object = [values['non_cond_frame_outputs'][91] for values in state['output_dict_per_obj'].values()]
        preserve_prompt_cache(tracker)
        tracker._clear_non_cond_mem_around_input(state, 87)
        self.assertNotIn(90, state['output_dict']['non_cond_frame_outputs'])
        for index, data in state['output_dict_per_obj'].items():
            self.assertIs(data['non_cond_frame_outputs'][91], per_object[index])
            self.assertNotIn(90, data['non_cond_frame_outputs'])
        self.assertEqual(state['consolidated_frame_inds']['non_cond_frame_outputs'], {91})

    def test_guard_installed_by_service_and_is_idempotent(self):
        from app.services.sam_service import SAMService
        service = object.__new__(SAMService)
        tracker = self.tracker()
        service._active_backend = 'sam3_multiplex_video'
        service._model = SimpleNamespace(model=SimpleNamespace(tracker=tracker))
        service._configure_interactive_video_tracking()
        clear = tracker._clear_non_cond_mem_around_input
        preserve_prompt_cache(tracker)
        self.assertIs(tracker._clear_non_cond_mem_around_input, clear)
        state = self.state()
        clear(state, 87)
        self.assertIn(91, state['output_dict']['non_cond_frame_outputs'])
        self.assertFalse(preserve_prompt_cache(SimpleNamespace()))
