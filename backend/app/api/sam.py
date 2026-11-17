from pathlib import Path
import json
import queue
import asyncio
import threading
import traceback
import logging
import uuid

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import annotation_store, sam_service, settings, video_service, account_store
from app.services.sam_pool import GPUCapacityError
from app.services.gpu_resources import GPUResourceError
from app.services.gpu_settings import GPUSettings
from app.api.auth import admin_user
from app.schemas.sam import PropagateRequest, SegmentRequest
from app.utils.mask import area_from_mask, bbox_from_mask, polygons_from_mask, save_mask_png
from app.utils.paths import mask_path, project_dir, rel_to_project

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects/{project_id}/sam", tags=["sam"])
_propagation_cancellations: dict[str, threading.Event] = {}


class BackendSwitchRequest(BaseModel):
    backend: str


class DeviceSwitchRequest(BaseModel):
    device: str


class CancelPropagationRequest(BaseModel):
    session_id: str


class ResetSessionRequest(BaseModel):
    session_id: str


status_router = APIRouter(prefix="/api/sam", tags=["sam"])


class AdminReleaseRequest(BaseModel):
    force: bool = False


@status_router.get('/admin')
def admin_gpu_snapshot(request: Request) -> dict:
    admin_user(request)
    snapshot = sam_service.admin_snapshot()
    users = {user['id']: user['username'] for user in account_store.users()}
    for session in snapshot['sessions']:
        session['username'] = users.get(session['owner_id'], session['owner_id'])
        record = account_store.project_record(session['project_id'], include_deleted=True)
        session['project_name'] = record['name'] if record else session['project_id']
    return snapshot


@status_router.put('/admin/settings')
def save_admin_gpu_settings(payload: GPUSettings, request: Request) -> dict:
    admin_user(request)
    try:
        return {'settings': sam_service.update_admin_settings(payload)}
    except GPUCapacityError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        logger.exception('Failed to save GPU settings')
        raise HTTPException(500, '配置保存失败，请检查存储目录权限。') from exc


@status_router.post('/admin/sessions/{session_id}/release')
def admin_release_gpu_session(session_id: str, payload: AdminReleaseRequest, request: Request) -> dict:
    admin_user(request)
    try:
        sam_service.admin_release_session(session_id, force=payload.force)
    except GPUCapacityError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {'ok': True}


@status_router.get('/resources')
def gpu_resources() -> dict:
    devices = sam_service.available_devices()
    return {'devices': devices, 'free': sum(bool(device['available']) for device in devices),
            'pool': sam_service.config.sam_gpu_pool and sam_service.backend_name() != 'mock',
            'idle_seconds': sam_service.config.sam_session_idle_seconds}


@status_router.post("/backend")
def switch_backend(payload: BackendSwitchRequest) -> dict:
    return _switch_backend(payload)


@status_router.post("/device")
def switch_device(payload: DeviceSwitchRequest) -> dict:
    try:
        device = sam_service.set_device(payload.device)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "device": device,
        "devices": sam_service.available_devices(),
        "backend": sam_service.backend_name(),
        "fallback_error": sam_service.fallback_error(),
    }


@router.post("/backend")
def switch_project_backend(project_id: str, payload: BackendSwitchRequest) -> dict:
    return _switch_backend(payload)


def _switch_backend(payload: BackendSwitchRequest) -> dict:
    try:
        backend = sam_service.set_backend(payload.backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "backend": backend,
        "video_supported": sam_service.is_video_supported(),
        "multiplex_supported": sam_service.is_multiplex_supported(),
        "fallback_error": sam_service.fallback_error(),
    }


def _session_frames(project_id: str, video_id: str | None) -> str:
    resolved = video_service.active_video_id(project_id, video_id)
    base = video_service.video_path(project_id, resolved) if resolved else project_dir(settings.projects_dir, project_id)
    return str(base / 'frames')


def _check_video_session(project_id: str, session_id: str | None, video_id: str | None) -> None:
    if session_id:
        try:
            sam_service.check_video_session(project_id, session_id, _session_frames(project_id, video_id))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get('/session')
def current_session(project_id: str, request: Request, video_id: str | None = Query(default=None)) -> dict:
    session = sam_service.find_video_session(project_id, _session_frames(project_id, video_id), owner_id=request.state.user['id'])
    return {'session': session, 'backend': (session or {}).get('backend', sam_service.backend_name()),
            'device': (session or {}).get('device', sam_service.device_name())}


