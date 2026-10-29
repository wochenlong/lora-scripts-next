"""使用已核验基础 Python 执行：python -I -S <worker.py>；单行 JSON 协议。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

# -I 不信任 cwd/PYTHONPATH；只接入 Rust 已按发布清单核验的同目录源码。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mikazuki.launcher.control import dispatch


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    try:
        raw = sys.stdin.buffer.readline(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("请求超过4MiB")
        request = json.loads(raw)
        result = {"schema_version": 1, "ok": True, "result": dispatch(request)}
        status = 0
    except Exception as error:
        result = {"schema_version": 1, "ok": False, "error": {"code": getattr(error, "code", "worker_error"), "message": str(error)}}
        status = 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
