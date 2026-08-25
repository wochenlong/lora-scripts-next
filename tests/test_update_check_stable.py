from mikazuki.update_check import (
    _has_stable_update,
    _pick_latest_stable,
    is_prerelease_version,
    is_stable_version,
)


def test_is_stable_version():
    assert is_stable_version("3.0.0")
    assert is_stable_version("v3.0.0")
    assert not is_stable_version("3.0.0-alpha")
    assert not is_stable_version("v3.0.0-rc.1")
    assert not is_stable_version("2.9.2-beta.1")


def test_is_prerelease_version():
    assert is_prerelease_version("3.0.0-alpha")
    assert is_prerelease_version("v2.9.2-beta.1")
    assert not is_prerelease_version("3.0.0")
    assert not is_prerelease_version("v3.0.1")


def test_has_stable_update_from_preview_to_same_base():
    assert _has_stable_update("3.0.0-alpha", "3.0.0")
    assert _has_stable_update("3.0.0-rc.1", "3.0.0")
    assert not _has_stable_update("3.0.0", "3.0.0")
    assert _has_stable_update("2.9.1", "3.0.0")


def test_pick_latest_stable_skips_prerelease():
    releases = [
        {"tag_name": "v3.0.0-alpha", "prerelease": True, "draft": False, "html_url": "a", "body": "pre"},
        {"tag_name": "v3.0.0", "prerelease": False, "draft": False, "html_url": "b", "body": "stable"},
        {"tag_name": "v2.9.1", "prerelease": False, "draft": False, "html_url": "c", "body": "old"},
    ]
    picked = _pick_latest_stable(releases)
    assert picked is not None
    assert picked["tag_name"] == "v3.0.0"