@router.post("/session")
def start_session(project_id: str, request: Request, video_id: str | None = Query(default=None)) -> dict:
    try:
        root = project_dir(settings.projects_dir, project_id)
        resolved_video_id = video_service.active_video_id(project_id, video_id)
        video = video_service.video_info(project_id, resolved_video_id)
        if not video:
            raise ValueError("No video selected")
        base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
        session_id = sam_service.start_video_session(project_id, str(root / video["video_path"]), str(base / "frames"), owner_id=request.state.user["id"])
    except GPUCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GPUResourceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = sam_service.find_video_session(project_id, str(base / "frames"), owner_id=request.state.user["id"]) or {}
    return {
        "session_id": session_id,
        "object_ids": session.get("object_ids", []),
        "backend": session.get("backend", sam_service.backend_name()),
        "device": session.get("device", sam_service.device_name()),
        "video_supported": sam_service.is_video_supported(),
        "multiplex_supported": sam_service.is_multiplex_supported(),
        "fallback_error": sam_service.fallback_error(),
    }


@router.post("/session/reset")
def reset_session(project_id: str, payload: ResetSessionRequest, video_id: str | None = Query(default=None)) -> dict:
    _check_video_session(project_id, payload.session_id, video_id)
    try:
        sam_service.reset_session(project_id, payload.session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "session_id": payload.session_id}


