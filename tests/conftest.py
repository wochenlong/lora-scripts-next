"""Workspace-safe temporary directories for the test process.

The DSH development sandbox (workspace-write policy) denies write access to
directories created via tempfile.mkdtemp / TemporaryDirectory even when they
live under project/.runtime/pytest-tmp, while directories created with a plain
os.mkdir remain fully writable.  The real-stack verifiers (agent_test_support
workspace_tempdir) already use the plain-mkdir pattern; this conftest applies
the same redirect process-wide so fixture-based tests (tmp_path) and direct
tempfile users keep working in the sandbox.

The redirect only affects this test process; production code is untouched.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parents[1] / ".runtime" / "pytest-tmp"


def _workspace_tmpdir(prefix: str = "pytest-") -> Path:
    _BASE.mkdir(parents=True, exist_ok=True)
    path = _BASE / f"{prefix}{uuid.uuid4().hex[:12]}"
    os.mkdir(path)
    return path


# --- session-wide tempfile redirect (sandbox denies writes into mkdtemp dirs) ---
def _mkdtemp(suffix: str | None = None, prefix: str | None = None, dir=None, text=None) -> str:
    del suffix, dir, text  # names are generated inside the safe base
    return str(_workspace_tmpdir((prefix or "tmp") + "-"))


tempfile.mkdtemp = _mkdtemp


class _SafeTemporaryDirectory(tempfile.TemporaryDirectory):
    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors: bool = False) -> None:
        del suffix, dir
        self._safe_path = _workspace_tmpdir((prefix or "tmp") + "-")
        super().__init__(str(self._safe_path), ignore_cleanup_errors=ignore_cleanup_errors)


tempfile.TemporaryDirectory = _SafeTemporaryDirectory  # type: ignore[misc,assignment]


@pytest.fixture
def tmp_path(request):
    """Override pytest's mkdtemp-backed fixture with the workspace-safe pattern."""
    del request
    path = _workspace_tmpdir("pytest-")
    yield path
    shutil.rmtree(path, ignore_errors=True)
