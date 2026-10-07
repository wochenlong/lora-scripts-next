"""Durable caption job state in the shared LLM SQLite database.

Private recovery data (server paths and original caption backups) never enters
the public report. Credentials and provider envelopes are never persisted.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


REQUEST_FIELDS = {
    "path", "paths", "mode", "recursive", "allow_local_fallback", "use_cache",
    "profile_id", "prompt_id", "prompt", "language", "layout", "conflict_action",
    "interrogator_model", "download_endpoint", "threshold", "character_threshold",
    "add_rating_tag", "add_model_tag", "additional_tags", "exclude_tags", "escape_tag",
    "replace_underscore", "replace_underscore_excludes", "expected_hashes", "retry_failed",
    "_prompt_frozen",
    "max_caption_length",
}


class CaptionJobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS caption_jobs (
                job_id TEXT PRIMARY KEY, state TEXT NOT NULL, recovery TEXT NOT NULL,
                updated_at REAL NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS caption_backups (
                job_id TEXT NOT NULL, item_index INTEGER NOT NULL, content BLOB,
                before_hash TEXT, PRIMARY KEY(job_id, item_index))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS caption_formats (
                path TEXT PRIMARY KEY, after_hash TEXT NOT NULL, format TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]')""")
            if "tags" not in {row["name"] for row in connection.execute("PRAGMA table_info(caption_formats)")}:
                connection.execute("ALTER TABLE caption_formats ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
            if "writer_job_id" not in {row["name"] for row in connection.execute("PRAGMA table_info(caption_formats)")}:
                connection.execute("ALTER TABLE caption_formats ADD COLUMN writer_job_id TEXT")
            if "format_detail" not in {row["name"] for row in connection.execute("PRAGMA table_info(caption_backups)")}:
                connection.execute("ALTER TABLE caption_backups ADD COLUMN format_detail TEXT")
            connection.execute("""CREATE TABLE IF NOT EXISTS caption_rollbacks (
                job_id TEXT NOT NULL, item_index INTEGER NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY(job_id, item_index))""")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, state, request, paths, completed, failed, intent=None):
        recovery = {
            "request": {key: copy.deepcopy(value) for key, value in request.items() if key in REQUEST_FIELDS},
            "paths": list(paths), "completed": list(completed),
            "failed": copy.deepcopy(failed), "intent": copy.deepcopy(intent),
        }
        with self._connect() as connection:
            connection.execute("""INSERT INTO caption_jobs(job_id, state, recovery, updated_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(job_id) DO UPDATE SET
                state=excluded.state, recovery=excluded.recovery, updated_at=excluded.updated_at""",
                (state["job_id"], json.dumps(state, ensure_ascii=False),
                 json.dumps(recovery, ensure_ascii=False), state["updated_at"]))

    def backup(self, job_id, index, content, before_hash, format_detail=None):
        with self._connect() as connection:
            connection.execute("""INSERT OR IGNORE INTO caption_backups
                (job_id, item_index, content, before_hash, format_detail) VALUES (?, ?, ?, ?, ?)""",
                (job_id, index, content, before_hash, json.dumps(format_detail) if format_detail else None))

    def get_backup(self, job_id, index):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM caption_backups WHERE job_id=? AND item_index=?", (job_id, index)).fetchone()
        if not row:
            return None
        return {"content": row["content"], "before_hash": row["before_hash"],
                "format_detail": json.loads(row["format_detail"]) if row["format_detail"] else None}

    def rollback_status(self, job_id, index):
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM caption_rollbacks WHERE job_id=? AND item_index=?", (job_id, index)).fetchone()
        return row["status"] if row else None

    def mark_rollback(self, job_id, index, status):
        with self._connect() as connection:
            connection.execute("""INSERT INTO caption_rollbacks VALUES (?, ?, ?)
                ON CONFLICT(job_id,item_index) DO UPDATE SET status=excluded.status""", (job_id, index, status))

    def delete_history(self, job_id):
        # Format provenance remains necessary after history/backups are removed.
        with self._connect() as connection:
            for table in ("caption_backups", "caption_rollbacks", "caption_jobs"):
                connection.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))

    def get(self, job_id=None):
        with self._connect() as connection:
            if job_id:
                row = connection.execute("SELECT * FROM caption_jobs WHERE job_id=?", (job_id,)).fetchone()
            else:
                row = connection.execute("SELECT * FROM caption_jobs ORDER BY updated_at DESC, rowid DESC LIMIT 1").fetchone()
        return {"state": json.loads(row["state"]), "recovery": json.loads(row["recovery"])} if row else None

    def history(self, limit=20):
        with self._connect() as connection:
            rows = connection.execute("SELECT state FROM caption_jobs ORDER BY updated_at DESC, rowid DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [json.loads(row["state"]) for row in rows]

    def remember_format(self, path, after_hash, caption_format, tags=None, writer_job_id=None):
        import os
        key = os.path.normcase(str(Path(path).resolve()))
        with self._connect() as connection:
            connection.execute("""INSERT INTO caption_formats(path, after_hash, format, tags, writer_job_id) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET after_hash=excluded.after_hash, format=excluded.format, tags=excluded.tags, writer_job_id=excluded.writer_job_id""",
                (key, after_hash, caption_format, json.dumps(tags or [], ensure_ascii=False), writer_job_id))

    def format_owner(self, path, current_hash):
        import os
        key = os.path.normcase(str(Path(path).resolve()))
        with self._connect() as connection:
            row = connection.execute("SELECT writer_job_id FROM caption_formats WHERE path=? AND after_hash=?", (key, current_hash)).fetchone()
        return row["writer_job_id"] if row else None

    def format_record(self, path):
        import os
        key = os.path.normcase(str(Path(path).resolve()))
        with self._connect() as connection:
            row = connection.execute("SELECT after_hash, writer_job_id FROM caption_formats WHERE path=?", (key,)).fetchone()
        return dict(row) if row else None

    def forget_format(self, path):
        import os
        with self._connect() as connection:
            connection.execute("DELETE FROM caption_formats WHERE path=?", (os.path.normcase(str(Path(path).resolve())),))

    def find_format(self, path, current_hash):
        detail = self.find_format_detail(path, current_hash)
        return detail["format"] if detail else None

    def find_format_detail(self, path, current_hash):
        import os
        key = os.path.normcase(str(Path(path).resolve()))
        with self._connect() as connection:
            row = connection.execute("SELECT after_hash, format, tags FROM caption_formats WHERE path=?", (key,)).fetchone()
        if row and row["after_hash"] == current_hash:
            return {"format": row["format"], "tags": json.loads(row["tags"])}
        # An external edit invalidates actual Tag projections, but does not
        # make a previously natural/mixed caption safe for Tag cleanup.
        if row and current_hash is not None and row["format"] in {"natural", "mixed", "unknown"}:
            return {"format": "unknown", "tags": []}
        return None
