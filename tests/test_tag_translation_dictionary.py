from __future__ import annotations

import sqlite3

from mikazuki.tag_translation.chinese_dictionary_service import ChineseDictionaryService


def _make_dictionary(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE tags (
            name TEXT PRIMARY KEY,
            category INTEGER,
            cn_name TEXT,
            post_count INTEGER
        );
        INSERT INTO tags VALUES ('blue_eyes', 0, '蓝瞳', 100);
        INSERT INTO tags VALUES ('long_hair', 0, '长发', 200);
        INSERT INTO tags VALUES ('same_name', 0, 'same_name', 1);
        """
    )
    connection.commit()
    connection.close()


def test_dictionary_lookup_reads_only_usable_translations(tmp_path):
    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    service = ChineseDictionaryService(str(tmp_path))

    assert service._validate_database(str(database)) == 3
    service.database_path = str(database)
    rows = service.lookup(["blue_eyes", "long_hair", "same_name", "missing"])

    assert rows["blue_eyes"]["text"] == "蓝瞳"
    assert rows["long_hair"]["category"] == 0
    assert "same_name" not in rows
    assert "missing" not in rows


def test_dictionary_lookup_deduplicates_and_limits_input(tmp_path):
    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    service = ChineseDictionaryService(str(tmp_path))
    service.database_path = str(database)

    rows = service.lookup(["blue_eyes", "blue_eyes", "", "long_hair"])

    assert set(rows) == {"blue_eyes", "long_hair"}
