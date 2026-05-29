import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_source_contract_is_declared():
    result = subprocess.run(
        [sys.executable, "scripts/verify_frontend_source.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "frontend source contract OK" in result.stdout


def test_frontend_source_settings_page_owns_tagger_api_config():
    settings = (ROOT / "frontend" / "source" / "src" / "settings.ts").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "frontend" / "source" / "src" / "main.ts").read_text(encoding="utf-8")

    assert "SettingsPage" in main
    assert 'route.path === "/other/settings.html"' in main
    assert "ui-configs" in settings
    assert "dataset_tagger_api_endpoint" in settings
    assert "dataset_tagger_api_key" in settings
    assert "dataset_tagger_api_model" in settings
    assert "dataset_tagger_api_prompt" in settings
    assert 'type: "password"' in settings
    assert "sd-trainer-ui-advanced-links" in settings
    assert "showLegacyTagEditor" in settings
    assert "showTensorboard" in settings
