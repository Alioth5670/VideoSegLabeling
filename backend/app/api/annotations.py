import json

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import annotation_store, settings, video_service
from app.schemas.annotation import BatchDeleteAnnotationsRequest, ManualBBoxRequest, ManualMaskRequest, ManualPolygonRequest
from app.utils.mask import (
    area_from_mask,
    bbox_from_mask,
    mask_from_base64_png,
    mask_from_polygons,
    polygons_from_mask,
    read_mask_png,
    save_mask_png,
)
from app.utils.paths import mask_path, project_dir, rel_to_project

router = APIRouter(prefix="/api/projects/{project_id}/annotations", tags=["annotations"])


class FrameAnnotationUpdate(BaseModel):
    locked: bool | None = None


@router.get("")
def get_annotations(project_id: str, video_id: str | None = Query(default=None)) -> dict:
    return annotation_store.load(project_id, video_id)


@router.post("/mask")
def save_manual_mask(project_id: str, payload: ManualMaskRequest, video_id: str | None = Query(default=None)) -> dict:
    if payload.format != "png_base64":
        raise HTTPException(status_code=400, detail="Only png_base64 masks are implemented in phase 4")
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    mask = mask_from_base64_png(payload.mask)
    obj = _manual_object(project_id, payload.object_id, payload.frame_index, payload.allow_overwrite, resolved_video_id)
    object_id = int(obj["object_id"])
    path = mask_path(settings.projects_dir, project_id, object_id, payload.frame_index, resolved_video_id)
    save_mask_png(mask, path)
    root = project_dir(settings.projects_dir, project_id)
    ann = {
        "object_id": object_id,
        "track_id": object_id,
        "frame_index": payload.frame_index,
        "mask_path": rel_to_project(path, root),
        "bbox": bbox_from_mask(mask),
        "area": area_from_mask(mask),
        "score": 1.0,
        "source": "manual",
        "is_keyframe": payload.is_keyframe,
    }
    annotation_store.save_frame_object(project_id, payload.frame_index, ann, payload.is_keyframe, resolved_video_id)
    return {**ann, "object": obj}


@router.post("/polygon")
def save_manual_polygon(project_id: str, payload: ManualPolygonRequest, video_id: str | None = Query(default=None)) -> dict:
    root = project_dir(settings.projects_dir, project_id)
    project = root / "project.json"
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    meta = json.loads(project.read_text(encoding="utf-8"))
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    video = video_service.video_info(project_id, resolved_video_id) or meta
    mask = mask_from_polygons(
        [[list(point) for point in polygon] for polygon in payload.polygons],
        int(video["width"]),
        int(video["height"]),
    )
    obj = _manual_object(project_id, payload.object_id, payload.frame_index, payload.allow_overwrite, resolved_video_id)
    object_id = int(obj["object_id"])
    path = mask_path(settings.projects_dir, project_id, object_id, payload.frame_index, resolved_video_id)
    save_mask_png(mask, path)
    ann = {
        "object_id": object_id,
        "track_id": object_id,
        "frame_index": payload.frame_index,
        "mask_path": rel_to_project(path, root),
        "bbox": bbox_from_mask(mask),
        "area": area_from_mask(mask),
        "score": 1.0,
        "source": "manual",
        "is_keyframe": payload.is_keyframe,
    }
    annotation_store.save_frame_object(project_id, payload.frame_index, ann, payload.is_keyframe, resolved_video_id)
    return {**ann, "polygons": payload.polygons, "mask_url": _mask_url(project_id, object_id, payload.frame_index, resolved_video_id), "object": obj}


