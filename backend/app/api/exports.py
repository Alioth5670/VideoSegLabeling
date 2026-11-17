from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import export_jobs, settings
from app.utils.paths import project_dir

router = APIRouter(prefix="/api/projects/{project_id}", tags=["exports"])


class ExportRequest(BaseModel):
    format: str
    video_id: str | None = None


@router.post("/export", status_code=202)
def export(project_id: str, payload: ExportRequest) -> dict:
    try:
        return export_jobs.submit(project_id, payload.format, payload.video_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/export/{job_id}")
def export_status(project_id: str, job_id: str) -> dict:
    try:
        return export_jobs.get(project_id, job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Export task not found") from exc


@router.get("/download/{path:path}")
def download(project_id: str, path: str) -> FileResponse:
    root = project_dir(settings.projects_dir, project_id).resolve()
    file_path = (root / path).resolve()
    if root not in file_path.parents and file_path != root:
        raise HTTPException(status_code=400, detail="Invalid download path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
