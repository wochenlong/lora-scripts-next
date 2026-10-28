"""验证施工计划静态结构；不执行产品、网络、Git写入或真实验收。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote


PHASES = [
    ("M0", "审核冻结与开发基线"),
    ("M1", "可靠安装与精准修复"),
    ("M2", "首批引擎真实闭环"),
    ("M3", "四引擎与可信更新"),
    ("M4", "资料导入与兼容回退"),
    ("M5", "独立壳与Windows分发"),
    ("M6", "从零沙盒最终验收"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preservation-snapshot", type=Path)
    args = parser.parse_args()
    plan = Path(__file__).resolve().parents[1]
    repo = plan.parents[2]
    issues: list[str] = []
    required = [
        "README.md",
        "plan-manifest.md",
        "00_总控目标索引.md",
        "06_开工前最终复盘报告.md",
        "07_用户审计单.md",
        "01_目标计划书/00_目标计划书索引.md",
        "03_goal提示词/桌面启动器全程执行_goal提示词.md",
        "05_最小可行性验证/minimal-feasibility-probe-plan.md",
        "05_最小可行性验证/feasibility-probe-report.md",
        "scripts/validate_plan.py",
    ]
    governance = [
        "README.md", "preflight-source-review.md", "gate-validation-checklist.md",
        "testing-and-evidence-governance.md", "risk-and-authorization-governance.md",
        "git-baseline-governance.md", "change-control-governance.md",
        "stage-completion-gate-template.md", "failure-report-template.md",
        "evidence-cleanup-report-template.md", "feasibility-probe-report-template.md",
    ]
    required += [f"00_预检证据/{name}" for name in governance]
    task_paths = []
    for number, (phase, title) in enumerate(PHASES, 1):
        required += [
            f"01_目标计划书/{number:02}_目标{phase}_{title}_实施验收计划.md",
            f"02_长程任务书/阶段{phase}_{title}_目标{phase}_长程任务书.md",
            f"04_阶段开工清单/阶段{phase}_{title}_执行前清单.md",
        ]
        task_paths.append(plan / required[-2])
    for relative in required:
        if not (plan / relative).is_file():
            issues.append(f"missing: {relative}")
    actual = sorted(
        p.relative_to(plan).as_posix() for p in plan.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    for extra in set(actual) - set(required):
        issues.append(f"unindexed artifact: {extra}")
    manifest = (plan / "plan-manifest.md").read_text(encoding="utf-8") if (plan / "plan-manifest.md").exists() else ""
    for relative in required:
        if f"]({relative})" not in manifest:
            issues.append(f"manifest missing link: {relative}")
    checked_links = 0
    for doc in sorted(plan.rglob("*.md")):
        try:
            content = doc.read_text(encoding="utf-8")
        except UnicodeError as exc:
            issues.append(f"invalid UTF-8: {doc.name}: {exc}")
            continue
        if content.startswith("\ufeff") or "\ufffd" in content:
            issues.append(f"BOM or replacement character: {doc.name}")
        if content.endswith("\n\n"):
            issues.append(f"extra blank line at EOF: {doc.name}")
        fence = False
        for number, line in enumerate(content.splitlines(), 1):
            if line.rstrip() != line:
                issues.append(f"trailing whitespace: {doc.name}:{number}")
            if re.match(r"^(<<<<<<< |=======|>>>>>>> )", line):
                issues.append(f"conflict marker: {doc.name}:{number}")
            if line.lstrip().startswith("```"):
                fence = not fence
        if fence:
            issues.append(f"unclosed code fence: {doc.name}")
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", content):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-zA-Z][\w+.-]*://", target):
                continue
            destination = Path(unquote(target))
            if not destination.is_absolute():
                destination = doc.parent / destination
            checked_links += 1
            if not destination.exists():
                issues.append(f"broken link: {doc.relative_to(plan).as_posix()} -> {target}")
    for doc in task_paths:
        if doc.exists():
            content = doc.read_text(encoding="utf-8").lower()
            for family in ["unit", "contract", "integration", "gray", "real", "zero-short"]:
                if family not in content:
                    issues.append(f"test family absent: {doc.name}: {family}")
    gates = plan / "00_预检证据/gate-validation-checklist.md"
    if gates.exists():
        content = gates.read_text(encoding="utf-8")
        for number in range(15):
            if f"GATE-{number:02}" not in content:
                issues.append(f"missing GATE-{number:02}")
        for phase, _ in PHASES:
            if f"EXIT-{phase}" not in content:
                issues.append(f"missing EXIT-{phase}")
    preserved = None
    if args.preservation_snapshot:
        before = json.loads(args.preservation_snapshot.read_text(encoding="utf-8"))
        preserved = 0
        for relative, expected in before["files"].items():
            path = repo / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                issues.append(f"pre-existing file changed: {relative}")
            else:
                preserved += 1
    result = {
        "result": "pass" if not issues else "fail",
        "scope": "static-plan-validation-only",
        "root": str(plan),
        "artifact_count": len(actual),
        "markdown_count": len(list(plan.rglob("*.md"))),
        "local_links_checked": checked_links,
        "phase_count": len(PHASES),
        "preserved_files": preserved,
        "issues": issues,
        "product_tests": "not-evaluated-by-static-validator",
        "implementation": "see-canonical-progress",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
