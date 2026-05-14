import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import cv2
from fastapi import UploadFile

from app.utils.project_registry import load_project_paths, project_root, register_project_dir


VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm"}


class VideoService:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir

    def create_project(self, name: str, project_dir: str | None = None) -> dict:
        project_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        root = self._new_project_root(project_id, project_dir)
        root.mkdir(parents=True, exist_ok=True)
        if (root / "project.json").exists():
            raise FileExistsError(root / "project.json")
        register_project_dir(self.projects_dir, project_id, root)
        project = {
            "project_id": project_id,
            "name": name,
            "videos": [],
            "active_video_id": None,
            "video_path": None,
            "frames_dir": None,
            "fps": 0,
            "width": 0,
            "height": 0,
            "frame_count": 0,
            "duration": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.save_project(project_id, project)
        return self._with_paths(project)

    def list_projects(self) -> list[dict]:
        project_paths: dict[str, Path] = {}
        for path in sorted(self.projects_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_dir():
                continue
            project_file = path / "project.json"
            if project_file.exists():
                data = json.loads(project_file.read_text(encoding="utf-8"))
                project_id = data.get("project_id")
                if project_id:
                    project_paths[project_id] = path
        for project_id, path in load_project_paths(self.projects_dir).items():
            project_paths.setdefault(project_id, Path(path))
        projects: list[dict] = []
        for path in sorted(project_paths.values(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
            project_file = path / "project.json"
            if project_file.exists():
                projects.append(self._with_paths(json.loads(project_file.read_text(encoding="utf-8"))))
        return projects

    def project_path(self, project_id: str) -> Path:
        return project_root(self.projects_dir, project_id)

    def project_json_path(self, project_id: str) -> Path:
        return self.project_path(project_id) / "project.json"

    def load_project(self, project_id: str) -> dict:
        path = self.project_json_path(project_id)
        if not path.exists():
            raise FileNotFoundError(project_id)
        return self._with_paths(json.loads(path.read_text(encoding="utf-8")))

    def save_project(self, project_id: str, project: dict) -> None:
        saved = {**project}
        saved.pop("paths", None)
        saved.setdefault("videos", [])
        saved.setdefault("active_video_id", None)
        saved["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.project_json_path(project_id).write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")

    async def save_upload_and_decode(self, project_id: str, upload: UploadFile, relative_path: str | None = None) -> dict:
        return await self._save_upload_and_decode(project_id, upload, relative_path)

    async def save_folder_uploads_and_decode(self, project_id: str, uploads: list[UploadFile]) -> dict:
        saved = 0
        last_error: Exception | None = None
        for upload in uploads:
            if not self._is_video_filename(upload.filename):
                continue
            try:
                await self._save_upload_and_decode(project_id, upload, upload.filename)
                saved += 1
            except Exception as exc:
                last_error = exc
        if saved == 0:
            if last_error:
                raise last_error
            raise ValueError("No video files found in uploaded folder")
        return self.load_project(project_id)

    async def _save_upload_and_decode(self, project_id: str, upload: UploadFile, relative_path: str | None) -> dict:
        root = self.project_path(project_id)
        root.mkdir(parents=True, exist_ok=True)
        project = self.load_project(project_id)
        video_id = uuid.uuid4().hex[:12]
        suffix = Path(upload.filename or "").suffix.lower() or ".mp4"
        video_name = Path(upload.filename or f"video{suffix}").name
        normalized_relative_path = self._normalize_relative_video_path(relative_path, video_name)
        storage_dir = self._storage_dir_for_upload(video_id, normalized_relative_path)
        video_root = root / storage_dir
        if video_root.exists():
            storage_dir = self._dedupe_storage_dir(root, storage_dir)
            video_root = root / storage_dir
        for folder in ["frames", "masks", "overlays", "exports"]:
            (video_root / folder).mkdir(parents=True, exist_ok=True)
        video_path = video_root / video_name
        with video_path.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
        info = self.decode_video(project_id, video_path, video_id, video_root)
        now = datetime.now(timezone.utc).isoformat()
        video = {
            "video_id": video_id,
            "name": video_name,
            "relative_path": normalized_relative_path,
            "storage_dir": storage_dir.as_posix(),
            "video_path": (storage_dir / video_path.name).as_posix(),
            "frames_dir": (storage_dir / "frames").as_posix(),
            "masks_dir": (storage_dir / "masks").as_posix(),
            "overlays_dir": (storage_dir / "overlays").as_posix(),
            "created_at": now,
            "updated_at": now,
            **info,
        }
        videos = project.setdefault("videos", [])
        videos.append(video)
        project["active_video_id"] = video_id
        self._apply_active_video(project, video)
        self.save_project(project_id, project)
        self.cleanup_empty_legacy_assets(project_id)
        return self._with_paths(project)

    def decode_video(self, project_id: str, video_path: Path, video_id: str | None = None, video_root: Path | None = None) -> dict:
        base = video_root or self.video_path(project_id, video_id)
        frames_dir = base / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError("Could not open uploaded video")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imwrite(str(frames_dir / f"{frame_index:06d}.jpg"), frame)
            frame_index += 1
        cap.release()
        duration = frame_index / fps if fps > 0 else 0
        return {"fps": fps, "width": width, "height": height, "frame_count": frame_index, "duration": duration}

    def list_videos(self, project_id: str) -> list[dict]:
        return self.load_project(project_id).get("videos", [])

    def active_video_id(self, project_id: str, video_id: str | None = None) -> str | None:
        if video_id:
            return video_id
        project = self.load_project(project_id)
        return project.get("active_video_id") or (project.get("videos") or [{}])[0].get("video_id")

    def video_path(self, project_id: str, video_id: str | None = None) -> Path:
        root = self.project_path(project_id)
        if not video_id:
            return root
        project_path = self.project_json_path(project_id)
        project = json.loads(project_path.read_text(encoding="utf-8")) if project_path.exists() else {}
        return self._video_path_from_project(root, video_id, project)

    def _video_path_from_project(self, root: Path, video_id: str, project: dict) -> Path:
        for video in project.get("videos", []):
            if video.get("video_id") == video_id:
                return root / (video.get("storage_dir") or f"videos/{video_id}")
        return root / "videos" / video_id

    def video_info(self, project_id: str, video_id: str | None = None) -> dict | None:
        project = self.load_project(project_id)
        resolved = video_id or project.get("active_video_id")
        for video in project.get("videos", []):
            if video.get("video_id") == resolved:
                return video
        if not project.get("videos") and project.get("video_path"):
            return {**project, "video_id": None, "name": project.get("name", "video")}
        return None

    def set_active_video(self, project_id: str, video_id: str) -> dict:
        project = self.load_project(project_id)
        video = next((item for item in project.get("videos", []) if item.get("video_id") == video_id), None)
        if video is None:
            raise KeyError(video_id)
        project["active_video_id"] = video_id
        self._apply_active_video(project, video)
        self.save_project(project_id, project)
        return self._with_paths(project)

    def _with_paths(self, project: dict) -> dict:
        project_id = project.get("project_id")
        if not project_id:
            return project
        root = self.project_path(project_id).resolve()
        enriched = {**project}
        enriched["paths"] = {
            "projects_dir": str(self.projects_dir.resolve()),
            "project_dir": str(root),
            "project_json": str((root / "project.json").resolve()),
        }
        active_video_id = project.get("active_video_id")
        if active_video_id:
            video_root = self._video_path_from_project(root, active_video_id, project)
            enriched["paths"]["active_video_dir"] = str(video_root.resolve())
            enriched["paths"]["active_frames_dir"] = str((video_root / "frames").resolve())
            enriched["paths"]["active_masks_dir"] = str((video_root / "masks").resolve())
            enriched["paths"]["active_exports_dir"] = str((video_root / "exports").resolve())
        return enriched

    def _new_project_root(self, project_id: str, project_dir: str | None) -> Path:
        if project_dir and project_dir.strip():
            return Path(project_dir).expanduser().resolve()
        return self.projects_dir / project_id


    def _apply_active_video(self, project: dict, video: dict) -> None:
        for field in ["video_path", "frames_dir", "fps", "width", "height", "frame_count", "duration"]:
            project[field] = video.get(field)

    def _normalize_relative_video_path(self, relative_path: str | None, fallback_name: str) -> str | None:
        if not relative_path:
            return None
        pure = PurePosixPath(relative_path.replace("\\", "/"))
        parts = [self._safe_path_part(part) for part in pure.parts if part not in {"", ".", ".."}]
        if not parts:
            return fallback_name
        parts[-1] = self._safe_file_name(parts[-1]) or fallback_name
        return PurePosixPath(*parts).as_posix()

    def _storage_dir_for_upload(self, video_id: str, relative_path: str | None) -> Path:
        if not relative_path:
            return Path("videos") / video_id
        pure = PurePosixPath(relative_path)
        parts = list(pure.with_suffix("").parts)
        return Path("videos", *parts)

    def _dedupe_storage_dir(self, root: Path, storage_dir: Path) -> Path:
        suffix = uuid.uuid4().hex[:8]
        return storage_dir.with_name(f"{storage_dir.name}_{suffix}")

    def _safe_path_part(self, value: str) -> str:
        cleaned = "".join(char if char not in '\\/:*?"<>|' else "_" for char in value.strip())
        return cleaned or "_"

    def _safe_file_name(self, value: str) -> str:
        path = Path(self._safe_path_part(value)).name
        return path or "video.mp4"

    def _is_video_filename(self, filename: str | None) -> bool:
        return Path(filename or "").suffix.lower() in VIDEO_EXTENSIONS

    def cleanup_empty_legacy_assets(self, project_id: str) -> None:
        root = self.project_path(project_id)
        annotations_path = root / "annotations.json"
        if annotations_path.exists():
            data = json.loads(annotations_path.read_text(encoding="utf-8"))
            has_annotations = any(data.get(key) for key in ["objects", "frames", "prompts", "keyframes"])
            if has_annotations:
                return
            annotations_path.unlink()
        for folder in ["frames", "masks", "overlays"]:
            path = root / folder
            if path.exists():
                shutil.rmtree(path)

    def _clear_generated_assets(self, root: Path) -> None:
        for folder in ["frames", "masks", "overlays", "exports"]:
            path = root / folder
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
