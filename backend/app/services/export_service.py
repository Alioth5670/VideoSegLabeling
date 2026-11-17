import hashlib
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from threading import RLock

from app.services.annotation_store import AnnotationStore
from app.services import annotation_database
from app.utils.rle import encode_rle
from app.utils.mask import read_mask_png
from app.utils.project_registry import project_root


class ExportService:
    def __init__(self, projects_dir: Path, store: AnnotationStore | None = None):
        self.projects_dir = projects_dir
        self.store = store or AnnotationStore(projects_dir)
        self._lock = RLock()
        self._progress: Callable[[float, str], None] | None = None
        self._snapshot: dict | None = None

    def _report(self, value: float, stage: str) -> None:
        if self._progress:
            self._progress(value, stage)

    def _project(self, root: Path) -> dict:
        return self._snapshot or json.loads((root / 'project.json').read_text(encoding='utf-8'))

    def _video_root(self, root: Path, video: dict) -> Path:
        return root / (video.get('storage_dir') or f"videos/{video['video_id']}") if video.get('video_id') else root

    def _data(self, root: Path, video_root: Path) -> dict:
        project = self._project(root)
        with annotation_database.connect(video_root / 'annotations.json', {'project_id': project['project_id'],
                'objects': {}, 'frames': {}, 'prompts': [], 'keyframes': []}) as db:
            db.execute('BEGIN')
            return annotation_database.snapshot(db)

    def export(self, project_id: str, export_format: str, *,
               progress: Callable[[float, str], None] | None = None, project_snapshot: dict | None = None) -> Path:
        if export_format not in {'project_json', 'mask_png', 'coco_video_json', 'all_videos_zip'}:
            raise ValueError(export_format)
        with self._lock:
            self._progress = progress
            self._snapshot = project_snapshot
            try:
                self._report(1, '读取项目')
                root = project_root(self.projects_dir, project_id)
                project = self._project(root)
                videos = (project.get('videos') or [self._legacy_video(project)]) if export_format == 'all_videos_zip' else [self._active_video(project)]
                revisions = []
                for video in videos:
                    base = self._video_root(root, video)
                    with annotation_database.connect(base / 'annotations.json', {'project_id': project_id}):
                        pass
                    stat = (base / 'annotations.sqlite3').stat()
                    revisions.append((video.get('video_id'), stat.st_mtime_ns, stat.st_size))
                fingerprint = hashlib.sha256(json.dumps([project, revisions, export_format, 3], sort_keys=True).encode()).hexdigest()[:20]
                cache = root / 'exports' / f'{export_format}-{fingerprint}.zip'
                if cache.exists():
                    self._report(99, '复用已有导出')
                    return cache
                cache.parent.mkdir(parents=True, exist_ok=True)
                result = self._export(project_id, export_format)
                self._report(98, '完成归档')
                result.replace(cache)
                archives = sorted(cache.parent.glob(f'{export_format}-*.zip'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
                for old in archives[2:]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
                return cache
            finally:
                self._progress = None
                self._snapshot = None

    def _export(self, project_id: str, export_format: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        project = self._project(root)
        video = self._active_video(project)
        base = self._video_root(root, video)
        out_dir = base / 'exports'
        out_dir.mkdir(parents=True, exist_ok=True)
        if export_format == 'project_json':
            self._report(5, '读取标注')
            data = self._data(root, base)
            self._report(25, '生成项目 JSON')
            out = out_dir / 'project_json.zip'
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                archive.writestr('project.json', json.dumps(project, ensure_ascii=False, indent=2))
                self._report(50, '压缩标注 JSON')
                archive.writestr('annotations.json', json.dumps(data, ensure_ascii=False, indent=2))
            self._report(95, '项目 JSON 已打包')
            return out
        if export_format == 'mask_png':
            self._report(3, '统计 mask 文件')
            masks = list((base / 'masks').rglob('*.png'))
            out = out_dir / 'mask_png.zip'
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for index, mask in enumerate(masks):
                    archive.write(mask, mask.relative_to(root).as_posix(), compress_type=zipfile.ZIP_STORED)
                    self._report(5 + 90 * (index + 1) / len(masks), f'打包 mask {index + 1}/{len(masks)}')
            return out
        if export_format == 'coco_video_json':
            return self._export_coco(project_id)
        return self._export_all_videos(project_id)

    def _export_coco(self, project_id: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        video = self._active_video(self._project(root))
        base = self._video_root(root, video)
        self._report(3, '读取标注')
        annotations = self._coco_annotations(root, base, video)
        self._report(80, '生成 COCO JSON')
        out = base / 'exports' / 'coco_video_json.zip'
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr('coco_video.json', json.dumps({'videos': [self._coco_video_record(video)],
                                                         'annotations': annotations}, ensure_ascii=False, indent=2))
        self._report(95, 'COCO JSON 已打包')
        return out

    def _export_all_videos(self, project_id: str) -> Path:
        root = project_root(self.projects_dir, project_id)
        project = self._project(root)
        out = root / 'exports' / 'all_videos.zip'
        videos = project.get('videos') or [self._legacy_video(project)]
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr('project.json', json.dumps(project, ensure_ascii=False, indent=2))
            summary, merged_videos, merged_annotations = [], [], []
            for index, video in enumerate(videos):
                video_id = video.get('video_id') or 'legacy'
                base = self._video_root(root, video)
                storage = video.get('storage_dir')
                prefix = storage if isinstance(storage, str) and storage.startswith('videos/') else f"videos/{index:03d}_{self._safe_name(video.get('name') or video_id)}"
                low, high = 5 + 85 * index / len(videos), 5 + 85 * (index + 1) / len(videos)
                middle = low + (high - low) * .7
                self._report(low, f'处理视频 {index + 1}/{len(videos)}')
                data = self._data(root, base)
                annotations = self._coco_annotations(root, base, video, data=data, bounds=(low, middle))
                record = self._coco_video_record(video)
                merged_videos.append(record)
                archive.writestr(f'{prefix}/video.json', json.dumps(video, ensure_ascii=False, indent=2))
                archive.writestr(f'{prefix}/annotations.json', json.dumps(data, ensure_ascii=False, indent=2))
                archive.writestr(f'{prefix}/coco_video.json', json.dumps({'videos': [record], 'annotations': annotations}, ensure_ascii=False, indent=2))
                for annotation in annotations:
                    merged_annotations.append({**annotation, 'id': len(merged_annotations) + 1})
                masks = list((base / 'masks').rglob('*.png'))
                for mask_index, mask in enumerate(masks):
                    archive.write(mask, f'{prefix}/{mask.relative_to(base).as_posix()}', compress_type=zipfile.ZIP_STORED)
                    self._report(middle + (high - middle) * (mask_index + 1) / len(masks),
                                 f'视频 {index + 1}/{len(videos)}：打包 mask {mask_index + 1}/{len(masks)}')
                summary.append({'video_id': video.get('video_id'), 'name': video.get('name'),
                                'frame_count': video.get('frame_count', 0), 'annotation_count': len(annotations), 'folder': prefix})
            self._report(92, '合并 COCO JSON')
            archive.writestr('summary.json', json.dumps({'videos': summary}, ensure_ascii=False, indent=2))
            archive.writestr('coco_all_videos.json', json.dumps({'videos': merged_videos, 'annotations': merged_annotations}, ensure_ascii=False, indent=2))
        self._report(95, '全部视频已打包')
        return out

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

    def _coco_annotations(self, root: Path, video_root: Path, video: dict, *, data: dict | None = None,
                          bounds: tuple[float, float] = (5, 75)) -> list[dict]:
        data = data if data is not None else self._data(root, video_root)
        total = sum(len(frame.get('objects', {})) for frame in data.get('frames', {}).values())
        annotations = []
        video_id = video.get('video_id') or 'legacy'
        low, high = bounds
        for frame_index, frame in data.get('frames', {}).items():
            for object_id, obj in frame.get('objects', {}).items():
                mask = read_mask_png(root / obj['mask_path'])
                annotations.append({'id': len(annotations) + 1, 'video_id': video_id,
                    'frame_index': int(frame_index), 'object_id': int(object_id), 'track_id': obj['track_id'],
                    'bbox': obj['bbox'], 'area': obj['area'], 'segmentation': encode_rle(mask)})
                self._report(low + (high - low) * len(annotations) / total,
                             f'编码 mask {len(annotations)}/{total}')
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
