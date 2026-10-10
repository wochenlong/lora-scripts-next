from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_copy_policy_excludes_user_data():
    policy = (ROOT / "build-scripts/03-copy-project.ps1").read_text(encoding="utf-8-sig")
    assert '"user_data"' in policy.split("$copyPolicy =")[0]


def test_release_update_preserves_user_data():
    updater = (ROOT / "scripts/portable/update_from_release.ps1").read_text(encoding="utf-8-sig")
    copy_args = updater.split("$robocopyArgs = @(")[1].split(")\n")[0]
    assert '"user_data"' in copy_args


def test_user_data_ignored():
    assert "/user_data/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
