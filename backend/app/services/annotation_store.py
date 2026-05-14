import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.color import color_for_object
from app.utils.project_registry import project_root
from app.utils.paths import video_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnnotationStore:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir

    def project_dir(self, project_id: str) -> Path:
        return project_root(self.projects_dir, project_id)

    def annotations_path(self, project_id: str, video_id: str | None = None) -> Path:
        if video_id:
            return video_dir(self.projects_dir, project_id, video_id) / "annotations.json"
        active_video_id = self._active_video_id(project_id)
        if active_video_id:
            return video_dir(self.projects_dir, project_id, active_video_id) / "annotations.json"
        return self.project_dir(project_id) / "annotations.json"

    def init_annotations(self, project_id: str, video_id: str | None = None) -> dict[str, Any]:
        data = self._default_annotations(project_id, video_id)
        self.save(project_id, data, video_id)
        return data

    def load(self, project_id: str, video_id: str | None = None) -> dict[str, Any]:
        path = self.annotations_path(project_id, video_id)
        if not path.exists():
            return self.init_annotations(project_id, video_id)
        return self._normalize(json.loads(path.read_text(encoding="utf-8")), project_id, video_id)

    def save(self, project_id: str, data: dict[str, Any], video_id: str | None = None) -> None:
        path = self.annotations_path(project_id, video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def next_object_id(self, data: dict[str, Any]) -> int:
        ids = [int(k) for k in data.get("objects", {}).keys()]
        return max(ids, default=0) + 1

    def ensure_object(self, project_id: str, object_id: int | None, category: str | None, frame_index: int = 0, video_id: str | None = None) -> dict[str, Any]:
        data = self.load(project_id, video_id)
        if object_id is None:
            object_id = self.next_object_id(data)
        key = str(object_id)
        objects = data.setdefault("objects", {})
        if key not in objects:
            color = color_for_object(object_id)
            objects[key] = {
                "object_id": object_id,
                "track_id": object_id,
                "category": category or f"object {object_id}",
                "color": list(color),
                "visible": True,
                "locked": False,
                "created_frame": frame_index,
            }
        elif category:
            objects[key]["category"] = category
        self.save(project_id, data, video_id)
        return objects[key]

    def add_prompt(self, project_id: str, prompt: dict[str, Any], video_id: str | None = None) -> None:
        data = self.load(project_id, video_id)
        data.setdefault("prompts", []).append(prompt)
        self.save(project_id, data, video_id)

    def save_frame_object(self, project_id: str, frame_index: int, annotation: dict[str, Any], is_keyframe: bool, video_id: str | None = None) -> None:
        data = self.load(project_id, video_id)
        frame = data.setdefault("frames", {}).setdefault(str(frame_index), {"objects": {}})
        existing = frame.get("objects", {}).get(str(annotation["object_id"]))
        if existing and "locked" not in annotation:
            annotation["locked"] = bool(existing.get("locked", False))
        frame["objects"][str(annotation["object_id"])] = annotation
        if is_keyframe:
            pair = {"frame_index": frame_index, "object_id": annotation["object_id"]}
            keyframes = data.setdefault("keyframes", [])
            if pair not in keyframes:
                keyframes.append(pair)
        self.save(project_id, data, video_id)

    def update_frame_object(self, project_id: str, frame_index: int, object_id: int, patch: dict[str, Any], video_id: str | None = None) -> dict[str, Any]:
        data = self.load(project_id, video_id)
        frame_key = str(frame_index)
        object_key = str(object_id)
        frame = data.get("frames", {}).get(frame_key)
        if not frame or object_key not in frame.get("objects", {}):
            raise KeyError((frame_index, object_id))
        annotation = frame["objects"][object_key]
        for field in ["locked"]:
            if patch.get(field) is not None:
                annotation[field] = patch[field]
        self.save(project_id, data, video_id)
        return annotation

    def delete_frame_object(self, project_id: str, frame_index: int, object_id: int, video_id: str | None = None) -> bool:
        data = self.load(project_id, video_id)
        frame_key = str(frame_index)
        object_key = str(object_id)
        frame = data.get("frames", {}).get(frame_key)
        if not frame or object_key not in frame.get("objects", {}):
            return False
        annotation = frame["objects"].pop(object_key, None)
        if not frame.get("objects"):
            data.get("frames", {}).pop(frame_key, None)
        data["keyframes"] = [
            keyframe
            for keyframe in data.get("keyframes", [])
            if keyframe["frame_index"] != frame_index or keyframe["object_id"] != object_id
        ]
        self.save(project_id, data, video_id)
        self._delete_mask_file(project_id, annotation)
        return True

    def delete_object_if_unreferenced(self, project_id: str, object_id: int, video_id: str | None = None) -> bool:
        data = self.load(project_id, video_id)
        key = str(object_id)
        for frame in data.get("frames", {}).values():
            if key in frame.get("objects", {}):
                return False
        if key not in data.get("objects", {}):
            return False
        data["objects"].pop(key, None)
        data["keyframes"] = [k for k in data.get("keyframes", []) if k["object_id"] != object_id]
        data["prompts"] = [p for p in data.get("prompts", []) if p.get("object_id") != object_id]
        self.save(project_id, data, video_id)
        return True

    def batch_delete(
        self,
        project_id: str,
        start_frame: int,
        end_frame: int,
        object_ids: list[int] | None = None,
        delete_annotations: bool = True,
        delete_prompts: bool = True,
        video_id: str | None = None,
    ) -> dict[str, Any]:
        data = self.load(project_id, video_id)
        lower = min(start_frame, end_frame)
        upper = max(start_frame, end_frame)
        selected_ids = {int(object_id) for object_id in object_ids} if object_ids else None
        deleted_annotations: list[dict[str, Any]] = []
        deleted_annotation_count = 0
        affected_frames: set[int] = set()

        if delete_annotations:
            for frame_key in list(data.get("frames", {}).keys()):
                try:
                    frame_index = int(frame_key)
                except ValueError:
                    continue
                if frame_index < lower or frame_index > upper:
                    continue
                frame = data.get("frames", {}).get(frame_key, {})
                objects = frame.get("objects", {})
                for object_key in list(objects.keys()):
                    try:
                        object_id = int(object_key)
                    except ValueError:
                        continue
                    if selected_ids is not None and object_id not in selected_ids:
                        continue
                    annotation = objects.pop(object_key, None)
                    if annotation:
                        deleted_annotations.append(annotation)
                        deleted_annotation_count += 1
                        affected_frames.add(frame_index)
                if not objects:
                    data.get("frames", {}).pop(frame_key, None)

            data["keyframes"] = [
                keyframe
                for keyframe in data.get("keyframes", [])
                if not (
                    lower <= (self._optional_int(keyframe.get("frame_index")) or -1) <= upper
                    and (selected_ids is None or (self._optional_int(keyframe.get("object_id")) or -1) in selected_ids)
                )
            ]

        deleted_prompt_count = 0
        if delete_prompts:
            kept_prompts = []
            for prompt in data.get("prompts", []):
                frame_index = self._optional_int(prompt.get("frame_index"))
                if frame_index is None:
                    kept_prompts.append(prompt)
                    continue
                object_id = self._optional_int(prompt.get("object_id"))
                prompt_matches = lower <= frame_index <= upper and (
                    selected_ids is None or (object_id is not None and object_id in selected_ids)
                )
                if prompt_matches:
                    deleted_prompt_count += 1
                    affected_frames.add(frame_index)
                else:
                    kept_prompts.append(prompt)
            data["prompts"] = kept_prompts

        deleted_object_ids = self._drop_unreferenced_objects(data)
        self.save(project_id, data, video_id)
        for annotation in deleted_annotations:
            self._delete_mask_file(project_id, annotation)
        return {
            "deleted_annotations": deleted_annotation_count,
            "deleted_prompts": deleted_prompt_count,
            "deleted_object_ids": deleted_object_ids,
            "affected_frames": sorted(affected_frames),
        }

    def frame_annotations(self, project_id: str, frame_index: int, video_id: str | None = None) -> dict[str, Any]:
        data = self.load(project_id, video_id)
        return {"frame_index": frame_index, "objects": data.get("frames", {}).get(str(frame_index), {"objects": {}})["objects"]}

    def update_object(self, project_id: str, object_id: int, patch: dict[str, Any], video_id: str | None = None) -> dict[str, Any]:
        data = self.load(project_id, video_id)
        key = str(object_id)
        objects = data.setdefault("objects", {})
        if key not in objects:
            raise KeyError(object_id)
        for field in ["category", "visible", "locked", "color"]:
            if patch.get(field) is not None:
                objects[key][field] = patch[field]
        self.save(project_id, data, video_id)
        return objects[key]

    def delete_object(self, project_id: str, object_id: int, video_id: str | None = None) -> None:
        data = self.load(project_id, video_id)
        key = str(object_id)
        data["objects"].pop(key, None)
        empty_frames: list[str] = []
        deleted_annotations: list[dict[str, Any]] = []
        for frame_key, frame in data.get("frames", {}).items():
            annotation = frame.get("objects", {}).pop(key, None)
            if annotation:
                deleted_annotations.append(annotation)
            if not frame.get("objects"):
                empty_frames.append(frame_key)
        for frame_key in empty_frames:
            data.get("frames", {}).pop(frame_key, None)
        data["keyframes"] = [k for k in data.get("keyframes", []) if k["object_id"] != object_id]
        data["prompts"] = [p for p in data.get("prompts", []) if p.get("object_id") != object_id]
        self.save(project_id, data, video_id)
        for annotation in deleted_annotations:
            self._delete_mask_file(project_id, annotation)

    def nearest_object_mask(self, project_id: str, object_id: int, start_frame: int, video_id: str | None = None) -> tuple[int, dict[str, Any]] | None:
        data = self.load(project_id, video_id)
        candidates: list[tuple[int, dict[str, Any]]] = []
        for frame_key, frame in data.get("frames", {}).items():
            obj = frame.get("objects", {}).get(str(object_id))
            if obj:
                candidates.append((int(frame_key), obj))
        if not candidates:
            return None
        return min(candidates, key=lambda item: abs(item[0] - start_frame))

    def _default_annotations(self, project_id: str, video_id: str | None = None) -> dict[str, Any]:
        return {"project_id": project_id, "video_id": video_id, "objects": {}, "frames": {}, "prompts": [], "keyframes": []}

    def _normalize(self, data: dict[str, Any], project_id: str, video_id: str | None = None) -> dict[str, Any]:
        normalized = self._default_annotations(project_id, video_id)
        if isinstance(data, dict):
            normalized.update(data)
        normalized["project_id"] = normalized.get("project_id") or project_id
        normalized["video_id"] = normalized.get("video_id") or video_id
        for key, default in self._default_annotations(project_id).items():
            if key not in normalized or normalized[key] is None:
                normalized[key] = default
        if not isinstance(normalized["objects"], dict):
            normalized["objects"] = {}
        if not isinstance(normalized["frames"], dict):
            normalized["frames"] = {}
        if not isinstance(normalized["prompts"], list):
            normalized["prompts"] = []
        if not isinstance(normalized["keyframes"], list):
            normalized["keyframes"] = []
        return normalized

    def _active_video_id(self, project_id: str) -> str | None:
        project_file = self.project_dir(project_id) / "project.json"
        if not project_file.exists():
            return None
        project = json.loads(project_file.read_text(encoding="utf-8"))
        return project.get("active_video_id")

    def _drop_unreferenced_objects(self, data: dict[str, Any]) -> list[int]:
        referenced: set[str] = set()
        for frame in data.get("frames", {}).values():
            referenced.update(frame.get("objects", {}).keys())
        deleted: list[int] = []
        for object_key in list(data.get("objects", {}).keys()):
            if object_key in referenced:
                continue
            data.get("objects", {}).pop(object_key, None)
            try:
                deleted.append(int(object_key))
            except ValueError:
                continue
        if deleted:
            deleted_set = set(deleted)
            data["keyframes"] = [k for k in data.get("keyframes", []) if int(k.get("object_id", -1)) not in deleted_set]
            data["prompts"] = [p for p in data.get("prompts", []) if self._optional_int(p.get("object_id")) not in deleted_set]
        return deleted

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _delete_mask_file(self, project_id: str, annotation: dict[str, Any] | None) -> None:
        if not annotation:
            return
        mask = annotation.get("mask_path")
        if not isinstance(mask, str) or not mask:
            return
        root = self.project_dir(project_id).resolve()
        path = (root / mask).resolve()
        if root not in path.parents and path != root:
            return
        path.unlink(missing_ok=True)
