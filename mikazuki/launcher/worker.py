"""固定基础Python worker：旧动作单JSON；显式只读query协议返回有界JSONL。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

# -I 不信任 cwd/PYTHONPATH；只接入 Rust 已按发布清单核验的同目录源码。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mikazuki.launcher.control import dispatch
from mikazuki.launcher.runtime import ControlError, QueryControl


REQUEST_LIMIT = RESULT_LIMIT = 4 * 1024 * 1024
PROGRESS_LIMIT = 16 * 1024


def _encoded_frame(value, limit, query=None):
    data = bytearray()
    for piece in json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(value):
        if query is not None:
            query.check()
        encoded = piece.encode("utf-8")
        if len(data) + len(encoded) > limit:
            raise ControlError("query_output_too_large", "查询输出超过允许大小")
        data.extend(encoded)
    return data.decode("utf-8") + "\n"


def _write_frame(output, value, limit, query=None):
    encoded = _encoded_frame(value, limit, query)
    output.write(encoded)
    output.flush()


def _error(error, *, bounded):
    code = getattr(error, "code", "worker_error")
    message = str(error)
    if bounded:
        if not isinstance(code, str) or len(code) > 96:
            code = "worker_error"
        message = message.encode("utf-8")[:4096].decode("utf-8", errors="ignore")
    return {"schema_version": 1, "ok": False, "error": {"code": code, "message": message}}


def run_request(request, output):
    """小合同可直接调用；唯一真实stdout所有者仍是本worker线程。"""
    query = None
    try:
        query = QueryControl.from_request(
            request, emit=lambda frame: _write_frame(output, frame, PROGRESS_LIMIT))
        value = dispatch(request, query=query)
        result = {"schema_version": 1, "ok": True, "result": value}
        status = 0
        if query is not None:
            query.check()
            result.update(type="result", task_id=query.task_id, scope=query.scope)
            # 编码完成前仍检查同一总期限；失败时未输出半帧，转为唯一错误final。
            encoded = _encoded_frame(result, RESULT_LIMIT, query)
        else:
            encoded = json.dumps(result, ensure_ascii=False) + "\n"
    except Exception as error:
        # 输出管道已断时不能继续扫描/重复写；父桥负责自有Job/reader回收。
        if getattr(error, "code", "") == "query_output_closed":
            return 1
        result = _error(error, bounded=query is not None)
        status = 1
        if query is not None:
            result.update(type="result", task_id=query.task_id, scope=query.scope)
            encoded = _encoded_frame(result, RESULT_LIMIT)
        else:
            encoded = json.dumps(result, ensure_ascii=False) + "\n"
    try:
        output.write(encoded)
        output.flush()
    except (OSError, ValueError):
        return 1
    return status


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
    try:
        raw = sys.stdin.buffer.readline(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError("请求超过4MiB")
        request = json.loads(raw)
    except Exception as error:
        sys.stdout.write(json.dumps(_error(error, bounded=False), ensure_ascii=False) + "\n")
        return 1
    return run_request(request, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
