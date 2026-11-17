import numpy as np


def encode_rle(mask: np.ndarray) -> dict:
    """COCO uncompressed, column-major RLE, computed with vector operations."""
    pixels = np.asarray(mask, dtype=bool).ravel(order="F")
    if pixels.size == 0:
        counts = [0]
    else:
        changes = np.flatnonzero(pixels[1:] != pixels[:-1]) + 1
        counts = np.diff(np.concatenate(([0], changes, [pixels.size]))).tolist()
        if pixels[0]:
            counts.insert(0, 0)
    return {"size": list(mask.shape), "counts": counts}
