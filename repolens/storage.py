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
