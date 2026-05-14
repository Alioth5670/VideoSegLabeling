from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import annotation_store, settings, video_service
from app.utils.mask import overlay_masks, read_mask_png
from app.utils.paths import project_dir

router = APIRouter(prefix="/api/projects/{project_id}", tags=["videos"])


@router.post("/video")
async def upload_video(project_id: str, video: UploadFile = File(...), relative_path: str | None = Form(default=None)) -> dict:
    try:
        project = await video_service.save_upload_and_decode(project_id, video, relative_path)
        video_id = project.get("active_video_id")
        annotation_store.init_annotations(project_id, video_id)
        return {
            "project_id": project_id,
            "project": project,
            "video_id": video_id,
            "fps": project["fps"],
            "width": project["width"],
            "height": project["height"],
            "frame_count": project["frame_count"],
            "duration": project["duration"],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/videos/upload-folder")
async def upload_video_folder(project_id: str, videos: list[UploadFile] = File(...)) -> dict:
    try:
        before = {video.get("video_id") for video in video_service.load_project(project_id).get("videos", [])}
        project = await video_service.save_folder_uploads_and_decode(project_id, videos)
        for video in project.get("videos", []):
            if video.get("video_id") not in before:
                annotation_store.init_annotations(project_id, video.get("video_id"))
        return {"project_id": project_id, "project": project}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/frames/{frame_index}")
def get_frame(project_id: str, frame_index: int, video_id: str | None = Query(default=None)) -> FileResponse:
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    root = project_dir(settings.projects_dir, project_id)
    base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
    path = base / "frames" / f"{frame_index:06d}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/frames/{frame_index}/overlay")
def get_overlay(project_id: str, frame_index: int, video_id: str | None = Query(default=None)) -> FileResponse:
    root = project_dir(settings.projects_dir, project_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
    frame_path = base / "frames" / f"{frame_index:06d}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    annotations = annotation_store.load(project_id, resolved_video_id)
    masks = []
    frame = annotations.get("frames", {}).get(str(frame_index), {"objects": {}})
    for object_id, ann in frame.get("objects", {}).items():
        obj = annotations.get("objects", {}).get(str(object_id), {})
        if not obj.get("visible", True):
            continue
        mask_file = root / ann["mask_path"]
        if mask_file.exists():
            masks.append((read_mask_png(mask_file), tuple(obj.get("color", [255, 0, 0])), ann.get("bbox")))
    out = base / "overlays" / f"{frame_index:06d}.jpg"
    overlay_masks(frame_path, masks, out)
    return FileResponse(out, media_type="image/jpeg")


@router.get("/masks/{object_id}/{frame_index}")
def get_mask(project_id: str, object_id: int, frame_index: int, video_id: str | None = Query(default=None)) -> FileResponse:
    root = project_dir(settings.projects_dir, project_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    frame = annotation_store.frame_annotations(project_id, frame_index, resolved_video_id)
    ann = frame.get("objects", {}).get(str(object_id))
    if not ann:
        raise HTTPException(status_code=404, detail="Mask not found")
    mask_file = root / ann.get("mask_path", "")
    if not mask_file.exists():
        raise HTTPException(status_code=404, detail="Mask file not found")
    return FileResponse(mask_file, media_type="image/png")