@router.post("/bbox")
def save_manual_bbox(project_id: str, payload: ManualBBoxRequest, video_id: str | None = Query(default=None)) -> dict:
    root = project_dir(settings.projects_dir, project_id)
    project = root / "project.json"
    if not project.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    meta = json.loads(project.read_text(encoding="utf-8"))
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    video = video_service.video_info(project_id, resolved_video_id) or meta
    width = int(video["width"])
    height = int(video["height"])
    x1, y1, x2, y2 = payload.bbox
    left = max(0, min(width, int(round(min(x1, x2)))))
    right = max(0, min(width, int(round(max(x1, x2)))))
    top = max(0, min(height, int(round(min(y1, y2)))))
    bottom = max(0, min(height, int(round(max(y1, y2)))))
    if right <= left or bottom <= top:
        raise HTTPException(status_code=400, detail="BBox must have positive width and height")
    mask = np.zeros((height, width), dtype=bool)
    mask[top:bottom, left:right] = True
    obj = _manual_object(project_id, payload.object_id, payload.frame_index, payload.allow_overwrite, resolved_video_id)
    object_id = int(obj["object_id"])
    path = mask_path(settings.projects_dir, project_id, object_id, payload.frame_index, resolved_video_id)
    save_mask_png(mask, path)
    ann = {
        "object_id": object_id,
        "track_id": object_id,
        "frame_index": payload.frame_index,
        "mask_path": rel_to_project(path, root),
        "bbox": bbox_from_mask(mask),
        "area": area_from_mask(mask),
        "score": 1.0,
        "source": "manual",
        "is_keyframe": payload.is_keyframe,
    }
    annotation_store.save_frame_object(project_id, payload.frame_index, ann, payload.is_keyframe, resolved_video_id)
    return {**ann, "mask_url": _mask_url(project_id, object_id, payload.frame_index, resolved_video_id), "object": obj}


@router.get("/{frame_index}")
def get_frame_annotations(project_id: str, frame_index: int, video_id: str | None = Query(default=None)) -> dict:
    root = project_dir(settings.projects_dir, project_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    data = annotation_store.frame_annotations(project_id, frame_index, resolved_video_id)
    objects = {}
    for object_id, ann in data.get("objects", {}).items():
        stored_mask_path = ann.get("mask_path")
        mask_file = root / stored_mask_path if stored_mask_path else None
        polygons = ann.get("polygons")
        if polygons is None:
            polygons = polygons_from_mask(read_mask_png(mask_file)) if mask_file and mask_file.exists() else []
        objects[object_id] = {
            **ann,
            "mask_url": _mask_url(project_id, int(object_id), frame_index, resolved_video_id) if stored_mask_path else None,
            "polygons": polygons,
        }
    return {"frame_index": frame_index, "objects": objects}


@router.post("/batch-delete")
def batch_delete_annotations(project_id: str, payload: BatchDeleteAnnotationsRequest, video_id: str | None = Query(default=None)) -> dict:
    if not payload.delete_annotations and not payload.delete_prompts:
        raise HTTPException(status_code=400, detail="Select annotations, prompts, or both to delete")
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    return annotation_store.batch_delete(
        project_id,
        payload.start_frame,
        payload.end_frame,
        payload.object_ids,
        payload.delete_annotations,
        payload.delete_prompts,
        resolved_video_id,
    )


@router.delete("/{frame_index}/objects/{object_id}")
def delete_frame_annotation(project_id: str, frame_index: int, object_id: int, video_id: str | None = Query(default=None)) -> dict:
    deleted = annotation_store.delete_frame_object(project_id, frame_index, object_id, video_id)
    object_deleted = annotation_store.delete_object_if_unreferenced(project_id, object_id, video_id) if deleted else False
    return {"deleted": deleted, "object_deleted": object_deleted, "frame_index": frame_index, "object_id": object_id}


@router.patch("/{frame_index}/objects/{object_id}")
def update_frame_annotation(project_id: str, frame_index: int, object_id: int, payload: FrameAnnotationUpdate, video_id: str | None = Query(default=None)) -> dict:
    try:
        annotation = annotation_store.update_frame_object(project_id, frame_index, object_id, payload.model_dump(), video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Annotation not found") from exc
    return annotation


def _manual_object(project_id: str, object_id: int | None, frame_index: int, allow_overwrite: bool, video_id: str | None) -> dict:
    if object_id is not None:
        _ensure_manual_write_allowed(project_id, frame_index, object_id, allow_overwrite, video_id)
    return annotation_store.ensure_object(project_id, object_id, None, frame_index, video_id)


def _ensure_manual_write_allowed(project_id: str, frame_index: int, object_id: int, allow_overwrite: bool, video_id: str | None) -> None:
    if allow_overwrite:
        return
    existing = annotation_store.frame_annotations(project_id, frame_index, video_id).get("objects", {}).get(str(object_id))
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This object already has an annotation on the current frame. Edit or delete the existing annotation instead.",
        )


def _mask_url(project_id: str, object_id: int, frame_index: int, video_id: str | None) -> str:
    url = f"/api/projects/{project_id}/masks/{object_id}/{frame_index}"
    if video_id:
        url += f"?video_id={video_id}"
    return url
