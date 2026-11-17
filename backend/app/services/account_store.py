"""SQLite account, session and project ownership index."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class DuplicateProjectNameError(ValueError):
    pass


class AccountStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS project_owner ON projects(owner_id, updated_at);
            ''')
            if 'deleted_at' not in {row['name'] for row in db.execute('PRAGMA table_info(projects)')}:
                db.execute('ALTER TABLE projects ADD COLUMN deleted_at TEXT DEFAULT NULL')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialized(self) -> bool:
        with self.connect() as db:
            return db.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None

    @staticmethod
    def password_hash(password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return f'{salt}:{digest}'

    def create_user(self, username: str, password: str, admin: bool = False, bootstrap: bool = False, projects: list[dict] | None = None) -> dict:
        user_id = secrets.token_hex(16)
        encoded = self.password_hash(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if bootstrap and db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise ValueError('系统已经初始化')
            db.execute('INSERT INTO users(id, username, password, admin) VALUES (?,?,?,?)',
                       (user_id, username, encoded, int(admin)))
            for project in projects or []:
                db.execute('INSERT OR IGNORE INTO projects(id, owner_id, name, updated_at) VALUES (?,?,?,?)',
                           (project['project_id'], user_id, project['name'], project.get('updated_at', '')))
        return {'id': user_id, 'username': username, 'admin': admin, 'active': True}

    def login(self, username: str, password: str) -> str | None:
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
            encoded = user['password'] if user else self.password_hash('dummy')
            if not hmac.compare_digest(encoded, self.password_hash(password, encoded.split(':')[0])) or not user:
                return None
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',
                       (self.token_hash(token), user['id'], time.time() + 86400))
            return token

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        user = dict(row)
        user['admin'] = bool(user['admin'])
        user['active'] = bool(user['active'])
        return user

    def current_user(self, token: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('''SELECT u.id, u.username, u.admin, u.active FROM users u
                JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1''',
                (self.token_hash(token), time.time())).fetchone()
            return self._public_user(row) if row else None

    def logout(self, token: str) -> None:
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (self.token_hash(token),))

    def users(self) -> list[dict]:
        with self.connect() as db:
            return [self._public_user(row) for row in db.execute('SELECT id, username, admin, active FROM users ORDER BY username')]

    def set_active(self, user_id: str, active: bool) -> None:
        with self.connect() as db:
            updated = db.execute('UPDATE users SET active=? WHERE id=?', (int(active), user_id))
            if updated.rowcount != 1:
                raise KeyError(user_id)
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

    def reset_password(self, user_id: str, password: str) -> None:
        encoded = self.password_hash(password)
        with self.connect() as db:
            updated = db.execute('UPDATE users SET password=? WHERE id=?', (encoded, user_id))
            if updated.rowcount != 1:
                raise KeyError(user_id)
            # The password update and revocation commit in the same transaction.
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

    def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        encoded = self.password_hash(new_password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute('SELECT password FROM users WHERE id=? AND active=1', (user_id,)).fetchone()
            if not user:
                return False
            previous = user['password']
            if not hmac.compare_digest(previous, self.password_hash(current_password, previous.split(':')[0])):
                return False
            db.execute('UPDATE users SET password=? WHERE id=?', (encoded, user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            return True

    @contextmanager
    def project_creation(self, owner_id: str, name: str):
        # Serialize validation and insertion across concurrent server requests.
        # Legacy duplicates remain readable; new duplicates are rejected.
        key = name.strip().casefold()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT name FROM projects WHERE owner_id=? AND deleted_at IS NULL', (owner_id,))
            if any(row['name'].strip().casefold() == key for row in existing):
                raise DuplicateProjectNameError('已存在同名项目，请修改项目名称')
            yield db

    def index_project(self, project: dict, owner_id: str, connection: sqlite3.Connection | None = None) -> None:
        values = (project['project_id'], owner_id, project['name'], project.get('updated_at', ''))
        if connection is not None:
            connection.execute('INSERT INTO projects(id, owner_id, name, updated_at) VALUES (?,?,?,?)', values)
        else:
            with self.connect() as db:
                db.execute('INSERT OR IGNORE INTO projects(id, owner_id, name, updated_at) VALUES (?,?,?,?)', values)

    def project_record(self, project_id: str, *, include_deleted: bool = False) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row or (row['deleted_at'] and not include_deleted):
                return None
            return dict(row)

    def owner(self, project_id: str) -> str | None:
        record = self.project_record(project_id)
        return record['owner_id'] if record else None

    def user(self, user_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT id, username, admin, active FROM users WHERE id=?', (user_id,)).fetchone()
            return self._public_user(row) if row else None

    def list_projects(self, owner_id: str | None, query: str = '', offset: int = 0, limit: int = 50, *, deleted: bool = False) -> dict:
        conditions = ['p.name LIKE ?', 'p.deleted_at IS NOT NULL' if deleted else 'p.deleted_at IS NULL']
        args: list = [f'%{query}%']
        if owner_id is not None:
            conditions.append('p.owner_id=?')
            args.append(owner_id)
        where = ' AND '.join(conditions)
        with self.connect() as db:
            total = db.execute(f'SELECT COUNT(*) FROM projects p WHERE {where}', args).fetchone()[0]
            rows = db.execute(f'''SELECT p.id AS project_id, p.name, p.updated_at, p.owner_id,
                p.deleted_at, u.username AS owner_username FROM projects p JOIN users u ON p.owner_id=u.id
                WHERE {where} ORDER BY p.updated_at DESC, p.id LIMIT ? OFFSET ?''', (*args, limit, offset))
            return {'projects': [dict(row) for row in rows], 'total': total}
