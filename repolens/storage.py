"""Small, transactional SQLite snapshot store. No source-repository writes."""

import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "repolens.sqlite3"


def connect(db_path=DEFAULT_DB):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id TEXT PRIMARY KEY, metadata TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS commits (
            run_id TEXT NOT NULL, hash TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(run_id, hash)
        );
        CREATE TABLE IF NOT EXISTS file_changes (
            run_id TEXT NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(run_id, position)
        );
        CREATE TABLE IF NOT EXISTS summaries (
            cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sprints (
            id TEXT PRIMARY KEY, repo_key TEXT NOT NULL, name TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            UNIQUE(repo_key, name)
        );
    """)
    return connection


def save_snapshot(snapshot, db_path=DEFAULT_DB):
    run_id = snapshot["meta"]["id"]
    db = connect(db_path)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO analysis_runs VALUES (?,?)", (run_id, json.dumps(snapshot["meta"], ensure_ascii=False)))
            db.execute("DELETE FROM commits WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM file_changes WHERE run_id=?", (run_id,))
            db.executemany("INSERT INTO commits VALUES (?,?,?)", [(run_id, c["hash"], json.dumps(c, ensure_ascii=False)) for c in snapshot["commits"]])
            db.executemany("INSERT INTO file_changes VALUES (?,?,?)", [(run_id, i, json.dumps(c, ensure_ascii=False)) for i, c in enumerate(snapshot["changes"])])
    finally:
        db.close()


def load_snapshot(run_id, db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        row = db.execute("SELECT metadata FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return {
            "meta": json.loads(row[0]),
            "commits": [json.loads(r[0]) for r in db.execute("SELECT payload FROM commits WHERE run_id=? ORDER BY rowid", (run_id,))],
            "changes": [json.loads(r[0]) for r in db.execute("SELECT payload FROM file_changes WHERE run_id=? ORDER BY position", (run_id,))],
        }
    finally:
        db.close()


def recent_runs(db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        return [json.loads(r[0]) for r in db.execute("SELECT metadata FROM analysis_runs ORDER BY rowid DESC LIMIT 10")]
    finally:
        db.close()


def load_summary(cache_key, db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        row = db.execute("SELECT payload FROM summaries WHERE cache_key=?", (cache_key,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        db.close()


def save_summary(cache_key, result, db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO summaries VALUES (?,?)", (cache_key, json.dumps(result, ensure_ascii=False)))
    finally:
        db.close()


def list_sprints(repo_key, db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        rows = db.execute("SELECT id, name, start_date, end_date FROM sprints WHERE repo_key=? ORDER BY start_date, name", (repo_key,)).fetchall()
        return [dict(zip(("id", "name", "start", "end"), row)) for row in rows]
    finally:
        db.close()


def save_sprint(repo_key, name, start, end, db_path=DEFAULT_DB, sprint_id=None):
    from datetime import date
    from uuid import uuid4
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Sprint 名称需为 1–100 个字符。")
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError("Sprint 开始日期不能晚于结束日期。")
    db = connect(db_path)
    try:
        with db:
            if sprint_id:
                cursor = db.execute("UPDATE sprints SET name=?,start_date=?,end_date=? WHERE id=? AND repo_key=?", (name, str(start), str(end), sprint_id, repo_key))
                if cursor.rowcount != 1:
                    raise ValueError("Sprint 不存在或不属于当前仓库。")
            else:
                sprint_id = uuid4().hex
                db.execute("INSERT INTO sprints VALUES (?,?,?,?,?)", (sprint_id, repo_key, name, str(start), str(end)))
        return sprint_id
    except sqlite3.IntegrityError as exc:
        raise ValueError("当前仓库已有同名 Sprint，请修改名称。") from exc
    finally:
        db.close()


def delete_sprint(repo_key, sprint_id, db_path=DEFAULT_DB):
    db = connect(db_path)
    try:
        with db:
            db.execute("DELETE FROM sprints WHERE repo_key=? AND id=?", (repo_key, sprint_id))
    finally:
        db.close()
