"""F2-3: the vendoring sync gate runs inside the test suite.

Any drift between agent-assets (authoritative source) and the vendored
plugin-packages snapshot must fail before commit, not in review. Skips
gracefully where the agent-assets repo is absent (e.g. a formal-workspace
checkout that consumes releases instead of carrying the source repo).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ASSETS = Path(os.environ.get("NEXT_TRAINER_AGENT_ASSETS_ROOT", "") or PROJECT_ROOT.parent / "agent-assets")
SYNC_SCRIPT = AGENT_ASSETS / "scripts" / "sync-to-project.py"

pytestmark = pytest.mark.skipif(
    not SYNC_SCRIPT.is_file(),
    reason="agent-assets source repo not present in this checkout",
)


def test_agent_assets_vendoring_zero_drift():
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "vendored snapshot drifts from agent-assets; run agent-assets/scripts/sync-to-project.py "
        f"and commit both sides\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "in sync" in result.stdout
