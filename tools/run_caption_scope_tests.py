"""Run the complete Issue #409 functional regression, preserving failures/skips.

Includes dataset/editor, unified LLM/translation, tagging, task/log projections,
configuration compatibility and SPA entry points. Agent/plugin/training stacks
are outside the user's revised scope, not silently marked as passing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PREFIXES = ("test_caption_", "test_llm_", "test_tagger_", "test_tag_translation_", "test_dataset", "test_task_")
EXTRA = {"test_local_vision_manager.py", "test_vision_service.py", "test_train_log_hub.py", "test_process_train_log_url.py",
         "test_config_import.py", "test_config_export.py", "test_vue_spa_routes.py", "test_train_utils_dataset_config.py"}


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
    manifest = {"contract": "Issue #409", "scope": "dataset-caption-translation-task-regression-v1",
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
                "files": [{"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in zip(relative, selected)]}
    (root / "scope.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    command = [sys.executable, "-m", "pytest", *relative, "-q", "-ra", f"--junitxml={root / 'junit.xml'}"]
    with (root / "pytest.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=repository, stdout=stream, stderr=subprocess.STDOUT, check=False)
    cases = ET.parse(root / "junit.xml").findall(".//testcase")
    failures = [case.attrib for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [{**case.attrib, "reason": case.find("skipped").get("message", "")} for case in cases if case.find("skipped") is not None]
    report = {"source_commit": manifest["source_commit"], "selected_files": len(selected), "testcases": len(cases),
              "exit_code": result.returncode, "failures": failures, "skipped": skipped, "passed": result.returncode == 0 and not skipped}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected_files": len(selected), "testcases": len(cases), "exit_code": result.returncode,
                      "failed": len(failures), "skipped": len(skipped)}, ensure_ascii=True), flush=True)
    return result.returncode if result.returncode else (1 if skipped else 0)


if __name__ == "__main__":
    raise SystemExit(main())
