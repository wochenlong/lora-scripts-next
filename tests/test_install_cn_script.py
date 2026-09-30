from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_cn_keeps_pip_cache_enabled_for_large_downloads():
    script = (ROOT / "install-cn.ps1").read_text(encoding="utf-8")

    assert "$Env:PIP_NO_CACHE_DIR = 1" not in script


def test_install_cn_installs_gui_requirements_only():
    """Training stacks moved to engine-pack venvs; the main installer no
    longer installs torch/xformers into the GUI environment."""
    script = (ROOT / "install-cn.ps1").read_text(encoding="utf-8")

    assert "Invoke-PipInstallWithRetries" in script
    assert "$PackageInstallRetriesPerSource = 2" in script
    assert 'PackageArgs @("--upgrade", "-r", "requirements.txt")' in script
    assert "torch==" not in script
    assert "xformers" not in script
    assert "PytorchSources" not in script
