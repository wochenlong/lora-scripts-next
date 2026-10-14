from __future__ import annotations

import sqlite3

import pytest

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


def test_dictionary_lookup_normalizes_spaces_and_prefers_longest_match(tmp_path):
    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO tags VALUES ('blue_eyes_extra', 0, '蓝眼睛扩展', 2)")
    connection.commit()
    connection.close()
    service = ChineseDictionaryService(str(tmp_path))
    service.database_path = str(database)

    rows = service.lookup(["blue eyes", "blue_eyes_extra"])

    assert rows["blue eyes"]["text"] == "蓝瞳"
    assert rows["blue_eyes_extra"]["text"] == "蓝眼睛扩展"


def test_dictionary_lookup_resolves_native_tagger_parenthesis_escapes(tmp_path):
    from mikazuki.tagger.interrogators.base import Interrogator

    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO tags VALUES (?, 0, ?, 1)",
            [(";)", "眨眼笑"), ("poster_(object)", "海报（物体）")],
        )
    serialized = Interrogator.postprocess_tags(
        {"general": [(";)", 1.0), ("poster_(object)", 0.9)]},
        replace_underscore=True,
        escape_tag=True,
    )
    assert list(serialized) == [r";\)", r"poster \(object\)"]

    rows = ChineseDictionaryService(str(tmp_path)).lookup(list(serialized))

    assert rows[r";\)"]["text"] == "眨眼笑"
    assert rows[r"poster \(object\)"]["text"] == "海报（物体）"
    assert set(rows) == set(serialized)


@pytest.mark.parametrize(
    "tag",
    [r"poster \\(object\\)", r"poster \\\(object\\\)", r"poster \[object\]"],
)
def test_dictionary_lookup_does_not_strip_literal_or_other_escapes(tmp_path, tag):
    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO tags VALUES (?, 0, ?, 1)",
            [("poster_(object)", "海报（物体）"), ("poster_[object]", "方括号海报")],
        )

    assert ChineseDictionaryService(str(tmp_path)).lookup([tag]) == {}


def test_dictionary_lookup_prefers_literal_backslash_match(tmp_path):
    database = tmp_path / "tag.sqlite"
    _make_dictionary(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO tags VALUES (?, 0, ?, 1)",
            [
                (r"literal\(name\)", "含反斜杠的原始标签"),
                ("literal(name)", "无反斜杠标签"),
                (r"path\name", "路径标签"),
                (r"path\\name", "双反斜杠路径标签"),
            ],
        )
    rows = ChineseDictionaryService(str(tmp_path)).lookup(
        [r"literal\(name\)", r"path\name", r"path\\name"]
    )

    assert rows[r"literal\(name\)"]["text"] == "含反斜杠的原始标签"
    assert rows[r"path\name"]["text"] == "路径标签"
    assert rows[r"path\\name"]["text"] == "双反斜杠路径标签"


def test_dictionary_download_candidates_prefer_github_api_over_raw_host():
    candidates = ChineseDictionaryService._candidate_download_urls(
        "https://raw.githubusercontent.com/ffdkj/repo/main/tag.sqlite"
    )
    assert candidates[0].startswith("https://ghfast.top/")
    assert any("api.github.com" in candidate for candidate in candidates)
    assert "raw.githubusercontent.com" in candidates[-1]
