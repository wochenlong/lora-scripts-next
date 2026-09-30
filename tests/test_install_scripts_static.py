"""Static guards for issue #319: installers must not report success falsely.

The deep behavioural check lives in
``scripts/dev/test_install_retry_semantics.ps1`` (it needs a real PowerShell to
exercise output-stream semantics). These assertions are the cheap part, so the
regressions show up in a plain ``pytest tests/`` run as well.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8", errors="replace")


def _retry_function_body(source: str) -> str:
    start = source.index("function Invoke-PipInstallWithRetries")
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body = source[start:index + 1]
                break
    else:
        raise AssertionError("unbalanced braces in Invoke-PipInstallWithRetries")
    return "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))


def test_retry_helper_keeps_its_output_stream_clean():
    """Anything on the output stream turns `return $false` into a truthy array."""
    body = _retry_function_body(_read("install-cn.ps1"))

    assert "Write-Output" not in body
    assert re.search(r"pip install[^\r\n]*\|\s*Out-Host", body), body


def test_install_cn_upgrades_pip_with_an_explicit_lower_bound():
    """A bare `--upgrade pip` no-ops when the mirror index hides newer versions."""
    source = _read("install-cn.ps1")

    assert 'pip>=23.1' in source
    assert "--resume-retries" in source
    # The option must be conditional: python 3.10's ensurepip gives pip 23.0.1,
    # which rejects it during argument parsing on every single attempt.
    assert "Get-PipResumeRetriesArgs" in source


def test_installers_no_longer_install_torch_into_gui_env():
    """Training stacks live in engine-pack venvs; GUI installers stay slim."""
    for name in ("install-cn.ps1", "install.ps1", "install.bash", "setup_environment.py"):
        source = _read(name)
        assert "torch==" not in source, name
        assert "xformers" not in source, name


def test_install_ps1_never_calls_bare_pip():
    """`pip` not being resolvable is a PS error that leaves $LASTEXITCODE stale."""
    source = _read("install.ps1")

    bare = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"^\s*pip\s+(install|uninstall|download)\b", line)
    ]

    assert bare == [], bare
    assert "python -m pip install" in source


def test_source_launcher_refuses_a_venv_without_gui_deps():
    source = _read("run_gui_source.bat")

    assert r"venv\Lib\site-packages\fastapi\__init__.py" in source
