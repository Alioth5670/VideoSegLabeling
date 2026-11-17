"""Project management permissions, naming and reversible removal."""
from datetime import datetime, timezone
from collections.abc import Callable
import json
import shutil
import tempfile
from pathlib import Path

from app.utils.project_registry import load_project_paths, unregister_project_dir

from app.services.account_store import AccountStore, DuplicateProjectNameError
from app.services.video_service import VideoService


class ProjectAccessError(LookupError):
    pass


class ProjectPermissionError(PermissionError):
    pass


class ProjectManagement:
    def __init__(self, accounts: AccountStore, videos: VideoService):
        self.accounts = accounts
        self.videos = videos

    def change(self, project_id: str, actor: dict, *, name: str | None = None,
               owner_id: str | None = None, deleted: bool | None = None,
               before_change: Callable[[], None] | None = None) -> dict:
        with self.accounts.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row or (not actor['admin'] and row['owner_id'] != actor['id']):
                raise ProjectAccessError('项目不存在')
            if row['deleted_at'] and deleted is not False:
                raise ProjectAccessError('项目已在回收站中')
            if deleted is True:
                # Recycling is an index-only operation. Missing or damaged files
                # must not prevent users from managing stale project records.
                if before_change:
                    before_change()
                now = datetime.now(timezone.utc).isoformat()
                db.execute('UPDATE projects SET deleted_at=?, updated_at=? WHERE id=?', (now, now, project_id))
                return {'project_id': project_id, 'name': row['name'], 'owner_id': row['owner_id'],
                        'deleted_at': now, 'updated_at': now}
            if owner_id is not None and not actor['admin']:
                raise ProjectPermissionError('只有管理员可以转移项目')
            target = owner_id or row['owner_id']
            user = db.execute('SELECT id, active FROM users WHERE id=?', (target,)).fetchone()
            if not user or (owner_id and not user['active']):
                raise ValueError('目标账户不存在或已停用')
            new_name = name.strip() if name is not None else row['name']
            if not new_name:
                raise ValueError('项目名称不能为空')
            if deleted is not True:
                others = db.execute('SELECT name FROM projects WHERE owner_id=? AND id<>? AND deleted_at IS NULL', (target, project_id))
                if any(other['name'].strip().casefold() == new_name.casefold() for other in others):
                    raise DuplicateProjectNameError('该账户已有同名项目，请先修改名称')
            project = self.videos.load_project(project_id)
            if before_change:
                before_change()
            project['name'] = new_name
            now = datetime.now(timezone.utc).isoformat()
            deleted_at = now if deleted is True else None if deleted is False else row['deleted_at']
            self.videos.save_project(project_id, project, update_index=False)
            db.execute('UPDATE projects SET name=?, owner_id=?, deleted_at=?, updated_at=? WHERE id=?',
                       (new_name, target, deleted_at, now, project_id))
            return {'project_id': project_id, 'name': new_name, 'owner_id': target,
                    'deleted_at': deleted_at, 'updated_at': now}


    def permanently_delete(self, project_id: str, actor: dict, confirmation_name: str,
                           before_delete: Callable[[], None] | None = None) -> None:
        with self.accounts.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row or (not actor['admin'] and row['owner_id'] != actor['id']):
                raise ProjectAccessError('项目不存在')
            if not row['deleted_at']:
                raise ValueError('只有回收站中的项目才能彻底删除')
            if confirmation_name != row['name']:
                raise ValueError('确认名称与项目名称不一致')
            paths = load_project_paths(self.videos.projects_dir)
            base = self.videos.projects_dir.resolve()
            raw = Path(paths.get(project_id, base / project_id))
            root = raw.resolve()
            repository = Path(__file__).resolve().parents[3]
            protected = {base, repository, Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
            protected.update(repository / name for name in ('backend', 'frontend', 'sam3', 'checkpoints', 'data', 'release', 'scripts', '.git', '.agents', '.codex', 'venv-server', '.venv'))
            if raw.is_symlink() or any(root == path or root in path.parents for path in protected):
                raise ValueError('项目路径不安全，不能删除公共目录或符号链接')
            other_ids = {record['id'] for record in db.execute('SELECT id FROM projects WHERE id<>?', (project_id,))}
            other_ids.update(key for key in paths if key != project_id)
            for other_id in other_ids:
                other = Path(paths.get(other_id, base / other_id)).resolve()
                if root == other or root in other.parents or other in root.parents:
                    raise ValueError('项目目录与其他项目重叠，不能彻底删除')
            if root.exists():
                metadata = root / 'project.json'
                if not root.is_dir() or metadata.is_symlink() or not metadata.is_file():
                    raise ValueError('无法确认目录归属：project.json 缺失，请先恢复该文件')
                try:
                    project = json.loads(metadata.read_text(encoding='utf-8'))
                except (ValueError, UnicodeError) as exc:
                    raise ValueError('无法确认目录归属：project.json 损坏') from exc
                if not isinstance(project, dict) or project.get('project_id') != project_id:
                    raise ValueError('目录中的项目编号不匹配，已拒绝删除')
                if root != (base / project_id).resolve():
                    # Custom paths may have existed before project creation.
                    allowed = {'project.json', 'annotations.json', 'annotations.sqlite3',
                               'annotations.sqlite3-journal', 'annotations.sqlite3-wal', 'annotations.sqlite3-shm',
                               'videos', 'frames', 'masks', 'overlays', 'exports'}
                    for video in [project, *project.get('videos', [])]:
                        video_path = video.get('video_path')
                        if isinstance(video_path, str) and video_path:
                            relative = Path(video_path)
                            if not relative.is_absolute() and '..' not in relative.parts:
                                allowed.add(relative.parts[0])
                    if any(child.name not in allowed for child in root.iterdir()):
                        raise ValueError('自定义项目目录包含其他文件，无法安全彻底删除')
            if before_delete:
                before_delete()
            if root.exists():
                # Keep ownership metadata until all other files have been removed,
                # so a permission/IO failure leaves enough information to retry.
                for child in root.iterdir():
                    if child.name == 'project.json':
                        continue
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                (root / 'project.json').unlink()
                root.rmdir()
            unregister_project_dir(self.videos.projects_dir, project_id)
            db.execute('DELETE FROM projects WHERE id=?', (project_id,))
