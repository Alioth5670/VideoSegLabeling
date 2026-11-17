import json
import os
import tempfile
from pathlib import Path


REGISTRY_FILENAME = ".project_paths.json"


def registry_path(projects_dir: Path) -> Path:
    return projects_dir / REGISTRY_FILENAME


def load_project_paths(projects_dir: Path) -> dict[str, str]:
    path = registry_path(projects_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def register_project_dir(projects_dir: Path, project_id: str, root: Path) -> None:
    projects_dir.mkdir(parents=True, exist_ok=True)
    paths = load_project_paths(projects_dir)
    paths[project_id] = str(root.resolve())
    _save_project_paths(projects_dir, paths)


def project_root(projects_dir: Path, project_id: str) -> Path:
    registered = load_project_paths(projects_dir).get(project_id)
    if registered:
        return Path(registered)
    return projects_dir / project_id


def _save_project_paths(projects_dir: Path, paths: dict[str, str]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix='.project-paths-', suffix='.json', dir=projects_dir)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
            json.dump(paths, out, indent=2, ensure_ascii=False)
        os.replace(temporary, registry_path(projects_dir))
    finally:
        Path(temporary).unlink(missing_ok=True)


def unregister_project_dir(projects_dir: Path, project_id: str) -> None:
    paths = load_project_paths(projects_dir)
    if project_id in paths:
        paths.pop(project_id)
        _save_project_paths(projects_dir, paths)
