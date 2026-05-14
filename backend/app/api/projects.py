import shutil

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import annotation_store, sam_service, settings, video_service
from app.schemas.annotation import ObjectUpdate, TrackedObjectCreate
from app.schemas.project import ProjectCreate
from app.utils.paths import project_dir

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create_project(payload: ProjectCreate) -> dict:
    try:
        return video_service.create_project(payload.name, payload.project_dir)
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail="Project directory already contains a project.json") from exc


@router.get("")
def list_projects() -> dict:
    return {"projects": video_service.list_projects()}


@router.get("/{project_id}")
def get_project(project_id: str, video_id: str | None = Query(default=None)) -> dict:
    try:
        project = video_service.load_project(project_id)
        if video_id:
            project = video_service.set_active_video(project_id, video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Video not found") from exc
    return {"project": project, "annotations": annotation_store.load(project_id, video_id)}


@router.get("/{project_id}/videos")
def list_videos(project_id: str) -> dict:
    try:
        project = video_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {"videos": project.get("videos", []), "active_video_id": project.get("active_video_id")}


@router.post("/{project_id}/videos/{video_id}/activate")
def activate_video(project_id: str, video_id: str) -> dict:
    try:
        project = video_service.set_active_video(project_id, video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Video not found") from exc
    return {"project": project, "annotations": annotation_store.load(project_id, video_id)}


@router.post("/{project_id}/objects")
def create_object(project_id: str, payload: TrackedObjectCreate, video_id: str | None = Query(default=None)) -> dict:
    obj = annotation_store.ensure_object(project_id, None, payload.category, payload.frame_index, video_id)
    if payload.color is not None:
        obj = annotation_store.update_object(project_id, obj["object_id"], {"color": list(payload.color)}, video_id)
    return obj


@router.patch("/{project_id}/objects/{object_id}")
def update_object(project_id: str, object_id: int, payload: ObjectUpdate, video_id: str | None = Query(default=None)) -> dict:
    try:
        return annotation_store.update_object(project_id, object_id, payload.model_dump(), video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Object not found") from exc


@router.post("/{project_id}/objects/{object_id}/session/remove")
def remove_object_from_session(
    project_id: str,
    object_id: int,
    session_id: str = Query(...),
    video_id: str | None = Query(default=None),
) -> dict:
    _ = video_service.active_video_id(project_id, video_id)
    try:
        sam_service.remove_object(project_id, session_id, object_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "object_id": object_id, "session_id": session_id}


@router.delete("/{project_id}/objects/{object_id}")
def delete_object(
    project_id: str,
    object_id: int,
    video_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> dict:
    sam_warning = None
    sam_removed = False
    if session_id:
        try:
            sam_service.remove_object(project_id, session_id, object_id)
            sam_removed = True
        except Exception as exc:
            sam_warning = str(exc)
    annotation_store.delete_object(project_id, object_id, video_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    root = project_dir(settings.projects_dir, project_id)
    base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
    shutil.rmtree(base / "masks" / f"object_{object_id}", ignore_errors=True)
    return {"ok": True, "sam_removed": sam_removed, "sam_warning": sam_warning}
