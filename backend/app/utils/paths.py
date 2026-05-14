from pathlib import Path
import json

from app.utils.project_registry import project_root


def project_dir(projects_dir: Path, project_id: str) -> Path:
    return project_root(projects_dir, project_id)


def video_dir(projects_dir: Path, project_id: str, video_id: str | None = None) -> Path:
    root = project_dir(projects_dir, project_id)
    if not video_id:
        return root
    project_file = root / "project.json"
    if project_file.exists():
        project = json.loads(project_file.read_text(encoding="utf-8"))
        for video in project.get("videos", []):
            if video.get("video_id") == video_id:
                return root / (video.get("storage_dir") or f"videos/{video_id}")
    return root / "videos" / video_id


def frame_path(projects_dir: Path, project_id: str, frame_index: int, video_id: str | None = None) -> Path:
    return video_dir(projects_dir, project_id, video_id) / "frames" / f"{frame_index:06d}.jpg"


def mask_path(projects_dir: Path, project_id: str, object_id: int, frame_index: int, video_id: str | None = None) -> Path:
    return video_dir(projects_dir, project_id, video_id) / "masks" / f"object_{object_id}" / f"{frame_index:06d}.png"


def rel_to_project(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