@router.post("/session/close")
def close_session(project_id: str, payload: ResetSessionRequest) -> dict:
    try:
        sam_service.close_session(project_id, payload.session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/segment")
def segment(project_id: str, payload: SegmentRequest, video_id: str | None = Query(default=None)) -> dict:
    _check_video_session(project_id, payload.session_id, video_id)
    root = project_dir(settings.projects_dir, project_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
    image_path = base / "frames" / f"{payload.frame_index:06d}.jpg"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    object_id = payload.object_id
    created_object_id = None
    if object_id is None and (payload.points or payload.box):
        created = annotation_store.ensure_object(project_id, None, payload.category or payload.text, payload.frame_index, resolved_video_id)
        object_id = int(created["object_id"])
        created_object_id = object_id
    try:
        results = sam_service.segment_frame(
            project_id=project_id,
            session_id=payload.session_id,
            frame_index=payload.frame_index,
            image_path=str(image_path),
            object_id=object_id,
            text=payload.text,
            box=payload.box,
            points=[p.model_dump() for p in payload.points],
            category=payload.category,
        )
    except Exception as exc:
        logger.exception('SAM segmentation failed: project=%s video=%s session=%s frame=%s object=%s',
                         project_id, resolved_video_id, payload.session_id, payload.frame_index, object_id)
        if created_object_id is not None:
            annotation_store.delete_object(project_id, created_object_id, resolved_video_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not results:
        if created_object_id is not None:
            annotation_store.delete_object(project_id, created_object_id, resolved_video_id)
        raise HTTPException(status_code=400, detail="SAM returned no masks for this prompt. Select only one prompt type, then try a larger box or a positive point near the object center.")
    if object_id is not None:
        results = [_merge_results_for_object(results, object_id)]
    objects = {}
    for result in results:
        result_object_id = int(result["object_id"])
        obj = annotation_store.ensure_object(
            project_id,
            result_object_id,
            payload.category or payload.text,
            payload.frame_index,
            resolved_video_id,
        )
        path = mask_path(settings.projects_dir, project_id, result["object_id"], payload.frame_index, resolved_video_id)
        save_mask_png(result["mask"], path)
        ann = _annotation(project_id, result, path, is_keyframe=True)
        annotation_store.save_frame_object(project_id, payload.frame_index, ann, is_keyframe=True, video_id=resolved_video_id)
        overlay_url = f"/api/projects/{project_id}/frames/{payload.frame_index}/overlay"
        if resolved_video_id:
            overlay_url = f"{overlay_url}?video_id={resolved_video_id}"
        objects[str(result["object_id"])] = {**ann, "mask_url": _mask_url(project_id, result["object_id"], payload.frame_index, resolved_video_id), "overlay_url": overlay_url, "object": obj}
    annotation_store.add_prompt(project_id, {
        "frame_index": payload.frame_index,
        "object_id": object_id,
        "prompt_type": "box" if payload.box else ("point" if payload.points else "text"),
        "box": payload.box,
        "points": [p.model_dump() for p in payload.points],
        "text": payload.text,
    }, resolved_video_id)
    return {"frame_index": payload.frame_index, "objects": objects}


@router.post("/propagate")
def propagate(project_id: str, payload: PropagateRequest, request: Request, video_id: str | None = Query(default=None)) -> StreamingResponse:
    _check_video_session(project_id, payload.session_id, video_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    events: queue.Queue[dict] = queue.Queue(maxsize=8)
    disconnected = threading.Event()
    cancel_key = _propagation_cancel_key(project_id, payload.session_id, resolved_video_id)
    cancel_event = threading.Event()
    _propagation_cancellations[cancel_key] = cancel_event
    request_id = uuid.uuid4().hex

    def publish(event: dict) -> None:
        while not disconnected.is_set():
            try:
                events.put(event, timeout=0.2)
                return
            except queue.Full:
                continue

    def worker() -> None:
        output_frames: set[int] = set()

        def save_propagated_frame(frame: dict) -> None:
            if cancel_event.is_set():
                return
            saved = _save_propagated_frame(project_id, frame, resolved_video_id)
            output_frames.add(int(saved["frame_index"]))
            publish({"type": "frame", "frame": saved})

        try:
            sam_service.propagate_in_video(
                project_id,
                payload.session_id,
                payload.object_ids,
                payload.start_frame,
                payload.end_frame,
                payload.direction,
                resolved_video_id,
                on_frame=save_propagated_frame,
                should_cancel=cancel_event.is_set,
            )
            event_type = "cancelled" if cancel_event.is_set() else "done"
            publish({
                "type": event_type,
                "backend": sam_service.backend_name(),
                "frames": [],
                "frame_count": len(output_frames),
                "request_id": request_id,
            })
        except Exception as exc:
            traceback.print_exc()
            publish({"type": "error", "detail": str(exc)})
        finally:
            existing = _propagation_cancellations.get(cancel_key)
            if existing is cancel_event:
                _propagation_cancellations.pop(cancel_key, None)

    async def stream():
        threading.Thread(target=worker, daemon=True).start()
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.to_thread(events.get, True, 0.25)
                except queue.Empty:
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event['type'] in {'done', 'cancelled', 'error'}:
                    break
        finally:
            disconnected.set()
            cancel_event.set()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/propagate/cancel")
def cancel_propagation(project_id: str, payload: CancelPropagationRequest, video_id: str | None = Query(default=None)) -> dict:
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    cancel_key = _propagation_cancel_key(project_id, payload.session_id, resolved_video_id)
    cancel_event = _propagation_cancellations.get(cancel_key)
    if cancel_event is None:
        return {"cancelled": False}
    cancel_event.set()
    return {"cancelled": True}


def _save_propagated_frame(project_id: str, frame: dict, video_id: str | None) -> dict:
    objects = {}
    annotations = []
    for result in frame["objects"]:
        path = mask_path(settings.projects_dir, project_id, result["object_id"], frame["frame_index"], video_id)
        save_mask_png(result["mask"], path)
        ann = _annotation(project_id, result, path, is_keyframe=False)
        annotations.append(ann)
        objects[str(result["object_id"])] = {**ann, "mask_url": _mask_url(project_id, result["object_id"], frame["frame_index"], video_id)}
    annotation_store.save_frame_objects(project_id, frame['frame_index'], annotations, is_keyframe=False, video_id=video_id)
    return {"frame_index": frame["frame_index"], "objects": objects}


def _merge_results_for_object(results: list[dict], object_id: int) -> dict:
    if len(results) == 1:
        result = {**results[0]}
        result["object_id"] = object_id
        result["track_id"] = object_id
        return result
    merged_mask = np.zeros_like(results[0]["mask"], dtype=bool)
    for result in results:
        merged_mask |= np.asarray(result["mask"]).astype(bool)
    first = results[0]
    return {
        **first,
        "object_id": object_id,
        "track_id": object_id,
        "mask": merged_mask,
        "bbox": bbox_from_mask(merged_mask),
        "area": area_from_mask(merged_mask),
        "score": max(float(result.get("score") or 0) for result in results),
    }


def _annotation(project_id: str, result: dict, path: Path, is_keyframe: bool) -> dict:
    root = project_dir(settings.projects_dir, project_id)
    polygons = polygons_from_mask(result["mask"])
    return {
        "object_id": result["object_id"],
        "track_id": result["track_id"],
        "frame_index": result["frame_index"],
        "mask_path": rel_to_project(path, root),
        "polygons": polygons,
        "bbox": result["bbox"],
        "area": result["area"],
        "score": result["score"],
        "source": result["source"],
        "is_keyframe": is_keyframe,
    }


def _mask_url(project_id: str, object_id: int, frame_index: int, video_id: str | None) -> str:
    url = f"/api/projects/{project_id}/masks/{object_id}/{frame_index}"
    if video_id:
        url += f"?video_id={video_id}"
    return url


def _propagation_cancel_key(project_id: str, session_id: str, video_id: str | None) -> str:
    return f"{project_id}:{video_id or ''}:{session_id}"
