from pathlib import Path

from mikazuki.llm.cache import CaptionCache


def test_caption_cache_round_trip_and_revision_isolation(tmp_path: Path):
    cache = CaptionCache(tmp_path / "translations.sqlite3")
    key = ("image-sha", "profile-v1", "prompt-v1", "zh-CN", "jpeg-v1")
    assert cache.get(*key) is None
    cache.put(*key, "一只猫。")
    assert cache.get(*key) == "一只猫。"
    assert cache.get("image-sha", "profile-v2", "prompt-v1", "zh-CN", "jpeg-v1") is None
    assert cache.count() == 1
    cache.clear()
    assert cache.count() == 0
