"""Incremental annotation storage; existing JSON is imported once, transactionally."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@contextmanager
def connect(path: Path, default: dict) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path.with_suffix('.sqlite3'), timeout=30)
    try:
        db.execute('PRAGMA busy_timeout=30000')
        if db.execute('PRAGMA user_version').fetchone()[0] == 0:
            with db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('PRAGMA user_version').fetchone()[0] == 0:
                    db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, data TEXT NOT NULL)')
                    db.execute('CREATE TABLE objects (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
                    db.execute('CREATE TABLE frames (frame INTEGER, object_id INTEGER, data TEXT NOT NULL, PRIMARY KEY(frame, object_id))')
                    db.execute('CREATE INDEX object_frames ON frames(object_id, frame)')
                    db.execute('CREATE TABLE prompts (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
                    db.execute('CREATE TABLE keyframes (frame INTEGER, object_id INTEGER, PRIMARY KEY(frame, object_id))')
                    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
                    replace(db, data)
                    db.execute('PRAGMA user_version=1')
        with db:
            yield db
    finally:
        db.close()


def replace(db: sqlite3.Connection, data: dict) -> None:
    for table in ('metadata', 'objects', 'frames', 'prompts', 'keyframes'):
        db.execute(f'DELETE FROM {table}')
    db.executemany('INSERT INTO metadata VALUES (?,?)',
                   [(k, dump(v)) for k, v in data.items() if k not in {'objects', 'frames', 'prompts', 'keyframes'}])
    db.executemany('INSERT INTO objects VALUES (?,?)',
                   [(int(k), dump(v)) for k, v in data.get('objects', {}).items()])
    db.executemany('INSERT INTO frames VALUES (?,?,?)',
                   [(int(f), int(k), dump(v)) for f, frame in data.get('frames', {}).items()
                    for k, v in frame.get('objects', {}).items()])
    db.executemany('INSERT INTO prompts(data) VALUES (?)', [(dump(v),) for v in data.get('prompts', [])])
    db.executemany('INSERT OR IGNORE INTO keyframes VALUES (?,?)',
                   [(v['frame_index'], v['object_id']) for v in data.get('keyframes', [])])


def snapshot(db: sqlite3.Connection) -> dict:
    data = {k: json.loads(v) for k, v in db.execute('SELECT key,data FROM metadata')}
    data['objects'] = {str(k): json.loads(v) for k, v in db.execute('SELECT id,data FROM objects ORDER BY id')}
    data['frames'] = {}
    for frame, object_id, value in db.execute('SELECT frame,object_id,data FROM frames ORDER BY frame,object_id'):
        data['frames'].setdefault(str(frame), {'objects': {}})['objects'][str(object_id)] = json.loads(value)
    data['prompts'] = [json.loads(v) for (v,) in db.execute('SELECT data FROM prompts ORDER BY id')]
    data['keyframes'] = [{'frame_index': f, 'object_id': o} for f, o in db.execute('SELECT frame,object_id FROM keyframes ORDER BY frame,object_id')]
    return data
