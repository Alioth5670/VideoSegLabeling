"""Bounded, demand-loaded CPU frames compatible with SAM3's image indexing."""
from collections import OrderedDict
from contextlib import contextmanager, ExitStack
import sys
from pathlib import Path
from threading import RLock

import numpy as np
from PIL import Image


class LazyFrameLoader:
    def __init__(self, directory: str, image_size: int, mean: tuple, std: tuple, capacity: int = 8):
        self.paths = sorted((p for p in Path(directory).iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png'}),
                            key=lambda p: int(p.stem))
        if not self.paths:
            raise ValueError('Video has no decoded frames')
        self.image_size = image_size
        self.mean = mean
        self.std = std
        self.capacity = max(1, capacity)
        self.cache: OrderedDict[int, object] = OrderedDict()
        self._lock = RLock()
        with Image.open(self.paths[0]) as image:
            self.video_width, self.video_height = image.size

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index):
        import torch
        if isinstance(index, slice):
            return torch.stack([self[i] for i in range(*index.indices(len(self)))])
        if isinstance(index, (list, tuple)) or isinstance(index, torch.Tensor) and index.ndim > 0:
            return torch.stack([self[int(i)] for i in index])
        index = int(index)
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        with self._lock:
            if index in self.cache:
                self.cache.move_to_end(index)
                return self.cache[index]
            # Match the official PIL bilinear resize / fp16 normalization path.
            with Image.open(self.paths[index]) as source:
                image = source.convert('RGB').resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
                pixels = np.array(image, dtype=np.float32) / 255.0
            tensor = torch.from_numpy(pixels).permute(2, 0, 1).to(dtype=torch.float16)
            tensor.sub_(torch.tensor(self.mean, dtype=torch.float16)[:, None, None])
            tensor.div_(torch.tensor(self.std, dtype=torch.float16)[:, None, None])
            self.cache[index] = tensor
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            return tensor

    def to(self, *args, **kwargs):
        # SAM moves the selected frame batch to its compute device itself.
        return self

    @property
    def device(self):
        import torch
        return torch.device('cpu')

    @property
    def shape(self) -> tuple[int, int, int, int]:
        return len(self), 3, self.image_size, self.image_size

    def clear(self) -> None:
        with self._lock:
            self.cache.clear()


@contextmanager
def lazy_frame_source(model, loader: LazyFrameLoader):
    """Adapt the checked-in SAM loaders without replacing official init_state.

    The caller must serialize model operations while module loader references
    are temporarily installed. No background loader is started.
    """
    modules = {sys.modules.get(cls.__module__) for cls in type(model).__mro__}
    modules = {module for module in modules if module and hasattr(module, 'load_resource_as_video_frames')}
    if not modules:
        raise RuntimeError('Unsupported SAM init_state frame loader; refusing eager video loading')
    def load_frames(*args, **kwargs):
        return loader, loader.video_height, loader.video_width
    with ExitStack() as stack:
        for module in modules:
            original = module.load_resource_as_video_frames
            stack.callback(setattr, module, 'load_resource_as_video_frames', original)
            module.load_resource_as_video_frames = load_frames
        yield
