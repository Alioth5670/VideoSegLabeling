"""Exercise real local mux/demux methods with offloaded state, without CUDA."""
import ast
from copy import deepcopy
from pathlib import Path
from types import MethodType, SimpleNamespace
import unittest

import numpy as np

from app.services.sam_state import align_multiplex_devices, align_multiplex_state_devices


class DeviceTensor:
    """Small CPU-backed tensor with strict device checks like a CUDA matmul."""
    def __init__(self, data, device='cpu', dtype='float32'):
        self.data = np.asarray(data)
        self.device = device
        self.dtype = dtype

    @property
    def shape(self):
        return self.data.shape

    def reshape(self, *shape):
        return DeviceTensor(self.data.reshape(*shape), self.device, self.dtype)

    def view(self, shape):
        return self.reshape(*shape)

    def to(self, *, device, dtype):
        return DeviceTensor(self.data, device, dtype)

    def __matmul__(self, other):
        if self.device != other.device:
            raise RuntimeError(f'Expected all tensors to be on the same device, but got mat2 is on {other.device}, different from other tensors on {self.device}')
        if self.dtype != other.dtype:
            raise RuntimeError('matrix dtype mismatch')
        return DeviceTensor(self.data @ other.data, self.device, self.dtype)


class MultiplexDeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        source = Path(__file__).resolve().parents[2] / 'sam3/sam3/model/multiplex_utils.py'
        tree = ast.parse(source.read_text())
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MultiplexState')
        methods = [deepcopy(node) for node in owner.body if isinstance(node, ast.FunctionDef) and node.name in {'mux', 'demux'}]
        namespace = {'torch': torch}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), str(source), 'exec'), namespace)
        cls.methods = namespace

    def state(self, real_tensors=False):
        if real_tensors:
            import torch
            matrix = torch.eye(2, dtype=torch.float32)
        else:
            matrix = DeviceTensor(np.eye(2), device='cuda:0')
        state = SimpleNamespace(total_valid_entries=2, num_buckets=1, multiplex_count=2,
                                mux_matrix=matrix, demux_matrix=matrix)
        for name in ('mux', 'demux'):
            setattr(state, name, MethodType(self.methods[name], state))
        return state

    def test_original_methods_reproduce_cpu_gpu_matrix_mismatch(self):
        state = self.state()
        for method, shape in (('mux', (2, 3)), ('demux', (1, 2, 3))):
            with self.subTest(method=method), self.assertRaisesRegex(RuntimeError, 'mat2 is on cpu'):
                getattr(state, method)(DeviceTensor(np.arange(6).reshape(shape)))

    def test_first_mux_and_demux_work_without_moving_cached_inputs(self):
        state = self.state()
        mux_matrix, demux_matrix = state.mux_matrix, state.demux_matrix
        align_multiplex_state_devices(state)
        original = DeviceTensor(np.arange(6).reshape(2, 3))
        for _ in range(2):
            multiplexed = state.mux(original)
            self.assertEqual(multiplexed.shape, (1, 2, 3))
            self.assertEqual(multiplexed.device, 'cpu')
            recovered = state.demux(multiplexed)
            np.testing.assert_array_equal(recovered.data, original.data)
            self.assertEqual(original.device, 'cpu')
            self.assertIs(state.mux_matrix, mux_matrix)
            self.assertIs(state.demux_matrix, demux_matrix)
        mux = state.mux
        align_multiplex_state_devices(state)
        self.assertIs(state.mux, mux)

    def test_real_cpu_tensors_support_offloaded_low_precision_cache(self):
        import torch
        state = self.state(real_tensors=True)
        source = torch.arange(6, dtype=torch.float16).reshape(2, 3)
        with self.assertRaises(RuntimeError):
            state.mux(source)
        align_multiplex_state_devices(state)
        multiplexed = state.mux(source)
        recovered = state.demux(multiplexed)
        torch.testing.assert_close(recovered, source)
        self.assertEqual(recovered.dtype, source.dtype)
        self.assertEqual(recovered.device.type, 'cpu')
        self.assertEqual(state.mux_matrix.dtype, torch.float32)

    def test_invalid_shape_still_raises_and_restores_original_matrix(self):
        state = self.state()
        matrix = state.mux_matrix
        align_multiplex_state_devices(state)
        with self.assertRaises(AssertionError):
            state.mux(DeviceTensor(np.zeros((3, 2))))
        self.assertIs(state.mux_matrix, matrix)

    def test_service_installs_guard_for_new_and_extracted_states(self):
        from app.services.sam_service import SAMService
        tracker = SimpleNamespace(multiplex_controller=SimpleNamespace(get_state=lambda **kwargs: self.state()))
        service = object.__new__(SAMService)
        service._active_backend = 'sam3_multiplex_video'
        service._model = SimpleNamespace(model=SimpleNamespace(tracker=tracker))
        service._configure_interactive_video_tracking()
        factory = tracker.multiplex_controller.get_state
        self.assertTrue(align_multiplex_devices(tracker))
        self.assertIs(factory, tracker.multiplex_controller.get_state)
        state = factory(num_valid_entries=2)
        self.assertEqual(state.mux(DeviceTensor(np.ones((2, 3)))).device, 'cpu')
        self.assertFalse(align_multiplex_devices(SimpleNamespace()))
