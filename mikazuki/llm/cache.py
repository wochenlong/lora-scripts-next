from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class CaptionCache:
    """SQLite cache shared by translation and caption LLM runtimes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS caption_translations (
                source_sha256 TEXT NOT NULL, profile_revision TEXT NOT NULL,
                target_language TEXT NOT NULL, translation TEXT NOT NULL,
                PRIMARY KEY(source_sha256, profile_revision, target_language))""")
            connection.execute("CREATE TABLE IF NOT EXISTS translation_cache_generation (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO translation_cache_generation VALUES (1, 0)")
            connection.execute("CREATE TABLE IF NOT EXISTS caption_cache_generation (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO caption_cache_generation VALUES (1, 0)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS caption_results (
                    image_sha256 TEXT NOT NULL,
                    profile_revision TEXT NOT NULL,
                    prompt_revision TEXT NOT NULL,
                    language TEXT NOT NULL,
                    preprocess_revision TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(image_sha256, profile_revision, prompt_revision, language, preprocess_revision)
                )
                """
            )

    def get(self, image_sha256: str, profile_revision: str, prompt_revision: str, language: str, preprocess_revision: str, *, expected_generation: int | None = None) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT caption FROM caption_results
                WHERE image_sha256 = ? AND profile_revision = ? AND prompt_revision = ?
                  AND language = ? AND preprocess_revision = ?
                  AND (? IS NULL OR (SELECT generation FROM caption_cache_generation WHERE id=1) = ?)
                """,
                (image_sha256, profile_revision, prompt_revision, language, preprocess_revision, expected_generation, expected_generation),
            ).fetchone()
        return str(row["caption"]) if row else None

    def put(self, image_sha256: str, profile_revision: str, prompt_revision: str, language: str, preprocess_revision: str, caption: str, *, expected_generation: int | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if expected_generation is not None and connection.execute("SELECT generation FROM caption_cache_generation WHERE id=1").fetchone()[0] != expected_generation:
                return
            connection.execute(
                """
                INSERT INTO caption_results(
                    image_sha256, profile_revision, prompt_revision, language,
                    preprocess_revision, caption, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_sha256, profile_revision, prompt_revision, language, preprocess_revision)
                DO UPDATE SET caption = excluded.caption, updated_at = excluded.updated_at
                """,
                (image_sha256, profile_revision, prompt_revision, language, preprocess_revision, caption, now, now),
            )

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM caption_results").fetchone()[0])

    def generation(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT generation FROM caption_cache_generation WHERE id=1").fetchone()[0])

    def clear(self) -> None:
        with self._connect() as connection:
            # Invalidation and deletion commit together so a pre-clear request
            # cannot refill this cache, including across runtime instances.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE caption_cache_generation SET generation=generation+1 WHERE id=1")
            connection.execute("DELETE FROM caption_results")

    def get_translation(self, source_hash, revision, language):
        with self._connect() as connection:
            row = connection.execute("SELECT translation FROM caption_translations WHERE source_sha256=? AND profile_revision=? AND target_language=?", (source_hash, revision, language)).fetchone()
        return row[0] if row else None

    def translation_generation(self):
        with self._connect() as connection:
            return connection.execute("SELECT generation FROM translation_cache_generation WHERE id=1").fetchone()[0]

    def put_translation(self, source_hash, revision, language, translation, *, expected_generation=None):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if expected_generation is not None and connection.execute("SELECT generation FROM translation_cache_generation WHERE id=1").fetchone()[0] != expected_generation:
                return
            connection.execute("INSERT OR REPLACE INTO caption_translations VALUES (?, ?, ?, ?)", (source_hash, revision, language, translation))

    def clear_translations(self):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE translation_cache_generation SET generation=generation+1 WHERE id=1")
            connection.execute("DELETE FROM caption_translations")

    def translation_count(self):
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM caption_translations").fetchone()[0]
