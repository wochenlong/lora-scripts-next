from __future__ import annotations

import sqlite3

from mikazuki.tag_translation.translation_store import TranslationStore


def test_v2_results_are_persistent_and_profile_isolated(tmp_path):
    path = tmp_path / "translations.sqlite3"
    store = TranslationStore(str(path))
    items = [{"name": "blue_eyes", "category": 0, "post_count": 10, "origin": "local"}]

    store.save_results("zh-CN", "mymemory", "mymemory-v1", items, {"blue_eyes": "蓝眼睛"})
    assert store.get_results("zh-CN", ["blue eyes"], "mymemory", "mymemory-v1")["blue eyes"]["text"] == "蓝眼睛"
    assert store.get_results("zh-CN", ["blue_eyes"], "llm", "model-a") == {}
    assert store.get_results("zh-CN", ["blue_eyes"], "mymemory", "mymemory-v2") == {}
    assert store.result_count("mymemory") == 1

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM translation_results_v2").fetchone()[0] == 1

