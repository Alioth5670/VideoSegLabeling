from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import annotations, exports, projects, sam, videos
from app.api.deps import sam_service
from app.config import get_settings


settings = get_settings()

app = FastAPI(title="Video Segmentation Labeling", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(videos.router)
app.include_router(sam.status_router)
app.include_router(sam.router)
app.include_router(annotations.router)
app.include_router(exports.router)
app.mount("/projects", StaticFiles(directory=str(settings.projects_dir)), name="projects")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "sam_backend": sam_service.backend_name(),
        "sam_device": sam_service.device_name(),
        "sam_devices": sam_service.available_devices(),
        "sam_fallback_error": sam_service.fallback_error(),
    }


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
