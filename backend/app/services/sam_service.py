import sys
import time
import uuid
import inspect
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import Settings
from app.services.annotation_store import AnnotationStore
from app.utils.mask import area_from_mask, bbox_from_mask, read_mask_png


class SAMService:
    def __init__(self, config: Settings, store: AnnotationStore):
        self.config = config
        self.store = store
        self._model: Any | None = None
        self._sessions: dict[str, dict[str, Any]] = {}
        self._active_backend = config.sam_backend
        self._active_device = self._normalize_device(config.sam_device)
        self._fallback_error: str | None = None

    def load_model(self) -> None:
        if self._active_backend == "mock" or self._model is not None:
            return
        self._activate_torch_device()
        if str(self.config.sam_repo_path) not in sys.path:
            sys.path.insert(0, str(self.config.sam_repo_path))
        from sam3.model_builder import build_sam3_predictor

        attempts: list[tuple[str, Any, Path]] = []
        if self._active_backend == "sam3_multiplex_video":
            attempts.append(("sam3_multiplex_video", "sam3.1", self.config.sam31_checkpoint_path))
            attempts.append(("sam3_video", "sam3", self.config.sam_checkpoint_path))
        elif self._active_backend == "sam3_video":
            attempts.append(("sam3_video", "sam3", self.config.sam_checkpoint_path))
        else:
            raise RuntimeError(f"Unsupported SAM_BACKEND={self._active_backend}")

        errors: list[str] = []
        for backend, version, checkpoint in attempts:
            try:
                with self._torch_device_context():
                    self._model = build_sam3_predictor(
                        checkpoint_path=str(checkpoint),
                        version=version,
                        use_fa3=False,
                        use_rope_real=False,
                        compile=False,
                        warm_up=False,
                        async_loading_frames=False,
                    )
                self._active_backend = backend
                self._configure_interactive_video_tracking()
                self._fallback_error = None
                return
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
        self._active_backend = "mock"
        self._model = None
        self._fallback_error = self._format_fallback_error("real SAM backend failed", " | ".join(errors))
        print(f"Warning: {self._fallback_error}")

    def backend_name(self) -> str:
        return self._active_backend

    def device_name(self) -> str:
        return self._active_device

    def fallback_error(self) -> str | None:
        return self._fallback_error

    def available_devices(self) -> list[dict[str, Any]]:
        try:
            import torch

            if not torch.cuda.is_available():
                return [{"id": "cpu", "label": "CPU", "available": True}]
            devices = []
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                devices.append({
                    "id": f"cuda:{index}",
                    "index": index,
                    "label": f"cuda:{index} - {props.name}",
                    "total_memory_mb": props.total_memory // 1024 // 1024,
                    "available": True,
                })
            return devices
        except Exception as exc:
            return [{"id": self._active_device, "label": f"{self._active_device} ({exc})", "available": False}]

    def set_device(self, device: str) -> str:
        normalized = self._normalize_device(device)
        self._validate_device(normalized)
        if normalized != self._active_device:
            self._close_real_sessions()
            self._sessions.clear()
            self._model = None
            self._active_device = normalized
            self._fallback_error = None
        return self._active_device

    def set_backend(self, backend: str) -> str:
        allowed = {"mock", "sam3_video", "sam3_multiplex_video"}
        if backend not in allowed:
            raise ValueError(f"Unsupported SAM backend: {backend}")
        if backend != self._active_backend:
            self._close_real_sessions()
            self._sessions.clear()
            self._model = None
            self._active_backend = backend
            self._fallback_error = None
        return self._active_backend

    def is_video_supported(self) -> bool:
        return self._active_backend in {"mock", "sam3_video", "sam3_multiplex_video"}

    def is_multiplex_supported(self) -> bool:
        return self._active_backend == "sam3_multiplex_video"

    def start_video_session(self, project_id: str, video_path: str, frames_dir: str) -> str:
        session_id = uuid.uuid4().hex
        if self._active_backend == "mock":
            self._sessions[session_id] = {"project_id": project_id, "frames_dir": frames_dir}
            return session_id
        self.load_model()
        if self._active_backend == "mock":
            self._sessions[session_id] = {"project_id": project_id, "frames_dir": frames_dir}
            return session_id
        try:
            self._close_real_sessions()
            return self._start_real_session(frames_dir)
        except Exception as exc:
            self._active_backend = "mock"
            self._model = None
            self._fallback_error = self._format_fallback_error("real SAM session failed", str(exc))
            print(f"Warning: {self._fallback_error}")
            self._sessions[session_id] = {"project_id": project_id, "frames_dir": frames_dir, "fallback_error": self._fallback_error}
            return session_id

    def segment_frame(
        self,
        project_id: str,
        session_id: str | None,
        frame_index: int,
        image_path: str,
        object_id: int | None,
        text: str | None = None,
        box: list[float] | None = None,
        points: list[dict] | None = None,
        mask: np.ndarray | None = None,
        category: str | None = None,
    ) -> list[dict]:
        if self._active_backend != "mock":
            return self._real_segment(frame_index, image_path, session_id, object_id, text, box, points or [])
        return self._mock_segment(project_id, frame_index, image_path, object_id, text, box, points or [], mask, category)

    def add_prompt(self, *args: Any, **kwargs: Any) -> dict:
        results = self.segment_frame(*args, **kwargs)
        return {"objects": results}

    def propagate_in_video(
        self,
        project_id: str,
        session_id: str,
        object_ids: list[int] | None,
        start_frame: int,
        end_frame: int,
        direction: str,
        video_id: str | None = None,
        on_frame: Callable[[dict], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict]:
        project = self.store.project_dir(project_id)
        if self._active_backend != "mock":
            return self._real_propagate(session_id, object_ids, start_frame, end_frame, direction, on_frame, should_cancel)
        data = self.store.load(project_id, video_id)
        ids = object_ids or [int(k) for k in data.get("objects", {}).keys()]
        frames: list[dict] = []
        frame_range = self._frame_range(start_frame, end_frame, direction)
        for frame_index in frame_range:
            if should_cancel and should_cancel():
                break
            frame_objects: list[dict] = []
            for object_id in ids:
                if should_cancel and should_cancel():
                    break
                nearest = self.store.nearest_object_mask(project_id, object_id, frame_index, video_id)
                if nearest is None:
                    continue
                _, ann = nearest
                src_mask = project / ann["mask_path"]
                mask = read_mask_png(src_mask)
                frame_objects.append(self._result_from_mask(frame_index, object_id, mask, "mock"))
            if frame_objects:
                frame = {"frame_index": frame_index, "objects": frame_objects}
                if should_cancel and should_cancel():
                    break
                if on_frame:
                    on_frame(frame)
                frames.append(frame)
        return frames

    def remove_object(self, project_id: str, session_id: str, object_id: int) -> None:
        if self._active_backend == "mock" or not session_id:
            return
        if self._model is None:
            raise RuntimeError("SAM model is not loaded.")
        request = {
            "type": "remove_object",
            "session_id": session_id,
            "obj_id": int(object_id),
        }
        with self._torch_device_context():
            self._model.handle_request(request)

    def reset_session(self, project_id: str, session_id: str) -> None:
        if self._active_backend == "mock":
            self._sessions.pop(session_id, None)
            return
        if self._model is None:
            raise RuntimeError("SAM model is not loaded.")
        with self._torch_device_context():
            self._model.handle_request({"type": "reset_session", "session_id": session_id})

    def close_session(self, project_id: str, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _start_real_session(self, frames_dir: str) -> str:
        if self._active_backend == "sam3_multiplex_video":
            init_kwargs: dict[str, Any] = {
                "resource_path": frames_dir,
                "offload_video_to_cpu": True,
                "async_loading_frames": False,
            }
            if "video_loader_type" in inspect.signature(self._model.model.init_state).parameters:
                init_kwargs["video_loader_type"] = getattr(self._model, "video_loader_type", "cv2")
            with self._torch_device_context():
                inference_state = self._model.model.init_state(**init_kwargs)
            session_id = str(uuid.uuid4())
            self._model._all_inference_states[session_id] = {
                "state": inference_state,
                "session_id": session_id,
                "start_time": time.time(),
                "last_use_time": time.time(),
            }
            return session_id
        with self._torch_device_context():
            response = self._model.handle_request({"type": "start_session", "resource_path": frames_dir, "offload_video_to_cpu": True})
        return response["session_id"]

    def _close_real_sessions(self) -> None:
        if self._model is None or not hasattr(self._model, "_all_inference_states"):
            return
        for session_id in list(self._model._all_inference_states.keys()):
            try:
                self._model.handle_request({"type": "close_session", "session_id": session_id})
            except Exception as exc:
                print(f"Warning: failed to close stale SAM session {session_id}: {exc}")
                self._model._all_inference_states.pop(session_id, None)
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _normalize_device(self, device: str | None) -> str:
        value = (device or "cuda:0").strip().lower()
        if value in {"auto", "cuda"}:
            return "cuda:0"
        if value.isdigit():
            return f"cuda:{value}"
        return value

    def _validate_device(self, device: str) -> None:
        if device == "cpu":
            return
        if not device.startswith("cuda:"):
            raise ValueError(f"Unsupported SAM_DEVICE={device}. Use cuda:N, N, auto, or cpu.")
        try:
            index = int(device.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError(f"Unsupported SAM_DEVICE={device}. Use cuda:N.") from exc
        try:
            import torch

            if not torch.cuda.is_available():
                raise ValueError("CUDA is not available in this Python environment.")
            count = torch.cuda.device_count()
            if index < 0 or index >= count:
                raise ValueError(f"CUDA device index {index} is out of range; available devices: 0..{count - 1}.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Could not validate CUDA device {device}: {exc}") from exc

    def _activate_torch_device(self) -> None:
        if self._active_device == "cpu":
            raise RuntimeError("Real SAM3 backends require CUDA because the local SAM3 code calls .cuda(). Use SAM_BACKEND=mock for CPU.")
        self._validate_device(self._active_device)
        import torch

        index = int(self._active_device.split(":", 1)[1])
        torch.cuda.set_device(index)
        print(f"SAM using CUDA device {self._active_device}: {torch.cuda.get_device_name(index)}", flush=True)

    def _torch_device_context(self):
        if self._active_device == "cpu":
            return nullcontext()
        import torch

        index = int(self._active_device.split(":", 1)[1])
        torch.cuda.set_device(index)
        return torch.cuda.device(index)

    def _real_segment(self, frame_index: int, image_path: str, session_id: str | None, object_id: int | None, text: str | None, box: list[float] | None, points: list[dict]) -> list[dict]:
        if not session_id:
            raise RuntimeError("A SAM video session is required for real SAM segmentation.")
        height, width = self._image_shape(image_path)
        if points:
            text = None
            box = None
        request: dict[str, Any] = {
            "type": "add_prompt",
            "session_id": session_id,
            "frame_index": frame_index,
            "text": text,
        }
        if object_id is not None:
            request["obj_id"] = object_id
        if box:
            x1, y1, x2, y2 = box
            x1 = max(0.0, min(float(width), float(x1)))
            x2 = max(0.0, min(float(width), float(x2)))
            y1 = max(0.0, min(float(height), float(y1)))
            y2 = max(0.0, min(float(height), float(y2)))
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            if x2 - x1 < 1 or y2 - y1 < 1:
                raise RuntimeError(f"Box prompt is too small after clamping: {[x1, y1, x2, y2]}")
            request["bounding_boxes"] = [[
                x1 / width,
                y1 / height,
                (x2 - x1) / width,
                (y2 - y1) / height,
            ]]
            request["bounding_box_labels"] = [1]
            request["output_prob_thresh"] = 0.25
        if points:
            request["points"] = [
                [
                    max(0.0, min(1.0, float(p["x"]) / width)),
                    max(0.0, min(1.0, float(p["y"]) / height)),
                ]
                for p in points
            ]
            request["point_labels"] = [int(p.get("label", 1)) for p in points]
        results = self._run_real_prompt_request(frame_index, width, height, request)
        if not results:
            time.sleep(0.15)
            print("SAM prompt returned no masks on first attempt; retrying once.", flush=True)
            results = self._run_real_prompt_request(frame_index, width, height, request)
        if not results and self._active_backend == "sam3_multiplex_video" and points and any(int(p.get("label", 1)) == 1 for p in points):
            fallback_request = self._point_box_fallback_request(request, points, width, height)
            results = self._run_real_prompt_request(frame_index, width, height, fallback_request)
        if box and len(results) > 1:
            results = [max(results, key=lambda result: self._box_iou(result["bbox"], box))]
        if points and len(results) > 1:
            results = [min(results, key=lambda result: self._point_bbox_distance(result["bbox"], points))]
        if object_id is not None and len(results) == 1:
            results[0]["object_id"] = object_id
            results[0]["track_id"] = object_id
        return results

    def _run_real_prompt_request(self, frame_index: int, width: int, height: int, request: dict[str, Any]) -> list[dict]:
        self._log_real_prompt_request(frame_index, width, height, request)
        with self._torch_device_context():
            response = self._model.handle_request(request)
        self._log_real_prompt_response(response.get("outputs", {}))
        return self._results_from_outputs(frame_index, response.get("outputs", {}), width, height, self._source_name())

    def _point_box_fallback_request(self, request: dict[str, Any], points: list[dict], width: int, height: int) -> dict[str, Any]:
        positives = [p for p in points if int(p.get("label", 1)) == 1]
        center_x = sum(float(p["x"]) for p in positives) / len(positives)
        center_y = sum(float(p["y"]) for p in positives) / len(positives)
        side = max(96.0, min(float(width), float(height)) * 0.10)
        x1 = max(0.0, center_x - side / 2)
        y1 = max(0.0, center_y - side / 2)
        x2 = min(float(width), center_x + side / 2)
        y2 = min(float(height), center_y + side / 2)
        fallback = {
            "type": "add_prompt",
            "session_id": request["session_id"],
            "frame_index": request["frame_index"],
            "text": request.get("text"),
            "bounding_boxes": [[
                x1 / width,
                y1 / height,
                (x2 - x1) / width,
                (y2 - y1) / height,
            ]],
            "bounding_box_labels": [1],
            "output_prob_thresh": 0.25,
        }
        print("SAM point prompt returned no masks; retrying as a local box prompt.", flush=True)
        return fallback

    def _real_propagate(
        self,
        session_id: str,
        object_ids: list[int] | None,
        start_frame: int,
        end_frame: int,
        direction: str,
        on_frame: Callable[[dict], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict]:
        propagation_object_ids = self._multiplex_propagation_object_ids(session_id, object_ids)
        request = self._propagation_request(session_id, start_frame, end_frame, direction)
        self._force_multiplex_partial_propagation(session_id, propagation_object_ids, start_frame)
        self._log_multiplex_propagation_state(session_id, start_frame, propagation_object_ids, "before-propagation")
        print(f"SAM propagate request: {request}", flush=True)
        frames: list[dict] = []
        aborted_empty_start = self._consume_real_propagation_stream(request, start_frame, end_frame, propagation_object_ids, on_frame, frames, abort_on_empty_start=True, should_cancel=should_cancel)
        if should_cancel and should_cancel():
            print(f"SAM propagate cancelled after {len(frames)} frame(s).", flush=True)
            return frames
        if aborted_empty_start or not frames:
            time.sleep(0.15)
            if aborted_empty_start:
                reason = "empty start item"
            else:
                reason = "no frames"
            print(f"SAM propagate returned {reason} on first attempt; retrying once.", flush=True)
            self._consume_real_propagation_stream(request, start_frame, end_frame, propagation_object_ids, on_frame, frames, abort_on_empty_start=False, should_cancel=should_cancel)
        print(f"SAM propagate frames saved candidates: {len(frames)}", flush=True)
        return frames

    def _propagation_request(self, session_id: str, start_frame: int, end_frame: int, direction: str) -> dict[str, Any]:
        propagation_direction = {"bidirectional": "both"}.get(direction, direction)
        if self._active_backend == "sam3_multiplex_video":
            return {
                "type": "propagate_in_video",
                "session_id": session_id,
                "propagation_direction": propagation_direction,
                "start_frame_index": start_frame,
                "max_frame_num_to_track": abs(end_frame - start_frame) + 1,
            }
        return {
            "type": "propagate_in_video",
            "session_id": session_id,
            "propagation_direction": propagation_direction,
            "start_frame_index": start_frame,
            "max_frame_num_to_track": abs(end_frame - start_frame) + 1,
        }

    def _consume_real_propagation_stream(
        self,
        request: dict[str, Any],
        start_frame: int,
        end_frame: int,
        propagation_object_ids: list[int] | None,
        on_frame: Callable[[dict], None] | None,
        frames: list[dict],
        abort_on_empty_start: bool,
        should_cancel: Callable[[], bool] | None = None,
    ) -> bool:
        with self._torch_device_context():
            import torch

            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                for item in self._model.handle_stream_request(request):
                    if should_cancel and should_cancel():
                        return False
                    frame_index = int(item["frame_index"])
                    if frame_index < min(start_frame, end_frame) or frame_index > max(start_frame, end_frame):
                        continue
                    outputs = item.get("outputs", item)
                    if abort_on_empty_start and not frames and self._is_empty_propagation_outputs(outputs):
                        print(f"SAM propagate cold-start empty item at frame {frame_index}; restarting propagation.", flush=True)
                        return True
                    self._log_propagate_item(frame_index, outputs)
                    if self._is_empty_propagation_outputs(outputs):
                        self._log_multiplex_propagation_state(
                            str(request.get("session_id", "")),
                            frame_index,
                            propagation_object_ids,
                            "empty-propagation-output",
                        )
                    masks = outputs.get("out_binary_masks")
                    if masks is None:
                        continue
                    masks_np = self._to_numpy(masks)
                    if masks_np.ndim >= 3:
                        height, width = masks_np.shape[-2], masks_np.shape[-1]
                    else:
                        height, width = 0, 0
                    results = self._results_from_outputs(frame_index, outputs, width, height, self._source_name(), propagation_object_ids)
                    if results:
                        frame = {"frame_index": frame_index, "objects": results}
                        if should_cancel and should_cancel():
                            return False
                        if on_frame:
                            on_frame(frame)
                        frames.append(frame)
        return False

    def _is_empty_propagation_outputs(self, outputs: dict[str, Any]) -> bool:
        obj_ids = self._to_numpy(outputs.get("out_obj_ids", []))
        masks = self._to_numpy(outputs.get("out_binary_masks", []))
        if obj_ids.size == 0:
            return True
        return masks.ndim >= 3 and masks.shape[0] == 0

    def _multiplex_propagation_object_ids(self, session_id: str, object_ids: list[int] | None) -> list[int] | None:
        if self._active_backend != "sam3_multiplex_video" or not object_ids:
            return object_ids
        session = getattr(self._model, "_all_inference_states", {}).get(session_id)
        inference_state = session.get("state") if isinstance(session, dict) else None
        if not isinstance(inference_state, dict):
            return object_ids
        valid_ids: set[int] = set()
        for state in inference_state.get("sam2_inference_states", []):
            valid_ids.update(int(obj_id) for obj_id in state.get("obj_ids", []))
        filtered = [int(object_id) for object_id in object_ids if int(object_id) in valid_ids]
        skipped = [int(object_id) for object_id in object_ids if int(object_id) not in valid_ids]
        if skipped:
            print(f"SAM skipping non-SAM2 propagation object_ids={skipped}; valid_sam2_object_ids={sorted(valid_ids)}", flush=True)
        if not filtered:
            raise RuntimeError("No selected objects are registered in the current SAM3.1 tracker state. Add/refine an object with a point prompt in this session before propagating.")
        return filtered

    def _force_multiplex_partial_propagation(self, session_id: str, object_ids: list[int] | None, start_frame: int) -> None:
        if self._active_backend != "sam3_multiplex_video" or not object_ids:
            return
        session = getattr(self._model, "_all_inference_states", {}).get(session_id)
        inference_state = session.get("state") if isinstance(session, dict) else None
        if not isinstance(inference_state, dict):
            return
        model = getattr(self._model, "model", None)
        add_action_history = getattr(model, "add_action_history", None)
        if not callable(add_action_history):
            return
        add_action_history(
            inference_state,
            action_type="refine",
            frame_idx=start_frame,
            obj_ids=[int(object_id) for object_id in object_ids],
        )

    def _mock_segment(self, project_id: str, frame_index: int, image_path: str, object_id: int | None, text: str | None, box: list[float] | None, points: list[dict], mask: np.ndarray | None, category: str | None) -> list[dict]:
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        tracked = self.store.ensure_object(project_id, object_id, category, frame_index)
        object_id = int(tracked["object_id"])
        if mask is None:
            mask = np.zeros((height, width), dtype=bool)
            if box:
                x1, y1, x2, y2 = [int(round(v)) for v in box]
                x1, x2 = sorted((max(0, x1), min(width, x2)))
                y1, y2 = sorted((max(0, y1), min(height, y2)))
                mask[y1:y2, x1:x2] = True
            elif points:
                for point in points:
                    center = (int(point["x"]), int(point["y"]))
                    layer = np.zeros((height, width), dtype=np.uint8)
                    cv2.circle(layer, center, 28, 1, -1)
                    if int(point.get("label", 1)) == 1:
                        mask |= layer.astype(bool)
                    else:
                        mask &= ~layer.astype(bool)
            elif text:
                x1, x2 = width // 3, width * 2 // 3
                y1, y2 = height // 3, height * 2 // 3
                mask[y1:y2, x1:x2] = True
        return [self._result_from_mask(frame_index, object_id, mask, "mock")]

    def _result_from_mask(self, frame_index: int, object_id: int, mask: np.ndarray, source: str) -> dict:
        return {
            "frame_index": frame_index,
            "object_id": object_id,
            "track_id": object_id,
            "mask": mask,
            "bbox": bbox_from_mask(mask),
            "area": area_from_mask(mask),
            "score": 1.0,
            "source": source,
        }

    def _results_from_outputs(self, frame_index: int, outputs: dict[str, Any], width: int, height: int, source: str, filter_object_ids: list[int] | None = None) -> list[dict]:
        obj_ids = self._to_numpy(outputs.get("out_obj_ids", []))
        masks = self._to_numpy(outputs.get("out_binary_masks", []))
        if masks.ndim == 2:
            masks = masks[None, :, :]
        results: list[dict] = []
        for index, mask in enumerate(masks):
            object_id = int(obj_ids[index]) if index < len(obj_ids) else index + 1
            if filter_object_ids and object_id not in filter_object_ids:
                continue
            binary = mask.astype(bool)
            if binary.ndim == 3:
                binary = binary.squeeze()
            if not binary.any():
                continue
            results.append(self._result_from_mask(frame_index, object_id, binary, source))
        return results

    def _log_real_prompt_request(self, frame_index: int, width: int, height: int, request: dict[str, Any]) -> None:
        prompt_type = "point" if request.get("points") is not None else ("box" if request.get("bounding_boxes") is not None else "text")
        details = {
            "backend": self._active_backend,
            "frame": frame_index,
            "image_size": [width, height],
            "prompt_type": prompt_type,
            "obj_id": request.get("obj_id"),
            "box_xywh_norm": request.get("bounding_boxes"),
            "points_norm": request.get("points"),
            "point_labels": request.get("point_labels"),
            "text": request.get("text"),
            "output_prob_thresh": request.get("output_prob_thresh"),
        }
        print(f"SAM prompt request: {details}", flush=True)

    def _log_real_prompt_response(self, outputs: dict[str, Any]) -> None:
        obj_ids = self._to_numpy(outputs.get("out_obj_ids", []))
        masks = self._to_numpy(outputs.get("out_binary_masks", []))
        boxes = self._to_numpy(outputs.get("out_boxes_xywh", []))
        mask_sums = []
        if masks.size:
            masks_for_sum = masks
            if masks_for_sum.ndim == 2:
                masks_for_sum = masks_for_sum[None, :, :]
            mask_sums = [int(np.asarray(mask).astype(bool).sum()) for mask in masks_for_sum]
        details = {
            "obj_ids_shape": list(obj_ids.shape),
            "obj_ids": obj_ids.tolist() if obj_ids.size <= 20 else obj_ids[:20].tolist(),
            "masks_shape": list(masks.shape),
            "mask_sums": mask_sums[:20],
            "boxes_shape": list(boxes.shape),
        }
        print(f"SAM prompt response: {details}", flush=True)

    def _log_propagate_item(self, frame_index: int, outputs: dict[str, Any]) -> None:
        obj_ids = self._to_numpy(outputs.get("out_obj_ids", []))
        masks = self._to_numpy(outputs.get("out_binary_masks", []))
        mask_sums = []
        if masks.size:
            masks_for_sum = masks
            if masks_for_sum.ndim == 2:
                masks_for_sum = masks_for_sum[None, :, :]
            mask_sums = [int(np.asarray(mask).astype(bool).sum()) for mask in masks_for_sum[:20]]
        print(
            "SAM propagate item: "
            f"{{'frame': {frame_index}, 'obj_ids': {obj_ids.tolist() if obj_ids.size <= 20 else obj_ids[:20].tolist()}, "
            f"'masks_shape': {list(masks.shape)}, 'mask_sums': {mask_sums}}}",
            flush=True,
        )

    def _log_multiplex_propagation_state(
        self,
        session_id: str,
        frame_index: int,
        object_ids: list[int] | None,
        label: str,
    ) -> None:
        if self._active_backend != "sam3_multiplex_video" or self._model is None:
            return
        session = getattr(self._model, "_all_inference_states", {}).get(session_id)
        inference_state = session.get("state") if isinstance(session, dict) else None
        if not isinstance(inference_state, dict):
            print(f"SAM multiplex state {label}: missing session state for {session_id}", flush=True)
            return

        selected = {int(obj_id) for obj_id in object_ids} if object_ids else None
        tracker_metadata = inference_state.get("tracker_metadata", {})
        rank0_metadata = tracker_metadata.get("rank0_metadata", {}) if isinstance(tracker_metadata, dict) else {}
        suppressed = rank0_metadata.get("suppressed_obj_ids", {})
        try:
            suppressed_at_frame = sorted(int(obj_id) for obj_id in suppressed.get(frame_index, set()))
        except Exception:
            suppressed_at_frame = []

        details: dict[str, Any] = {
            "label": label,
            "frame": frame_index,
            "selected_object_ids": sorted(selected) if selected is not None else None,
            "sam2_state_count": len(inference_state.get("sam2_inference_states", [])),
            "cached_frame_output_keys_nearby": self._nearby_keys(inference_state.get("cached_frame_outputs", {}), frame_index),
            "tracker_obj_ids_all": self._small_int_list(tracker_metadata.get("obj_ids_all_gpu", [])) if isinstance(tracker_metadata, dict) else [],
            "suppressed_at_frame": suppressed_at_frame,
            "states": [],
        }

        for state_index, sam2_state in enumerate(inference_state.get("sam2_inference_states", [])):
            state_obj_ids = self._small_int_list(sam2_state.get("obj_ids", []))
            if selected is not None and not (set(state_obj_ids) & selected):
                continue
            obj_id_to_idx = sam2_state.get("obj_id_to_idx", {})
            state_detail: dict[str, Any] = {
                "state_index": state_index,
                "obj_ids": state_obj_ids,
                "tracked_frame": sam2_state.get("frames_already_tracked", {}).get(frame_index),
                "output_cond_keys_nearby": self._nearby_keys(sam2_state.get("output_dict", {}).get("cond_frame_outputs", {}), frame_index),
                "output_non_cond_keys_nearby": self._nearby_keys(sam2_state.get("output_dict", {}).get("non_cond_frame_outputs", {}), frame_index),
                "objects": [],
            }
            inspect_obj_ids = state_obj_ids if selected is None else [obj_id for obj_id in state_obj_ids if obj_id in selected]
            for obj_id in inspect_obj_ids[:8]:
                obj_idx = obj_id_to_idx.get(obj_id)
                if obj_idx is None:
                    obj_idx = obj_id_to_idx.get(str(obj_id))
                object_detail: dict[str, Any] = {
                    "obj_id": obj_id,
                    "obj_idx": int(obj_idx) if obj_idx is not None else None,
                    "point_frames": [],
                    "mask_frames": [],
                    "temp_cond_keys_nearby": [],
                    "temp_non_cond_keys_nearby": [],
                    "frame_output": self._sam2_object_frame_output_summary(sam2_state, obj_idx, frame_index),
                }
                if obj_idx is not None:
                    point_inputs = sam2_state.get("point_inputs_per_obj", {}).get(obj_idx, {})
                    mask_inputs = sam2_state.get("mask_inputs_per_obj", {}).get(obj_idx, {})
                    temp_outputs = sam2_state.get("temp_output_dict_per_obj", {}).get(obj_idx, {})
                    object_detail["point_frames"] = self._small_int_list(point_inputs.keys())
                    object_detail["mask_frames"] = self._small_int_list(mask_inputs.keys())
                    object_detail["temp_cond_keys_nearby"] = self._nearby_keys(temp_outputs.get("cond_frame_outputs", {}), frame_index)
                    object_detail["temp_non_cond_keys_nearby"] = self._nearby_keys(temp_outputs.get("non_cond_frame_outputs", {}), frame_index)
                state_detail["objects"].append(object_detail)
            details["states"].append(state_detail)

        print(f"SAM multiplex propagation state: {details}", flush=True)

    def _sam2_object_frame_output_summary(self, sam2_state: dict[str, Any], obj_idx: Any, frame_index: int) -> dict[str, Any] | None:
        if obj_idx is None:
            return None
        per_obj = sam2_state.get("output_dict_per_obj", {}).get(obj_idx, {})
        for storage_key in ("cond_frame_outputs", "non_cond_frame_outputs"):
            frame_out = per_obj.get(storage_key, {}).get(frame_index)
            if frame_out is None:
                continue
            pred_masks = self._to_numpy(frame_out.get("pred_masks", []))
            score_logits = self._to_numpy(frame_out.get("object_score_logits", []))
            return {
                "storage_key": storage_key,
                "pred_masks_shape": list(pred_masks.shape),
                "pred_mask_positive_sum": int((pred_masks > 0).sum()) if pred_masks.size else 0,
                "object_score_logits": score_logits.reshape(-1).tolist()[:8] if score_logits.size else [],
            }
        return None

    def _nearby_keys(self, mapping: Any, frame_index: int, radius: int = 3) -> list[int]:
        if not hasattr(mapping, "keys"):
            return []
        keys: list[int] = []
        for key in mapping.keys():
            try:
                value = int(key)
            except Exception:
                continue
            if abs(value - frame_index) <= radius:
                keys.append(value)
        return sorted(keys)

    def _small_int_list(self, values: Any, limit: int = 20) -> list[int]:
        result: list[int] = []
        for value in list(values)[:limit]:
            try:
                result.append(int(value))
            except Exception:
                continue
        return result

    def _source_name(self) -> str:
        if self._active_backend == "sam3_multiplex_video":
            return "sam3_multiplex"
        if self._active_backend == "sam3_video":
            return "sam3_video"
        return self._active_backend

    def _configure_interactive_video_tracking(self) -> None:
        if self._active_backend != "sam3_multiplex_video" or self._model is None:
            return
        model = getattr(self._model, "model", None)
        if model is None:
            return
        for name, value in {
            "hotstart_delay": 0,
            "masklet_confirmation_enable": False,
            "postprocess_batch_size": 1,
        }.items():
            if hasattr(model, name):
                setattr(model, name, value)
        print(
            "SAM3.1 multiplex interactive tracking config: "
            f"hotstart_delay={getattr(model, 'hotstart_delay', None)}, "
            f"masklet_confirmation_enable={getattr(model, 'masklet_confirmation_enable', None)}, "
            f"postprocess_batch_size={getattr(model, 'postprocess_batch_size', None)}",
            flush=True,
        )

    def _format_fallback_error(self, context: str, detail: str) -> str:
        message = f"{context}; falling back to mock. {detail}"
        if "CUDA error" in detail:
            message += " Restart the backend process before retrying a real SAM backend; CUDA launch failures can leave the process CUDA context invalid. Set CUDA_LAUNCH_BLOCKING=1 before starting the backend for a more accurate stack trace."
        return message

    def _to_numpy(self, value: Any) -> np.ndarray:
        if value is None:
            return np.array([])
        if hasattr(value, "detach"):
            if str(getattr(value, "dtype", "")) == "torch.bfloat16":
                value = value.float()
            value = value.detach().cpu().numpy()
        return np.asarray(value)

    def _image_shape(self, image_path: str) -> tuple[int, int]:
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        return height, width

    def _box_iou(self, first: list[float], second: list[float]) -> float:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    def _point_bbox_distance(self, bbox: list[float], points: list[dict]) -> float:
        positives = [p for p in points if int(p.get("label", 1)) == 1] or points
        px = sum(float(p["x"]) for p in positives) / len(positives)
        py = sum(float(p["y"]) for p in positives) / len(positives)
        x1, y1, x2, y2 = bbox
        if x1 <= px <= x2 and y1 <= py <= y2:
            return 0.0
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return (cx - px) ** 2 + (cy - py) ** 2

    def _frame_range(self, start_frame: int, end_frame: int, direction: str) -> range:
        if direction == "backward":
            return range(start_frame, end_frame - 1, -1)
        return range(start_frame, end_frame + 1)
