import json
import zipfile
from pathlib import Path

from app.utils.rle import encode_rle
from app.utils.mask import read_mask_png
from app.utils.project_registry import project_root
from app.utils.paths import video_dir


class ExportService:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir

    def export(self, project_id: str, export_format: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        project = json.loads((root / "project.json").read_text(encoding="utf-8"))
        active_video_id = project.get("active_video_id")
        video_root = video_dir(self.projects_dir, project_id, active_video_id) if active_video_id else root
        annotations_path = video_root / "annotations.json"
        out_dir = video_root / "exports"
        out_dir.mkdir(exist_ok=True)
        if export_format == "project_json":
            out = out_dir / "project_json.zip"
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(root / "project.json", "project.json")
                zf.write(annotations_path, "annotations.json")
            return out
        if export_format == "mask_png":
            out = out_dir / "mask_png.zip"
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for mask in (video_root / "masks").rglob("*.png"):
                    zf.write(mask, mask.relative_to(root).as_posix())
            return out
        if export_format == "coco_video_json":
            return self._export_coco(project_id)
        if export_format == "all_videos_zip":
            return self._export_all_videos(project_id)
        raise ValueError(export_format)

    def _export_coco(self, project_id: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        project = json.loads((root / "project.json").read_text(encoding="utf-8"))
        active_video_id = project.get("active_video_id")
        video_root = video_dir(self.projects_dir, project_id, active_video_id) if active_video_id else root
        video = self._active_video(project)
        payload = self._coco_payload(root, video_root, video)
        out_json = video_root / "exports" / "coco_video.json"
        out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        out_zip = video_root / "exports" / "coco_video_json.zip"
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(out_json, "coco_video.json")
        return out_zip

    def _export_all_videos(self, project_id: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        project = json.loads((root / "project.json").read_text(encoding="utf-8"))
        out_dir = root / "exports"
        out_dir.mkdir(exist_ok=True)
        out = out_dir / "all_videos.zip"
        videos = project.get("videos") or [self._legacy_video(project)]
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(root / "project.json", "project.json")
            summary = []
            merged_videos = []
            merged_annotations = []
            next_ann_id = 1
            for index, video in enumerate(videos):
                video_id = video.get("video_id") or "legacy"
                video_root = video_dir(self.projects_dir, project_id, video_id) if video.get("video_id") else root
                storage_dir = video.get("storage_dir")
                if isinstance(storage_dir, str) and storage_dir.startswith("videos/"):
                    prefix = storage_dir
                else:
                    prefix = f"videos/{index:03d}_{self._safe_name(video.get('name') or video_id)}"
                zf.writestr(f"{prefix}/video.json", json.dumps(video, indent=2, ensure_ascii=False))
                video_record = self._coco_video_record(video)
                merged_videos.append(video_record)

                annotations_path = video_root / "annotations.json"
                annotation_count = 0
                if annotations_path.exists():
                    coco_annotations = self._coco_annotations(root, video_root, video)
                    annotation_count = len(coco_annotations)
                    zf.write(annotations_path, f"{prefix}/annotations.json")
                    zf.writestr(
                        f"{prefix}/coco_video.json",
                        json.dumps({"videos": [video_record], "annotations": coco_annotations}, indent=2, ensure_ascii=False),
                    )
                    for ann in coco_annotations:
                        merged_annotations.append({
                            **ann,
                            "id": next_ann_id,
                        })
                        next_ann_id += 1

                masks_dir = video_root / "masks"
                if masks_dir.exists():
                    for mask in masks_dir.rglob("*.png"):
                        zf.write(mask, f"{prefix}/{mask.relative_to(video_root).as_posix()}")
                summary.append({
                    "video_id": video.get("video_id"),
                    "name": video.get("name"),
                    "frame_count": video.get("frame_count", 0),
                    "annotation_count": annotation_count,
                    "folder": prefix,
                })
            zf.writestr("summary.json", json.dumps({"videos": summary}, indent=2, ensure_ascii=False))
            zf.writestr(
                "coco_all_videos.json",
                json.dumps({"videos": merged_videos, "annotations": merged_annotations}, indent=2, ensure_ascii=False),
            )
        return out

    def _coco_payload(self, root: Path, video_root: Path, video: dict) -> dict:
        return {
            "videos": [self._coco_video_record(video)],
            "annotations": self._coco_annotations(root, video_root, video),
        }

    def _coco_video_record(self, video: dict) -> dict:
        video_id = video.get("video_id") or "legacy"
        return {
            "id": video_id,
            "name": video.get("name") or video_id,
            "file_name": video.get("video_path"),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": float(video.get("fps") or 0),
            "frame_count": int(video.get("frame_count") or 0),
            "duration": float(video.get("duration") or 0),
        }

    def _coco_annotations(self, root: Path, video_root: Path, video: dict) -> list[dict]:
        data = json.loads((video_root / "annotations.json").read_text(encoding="utf-8"))
        annotations = []
        ann_id = 1
        video_id = video.get("video_id") or "legacy"
        for frame_idx, frame in data.get("frames", {}).items():
            for object_id, obj in frame.get("objects", {}).items():
                mask = read_mask_png(root / obj["mask_path"])
                annotations.append({
                    "id": ann_id,
                    "video_id": video_id,
                    "frame_index": int(frame_idx),
                    "object_id": int(object_id),
                    "track_id": obj["track_id"],
                    "bbox": obj["bbox"],
                    "area": obj["area"],
                    "segmentation": encode_rle(mask),
                })
                ann_id += 1
        return annotations

    def _active_video(self, project: dict) -> dict:
        active_video_id = project.get("active_video_id")
        for video in project.get("videos", []):
            if video.get("video_id") == active_video_id:
                return video
        return self._legacy_video(project)

    def _legacy_video(self, project: dict) -> dict:
        return {
            "video_id": None,
            "name": project.get("name", "legacy"),
            "video_path": project.get("video_path"),
            "frames_dir": project.get("frames_dir"),
            "fps": project.get("fps", 0),
            "width": project.get("width", 0),
            "height": project.get("height", 0),
            "frame_count": project.get("frame_count", 0),
            "duration": project.get("duration", 0),
        }

    def _safe_name(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
