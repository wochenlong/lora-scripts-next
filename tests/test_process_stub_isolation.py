"""Regression for issue #95: process-launch test stubs must not leak.

``tests/test_process_mixed_precision_launch.py`` installs stand-in modules into
``sys.modules`` (including ``mikazuki.anima_fast_backend.service_resolver``) so
``mikazuki.process`` can be imported without the full GUI runtime. If those
stubs are not restored, a later test that imports the real
``mikazuki.anima_fast_backend.service_resolver`` (e.g.
``tests/test_anima_fast_backend.py``) fails during collection with::

    ImportError: cannot import name 'LegacyServiceResolverShim' from
    'mikazuki.anima_fast_backend.service_resolver' (unknown location)

This test runs the affected modules in the failing order inside a fresh
interpreter and asserts the run succeeds, exercising the snapshot/restore
``tearDownModule`` hooks that fix the leak.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


class ProcessStubIsolationTests(unittest.TestCase):
    def test_launch_stubs_do_not_break_anima_fast_import(self):
        modules = [
            "tests.test_process_train_log_url",
            "tests.test_process_mixed_precision_launch",
            "tests.test_anima_fast_backend",
        ]
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *modules],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=(
                "sys.modules stub leak regression failed (issue #95).\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
