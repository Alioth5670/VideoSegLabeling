from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import export_service, settings
from app.utils.paths import project_dir

router = APIRouter(prefix="/api/projects/{project_id}", tags=["exports"])


class ExportRequest(BaseModel):
    format: str


@router.post("/export")
def export(project_id: str, payload: ExportRequest) -> dict:
    try:
        path = export_service.export(project_id, payload.format)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rel = path.relative_to(project_dir(settings.projects_dir, project_id)).as_posix()
    return {"download_url": f"/api/projects/{project_id}/download/{rel}"}


@router.get("/download/{path:path}")
def download(project_id: str, path: str) -> FileResponse:
    root = project_dir(settings.projects_dir, project_id).resolve()
    file_path = (root / path).resolve()
    if root not in file_path.parents and file_path != root:
        raise HTTPException(status_code=400, detail="Invalid download path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
