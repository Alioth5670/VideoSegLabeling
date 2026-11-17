import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.account_store import AccountStore


class ProjectIndexMigrationTests(unittest.TestCase):
    def test_old_project_index_upgrades_without_losing_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE projects (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, updated_at TEXT NOT NULL)')
                db.execute('INSERT INTO projects VALUES (?,?,?,?)', ('old', 'owner', 'Legacy project', '2026-01-01'))
            store = AccountStore(path)
            record = store.project_record('old')
            self.assertEqual(record['owner_id'], 'owner')
            self.assertEqual(record['name'], 'Legacy project')
            self.assertIsNone(record['deleted_at'])
            store.index_project({'project_id': 'new', 'name': 'New project'}, 'owner')
            self.assertEqual(store.owner('new'), 'owner')
            restarted = AccountStore(path)
            self.assertEqual(restarted.project_record('old'), record)

    def test_availability_respects_custom_paths_without_loading_metadata(self):
        from app.services.video_service import VideoService
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos = VideoService(root / 'projects')
            external = root / 'custom-storage'
            project = videos.create_project('Custom project', str(external))
            project_id = project['project_id']
            with patch.object(videos, 'load_project', side_effect=AssertionError('List must not parse full metadata')):
                availability = videos.project_availability([project_id, 'missing-project'])
            self.assertEqual(availability[project_id]['data_status'], 'available')
            self.assertEqual(availability['missing-project']['data_status'], 'missing')
            (external / 'project.json').unlink()
            self.assertEqual(videos.project_availability([project_id])[project_id]['data_status'], 'missing')


class PermanentDeletionSafetyTests(unittest.TestCase):
    def setUp(self):
        from app.services.video_service import VideoService
        from app.services.project_management import ProjectManagement
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.videos = VideoService(self.root / 'projects')
        self.accounts = self.videos.account_store
        self.actor = self.accounts.create_user('owner', '123456', admin=True)
        self.management = ProjectManagement(self.accounts, self.videos)

    def create(self, name='Purge safety project', custom=None):
        project = self.videos.create_project(name, str(custom) if custom else None)
        self.accounts.index_project(project, self.actor['id'])
        self.management.change(project['project_id'], self.actor, deleted=True)
        return project

    def purge(self, project):
        self.management.permanently_delete(project['project_id'], self.actor, project['name'])

    def test_shared_public_and_symlink_roots_are_rejected(self):
        from app.utils.project_registry import register_project_dir
        for kind in ('public', 'shared', 'symlink', 'nested'):
            with self.subTest(kind=kind):
                project = self.create(f'Safety {kind}')
                project_id = project['project_id']
                original = self.videos.project_path(project_id)
                sentinel = original / 'keep.txt'
                sentinel.write_text('keep')
                if kind == 'public':
                    register_project_dir(self.videos.projects_dir, project_id, self.videos.projects_dir)
                elif kind == 'symlink':
                    link = self.root / 'linked-project'
                    link.symlink_to(original, target_is_directory=True)
                    # Preserve the raw link in the registry to exercise the guard.
                    import json
                    from app.utils.project_registry import registry_path, load_project_paths
                    paths = load_project_paths(self.videos.projects_dir)
                    paths[project_id] = str(link)
                    registry_path(self.videos.projects_dir).write_text(json.dumps(paths))
                elif kind == 'shared':
                    register_project_dir(self.videos.projects_dir, 'shared-other-id', original)
                else:
                    nested = self.videos.create_project('Nested project', str(original / 'nested'))
                    self.accounts.index_project(nested, self.actor['id'])
                with self.assertRaises(ValueError):
                    self.purge(project)
                self.assertEqual(sentinel.read_text(), 'keep')
                self.assertIsNotNone(self.accounts.project_record(project_id, include_deleted=True))
                # Remove test-only aliases so following cases are independent.
                from app.utils.project_registry import unregister_project_dir
                if kind == 'public' or kind == 'symlink':
                    register_project_dir(self.videos.projects_dir, project_id, original)
                if kind == 'shared':
                    unregister_project_dir(self.videos.projects_dir, 'shared-other-id')

    def test_custom_directory_preserves_unrelated_files(self):
        project = self.create(custom=self.root / 'custom-project')
        folder = self.videos.project_path(project['project_id'])
        unrelated = folder / 'personal-document.txt'
        unrelated.write_text('do not delete')
        with self.assertRaisesRegex(ValueError, '其他文件'):
            self.purge(project)
        self.assertEqual(unrelated.read_text(), 'do not delete')
        unrelated.unlink()
        (folder / 'masks').mkdir()
        (folder / 'masks/annotation.txt').write_text('owned project data')
        self.purge(project)
        self.assertFalse(folder.exists())

    def test_missing_or_mismatched_metadata_blocks_existing_directory_delete(self):
        import json
        project = self.create()
        folder = self.videos.project_path(project['project_id'])
        metadata = folder / 'project.json'
        original = metadata.read_text()
        metadata.write_text(json.dumps({'project_id': 'different-project'}))
        with self.assertRaisesRegex(ValueError, '编号不匹配'):
            self.purge(project)
        metadata.unlink()
        (folder / 'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, '缺失'):
            self.purge(project)
        self.assertTrue((folder / 'keep.txt').exists())
        metadata.write_text(original)

    def test_io_failure_retains_metadata_and_index_for_retry(self):
        from unittest.mock import patch
        project = self.create()
        project_id = project['project_id']
        folder = self.videos.project_path(project_id)
        (folder / 'masks').mkdir()
        (folder / 'masks/keep.txt').write_text('keep')
        with patch('app.services.project_management.shutil.rmtree', side_effect=PermissionError('test permission failure')):
            with self.assertRaises(PermissionError):
                self.purge(project)
        self.assertTrue((folder / 'project.json').exists())
        self.assertIsNotNone(self.accounts.project_record(project_id, include_deleted=True))
        self.purge(project)
        self.assertFalse(folder.exists())
