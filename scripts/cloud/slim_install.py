#!/usr/bin/env python3
"""引擎 slim 安装驱动：在选定宿主解释器内运行（此时 GUI 依赖已装好，可 import mikazuki）。

由 scripts/cloud/bootstrap.py 以子进程方式调用：
  --deps-only   快照源码 + 装引擎 delta 依赖进宿主环境（不装 torch，复用宿主）
  --audit-only  只做安装后自检并回写 install_state
  默认          两者都做
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_musubi(deps_only: bool, audit_only: bool) -> int:
    from mikazuki.engines.musubi.environment import audit_slim_install, install_slim_dependencies
    from mikazuki.engines.musubi.extension_state import default_layout
    from mikazuki.engines.musubi.manifest import UPSTREAM
    from mikazuki.engines.musubi.settings import default_upstream_cache

    layout = default_layout(REPO_ROOT)
    if not audit_only:
        install_slim_dependencies(
            REPO_ROOT,
            layout,
            Path(sys.executable),
            default_upstream_cache(REPO_ROOT),
            source_commit=str(UPSTREAM.get("commit") or "") or None,
        )
    if not deps_only:
        result = audit_slim_install(REPO_ROOT, layout)
        return 0 if result.ok else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="引擎 slim 安装驱动（start_cloud 内部调用）")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--deps-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args(argv)

    if args.engine == "musubi":
        return _run_musubi(args.deps_only, args.audit_only)
    print(f"引擎 {args.engine} 尚不支持 slim 安装", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
