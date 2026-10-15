"""Run the complete Issue #409 functional regression, preserving failures/skips.

Includes dataset/editor, unified LLM/translation, tagging, task/log projections,
configuration compatibility and SPA entry points. Agent/plugin/training stacks
are outside the user's revised scope, not silently marked as passing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PREFIXES = ("test_caption_", "test_llm_", "test_tagger_", "test_tag_translation_", "test_dataset", "test_task_", "test_user_data",
            "test_translation_", "test_tag_dictionary_", "test_local_text_", "test_local_vision_")
EXTRA = {
    "test_vision_service.py",
    "test_train_log_hub.py", "test_process_train_log_url.py", "test_config_import.py",
    "test_config_export.py", "test_vue_spa_routes.py", "test_train_utils_dataset_config.py",
    "test_startup_settings.py", "test_startup_proxy.py", "test_network_api.py",
    "test_network_policy.py", "test_path_browser.py", "test_get_files.py",
    "test_portable_data_dir_links.py", "test_portable_venv.py",
    "test_native_picker.py", "test_portable_packaging_scripts.py",
}


def known_environment_skip(item, platform):
    reason = item["reason"].lower()
    if any(marker in reason for marker in ("symlink privilege is unavailable", "symlink privilege unavailable", "symlinks unavailable")):
        return True
    # Keep the Linux CI useful without pretending Windows-only packaging and
    # junction operations ran there. The Windows job must execute these cases.
    if platform != "nt":
        expected = {
            "tests.test_portable_data_dir_links": {"junctions are windows-only"},
            "tests.test_tag_dictionary_packaging": {
                "actual release copy requires windows robocopy",
                "windows packaging requires powershell",
            },
        }
        return reason in expected.get(item["classname"], set())
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="New local report directory")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    if root.exists():
        parser.error("test report root must be new")
    root.mkdir(parents=True)
    selected = sorted(path for path in (repository / "tests").glob("test_*.py") if path.name.startswith(PREFIXES) or path.name in EXTRA)
    relative = [path.relative_to(repository).as_posix() for path in selected]
    manifest = {"contract": "Issue #409", "scope": "dataset-caption-translation-task-regression-v2",
                "python_version": sys.version, "python_executable": sys.executable,
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
                "files": [{"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in zip(relative, selected)]}
    (root / "scope.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    command = [sys.executable, "-m", "pytest", *relative, "-q", "-ra", f"--junitxml={root / 'junit.xml'}"]
    with (root / "pytest.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=repository, stdout=stream, stderr=subprocess.STDOUT, check=False)
    cases = ET.parse(root / "junit.xml").findall(".//testcase")
    failures = [case.attrib for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [{**case.attrib, "reason": case.find("skipped").get("message", "")} for case in cases if case.find("skipped") is not None]
    known_skips = [item for item in skipped if known_environment_skip(item, os.name)]
    unexpected_skips = [item for item in skipped if item not in known_skips]
    report = {"source_commit": manifest["source_commit"], "python_version": sys.version,
              "selected_files": len(selected), "testcases": len(cases),
              "exit_code": result.returncode, "failures": failures, "skipped": skipped,
              "known_environment_skips": known_skips, "unexpected_skips": unexpected_skips,
              "passed": result.returncode == 0 and not failures and not unexpected_skips}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected_files": len(selected), "testcases": len(cases), "exit_code": result.returncode,
                      "failed": len(failures), "skipped": len(skipped)}, ensure_ascii=True), flush=True)
    return result.returncode if result.returncode else (1 if unexpected_skips else 0)


if __name__ == "__main__":
    raise SystemExit(main())
