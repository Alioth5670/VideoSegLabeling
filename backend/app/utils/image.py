from pathlib import Path

from PIL import Image


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size
