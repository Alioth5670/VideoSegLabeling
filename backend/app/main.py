from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlsplit
import re
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import annotations, auth, exports, projects, sam, videos
from app.api.deps import sam_service, account_store, video_service, export_jobs
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

@app.middleware("http")
async def protect_data(request: Request, call_next):
    path = request.url.path
    if path == "/projects" or path.startswith("/projects/"):
        return JSONResponse({"detail": "请使用受保护的项目 API"}, status_code=404)
    if path.startswith("/api/"):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "不允许跨站修改数据"}, status_code=403)
        public = {"/api/auth/status", "/api/auth/setup", "/api/auth/login"}
        if path not in public:
            user = account_store.current_user(request.cookies.get(auth.COOKIE, ""))
            if not user:
                return JSONResponse({"detail": "请先登录"}, status_code=401)
            request.state.user = user
            match = re.match(r"^/api/projects/([^/]+)", path)
            if match:
                restoring = request.method == 'POST' and path == f'/api/projects/{match[1]}/restore'
                purging = request.method == 'DELETE' and path == f'/api/projects/{match[1]}/permanent'
                record = account_store.project_record(match[1], include_deleted=restoring or purging)
                if not record or (not user['admin'] and record['owner_id'] != user['id']):
                    return JSONResponse({'detail': '项目不存在'}, status_code=404)
            if match:
                video_id = request.query_params.get("video_id")
                if video_id:
                    project = video_service.load_project(match[1])
                    if not any(v.get("video_id") == video_id for v in project.get("videos", [])):
                        return JSONResponse({"detail": "视频不存在"}, status_code=404)
            if (path.startswith("/api/sam/") or path.endswith("/sam/backend")) and not (path == "/api/sam/resources" and request.method == "GET") and not user["admin"]:
                return JSONResponse({"detail": "需要管理员权限"}, status_code=403)
    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(videos.router)
app.include_router(sam.status_router)
app.include_router(sam.router)
app.include_router(annotations.router)
app.include_router(exports.router)



@app.on_event("shutdown")
def stop_export_workers() -> None:
    export_jobs.shutdown()
    sam_service.shutdown()


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
