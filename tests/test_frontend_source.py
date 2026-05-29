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
