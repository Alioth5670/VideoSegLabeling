import numpy as np


def encode_rle(mask: np.ndarray) -> dict:
    pixels = mask.astype(np.uint8).T.flatten()
    counts: list[int] = []
    last = 0
    run = 0
    for value in pixels:
        if value == last:
            run += 1
        else:
            counts.append(run)
            run = 1
            last = int(value)
    counts.append(run)
    return {"size": list(mask.shape), "counts": counts}
