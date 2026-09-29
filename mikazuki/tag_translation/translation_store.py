# This file is adapted from ComfyUI-Autocomplete-Aaalice.
# Source snapshot: 37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0
# License: MIT; see docs/third_party/comfyui-autocomplete-aaalice-MIT.txt.
# Next Trainer changes are tracked in git history.

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


SQLITE_LOOKUP_CHUNK_SIZE = 500


def is_translation_acceptable(tag_name, text, locale, category=0):
    value = str(text or "").strip()
    if not value:
        return False
    if value.casefold() == str(tag_name or "").strip().casefold():
        return False
    normalized_locale = str(locale or "").replace("_", "-").lower()
    if normalized_locale.startswith("zh"):
        return any("\u3400" <= character <= "\u9fff" for character in value)
    if normalized_locale.startswith("ja"):
        return any(
            "\u3040" <= character <= "\u30ff" or "\u3400" <= character <= "\u9fff"
            for character in value
        )
    return True


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class TranslationStore:
    """Persistent dictionary for successful, locale-specific tag translations."""

    def __init__(self, database_path):
        self.database_path = database_path
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self):
        import os

        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    tag_name TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    text TEXT NOT NULL,
                    category INTEGER NOT NULL DEFAULT 0,
                    post_count INTEGER NOT NULL DEFAULT 0,
                    origin TEXT NOT NULL DEFAULT 'local',
                    model TEXT,
                    prompt_hash TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(tag_name, locale)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_failures (
                    tag_name TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    model TEXT,
                    prompt_hash TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(tag_name, locale)
                )
                """
            )
            invalid_rows = [
                (row["tag_name"], row["locale"])
                for row in connection.execute(
                    "SELECT tag_name, locale, text, category FROM translations"
                ).fetchall()
                if not is_translation_acceptable(
                    row["tag_name"],
                    row["text"],
                    row["locale"],
                    row["category"],
                )
            ]
            if invalid_rows:
                connection.executemany(
                    "DELETE FROM translations WHERE tag_name = ? AND locale = ?",
                    invalid_rows,
                )

    def get_many(self, locale, tag_names):
        names = list(dict.fromkeys(tag_names))
        if not names:
            return {}
        rows = []
        with self._connect() as connection:
            for index in range(0, len(names), SQLITE_LOOKUP_CHUNK_SIZE):
                chunk = names[index : index + SQLITE_LOOKUP_CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)
                rows.extend(
                    connection.execute(
                        f"SELECT * FROM translations WHERE locale = ? AND tag_name IN ({placeholders})",
                        (locale, *chunk),
                    ).fetchall()
                )
        return {row["tag_name"]: dict(row) for row in rows}

    def get_failures(self, locale, tag_names, model, prompt_hash):
        names = list(dict.fromkeys(tag_names))
        if not names:
            return set()
        found = set()
        with self._connect() as connection:
            for index in range(0, len(names), SQLITE_LOOKUP_CHUNK_SIZE):
                chunk = names[index : index + SQLITE_LOOKUP_CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT tag_name FROM translation_failures"
                    f" WHERE locale = ? AND model = ? AND prompt_hash = ? AND tag_name IN ({placeholders})",
                    (locale, model, prompt_hash, *chunk),
                ).fetchall()
                found.update(row["tag_name"] for row in rows)
        return found

    def save_failures(self, locale, items, tag_names, model, prompt_hash):
        known = {item["name"] for item in items}
        now = utc_now()
        rows = [
            (tag_name, locale, model, prompt_hash, now)
            for tag_name in tag_names
            if tag_name in known
        ]
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO translation_failures(tag_name, locale, model, prompt_hash, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag_name, locale) DO UPDATE SET
                    model = excluded.model,
                    prompt_hash = excluded.prompt_hash,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def catalog(self, locale):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT tag_name, locale, text, category, post_count, origin, updated_at
                  FROM translations
                 WHERE locale = ?
                   AND (origin != 'danbooru_api' OR post_count > 0)
                 ORDER BY post_count DESC, tag_name ASC
                """,
                (locale,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_many(self, locale, items, translations, model, prompt_hash):
        if not translations:
            return
        metadata = {item["name"]: item for item in items}
        rows = []
        now = utc_now()
        for tag_name, text in translations.items():
            item = metadata[tag_name]
            if not is_translation_acceptable(tag_name, text, locale, item["category"]):
                continue
            rows.append(
                (
                    tag_name,
                    locale,
                    text,
                    item["category"],
                    item["post_count"],
                    item["origin"],
                    model,
                    prompt_hash,
                    now,
                )
            )
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO translations(
                    tag_name, locale, text, category, post_count, origin, model, prompt_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tag_name, locale) DO UPDATE SET
                    text = excluded.text,
                    category = excluded.category,
                    post_count = excluded.post_count,
                    origin = excluded.origin,
                    model = excluded.model,
                    prompt_hash = excluded.prompt_hash,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            # A successful translation supersedes any recorded failure.
            connection.executemany(
                "DELETE FROM translation_failures WHERE tag_name = ? AND locale = ?",
                [(row[0], row[1]) for row in rows],
            )

    def count(self):
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0]

