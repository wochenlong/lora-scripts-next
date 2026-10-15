"""The strict runner must distinguish platform scope from missing coverage."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("caption_scope_runner", Path(__file__).parents[1] / "tools/run_caption_scope_tests.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("classname,reason,platform,expected", [
    ("tests.test_portable_data_dir_links", "junctions are Windows-only", "posix", True),
    ("tests.test_portable_data_dir_links", "junctions are Windows-only", "nt", False),
    ("tests.test_tag_dictionary_packaging", "Actual Release copy requires Windows robocopy", "posix", True),
    ("tests.test_tag_dictionary_packaging", "Windows packaging requires PowerShell", "nt", False),
    ("tests.test_caption_translation", "Actual Release copy requires Windows robocopy", "posix", False),
    ("tests.test_task_insights", "tensorboard not available", "nt", False),
])
def test_known_skip_requires_the_right_platform_and_suite(classname, reason, platform, expected):
    assert runner.known_environment_skip({"classname": classname, "reason": reason}, platform) is expected
