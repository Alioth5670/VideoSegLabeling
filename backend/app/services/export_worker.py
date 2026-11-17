"""Standalone export worker: no model, CUDA, or API dependencies are imported."""
import json
import sys
import time
from pathlib import Path

from app.services.export_jobs import write_status
from app.services.export_service import ExportService
from app.utils.project_registry import project_root


def run(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    path = Path(spec['status_path'])
    status = json.loads(path.read_text(encoding='utf-8'))
    status.update(status='running', stage='准备导出', started_at=time.time())
    write_status(path, status)
    last_update = 0.0

    def progress(value: float, stage: str) -> None:
        nonlocal last_update
        value = min(99, max(status['progress'], round(value, 1)))
        status.update(progress=value, stage=stage)
        now = time.monotonic()
        if now - last_update >= 0.2:
            write_status(path, status)
            last_update = now

    try:
        projects_dir = Path(spec['projects_dir'])
        project_id = spec['project']['project_id']
        service = ExportService(projects_dir)
        result = service.export(project_id, spec['format'], progress=progress, project_snapshot=spec['project'])
        relative = result.relative_to(project_root(projects_dir, project_id)).as_posix()
        status.update(status='completed', progress=100, stage='导出完成', finished_at=time.time(),
                      download_url=f'/api/projects/{project_id}/download/{relative}')
    except Exception as exc:
        status.update(status='failed', stage='导出失败', error=str(exc), finished_at=time.time())
    write_status(path, status)


if __name__ == '__main__':
    run(Path(sys.argv[1]))
