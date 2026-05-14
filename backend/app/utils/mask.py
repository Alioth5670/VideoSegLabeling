import base64
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def save_mask_png(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    binary = (mask > 0).astype(np.uint8) * 255
    Image.fromarray(binary, mode="L").save(path)


def read_mask_png(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("L")) > 0


def bbox_from_mask(mask: np.ndarray) -> list[float]:
    ys, xs = np.where(mask > 0)
    if xs.size == 0 or ys.size == 0:
        return [0, 0, 0, 0]
    return [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]


def area_from_mask(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def mask_from_base64_png(data: str) -> np.ndarray:
    if "," in data:
        data = data.split(",", 1)[1]
    image = Image.open(BytesIO(base64.b64decode(data))).convert("L")
    return np.array(image) > 0


def polygons_from_mask(mask: np.ndarray, epsilon_ratio: float = 0.003) -> list[list[list[float]]]:
    binary = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons: list[list[list[float]]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 4:
            continue
        epsilon = max(1.0, epsilon_ratio * cv2.arcLength(contour, True))
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue
        points = [[float(point[0][0]), float(point[0][1])] for point in approx]
        polygons.append(points)
    polygons.sort(key=lambda polygon: cv2.contourArea(np.array(polygon, dtype=np.float32).reshape(-1, 1, 2)), reverse=True)
    return polygons


def mask_from_polygons(polygons: list[list[list[float]]], width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        points = np.array(
            [[
                [int(round(max(0, min(width - 1, point[0])))), int(round(max(0, min(height - 1, point[1]))))]
                for point in polygon
            ]],
            dtype=np.int32,
        )
        cv2.fillPoly(mask, points, 255)
    return mask > 0


def overlay_masks(image_path: Path, masks: list[tuple[np.ndarray, tuple[int, int, int], list[float] | None]], out_path: Path) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(str(image_path))
    overlay = image.copy()
    alpha = 0.45
    for mask, color_rgb, bbox in masks:
        color_bgr = (int(color_rgb[2]), int(color_rgb[1]), int(color_rgb[0]))
        color_layer = np.zeros_like(image)
        color_layer[:] = color_bgr
        overlay = np.where(mask[..., None], (overlay * (1 - alpha) + color_layer * alpha).astype(np.uint8), overlay)
        if bbox and bbox != [0, 0, 0, 0]:
            x1, y1, x2, y2 = [int(round(v)) for v in bbox]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color_bgr, 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), overlay)
