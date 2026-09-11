#!/usr/bin/env python3
"""nt.py — Next Trainer agent CLI (stdlib-only).

Talks to a running Next Trainer HTTP API. No third-party dependencies;
any python3 works. Connection: --base-url / NT_BASE_URL (default
http://127.0.0.1:28000). Remote use: ssh port-forward or a LAN URL.

Every command prints a JSON object on stdout; failures print a JSON error
on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:28000"
TERMINAL_STATUSES = {"FINISHED", "FAILED", "TERMINATED"}
BUSY_STATUSES = {"RUNNING", "QUEUED"}
TASK_KEEP_FIELDS = ("id", "status", "lane", "returncode", "created_at", "finished_at")
LOG_TAIL_CAP = 2000


class ApiError(Exception):
    pass


class Client:
    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, *, params: dict | None = None, body=None):
        url = self.base_url + path
        if params:
            from urllib.parse import urlencode

            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise ApiError(f"无法连接 Next Trainer 后端 {self.base_url}（{reason}）—— 请先启动主程序")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(f"后端返回非 JSON: {raw[:500]!r}")

        if isinstance(payload, dict) and payload.get("status") == "fail":
            raise ApiError(payload.get("message") or "后端返回失败")
        if isinstance(payload, dict) and "detail" in payload and "data" not in payload:
            raise ApiError(f"后端错误: {payload['detail']}")
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"] if payload["data"] is not None else payload
        return payload

    def request_raw(self, path: str, *, params: dict | None = None) -> tuple[bytes, str]:
        url = self.base_url + path
        if params:
            from urllib.parse import urlencode

            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return resp.read(), resp.headers.get("content-type", "application/octet-stream")
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise ApiError(f"请求 {path} 失败: {reason}")


# ---------------------------------------------------------------- task helpers


def fetch_tasks(client: Client) -> list[dict]:
    data = client.request("GET", "/api/tasks")
    tasks = data.get("tasks") if isinstance(data, dict) else None
    return tasks if isinstance(tasks, list) else []


def compact_task(t: dict) -> dict:
    out = {k: t.get(k) for k in TASK_KEEP_FIELDS if t.get(k) is not None}
    metadata = t.get("metadata") or {}
    if metadata.get("train_type"):
        out["train_type"] = metadata["train_type"]
    if metadata.get("error"):
        out["error"] = metadata["error"]
    return out


def find_task(client: Client, task_id: str) -> dict:
    for t in fetch_tasks(client):
        if isinstance(t, dict) and t.get("id") == task_id:
            return t
    raise ApiError(f"未知任务: {task_id}（用 tasks 看现有任务）")


def busy_tasks(client: Client) -> list[dict]:
    return [
        t
        for t in fetch_tasks(client)
        if isinstance(t, dict)
        and t.get("status") in BUSY_STATUSES
        and t.get("lane", "compute") == "compute"
    ]


def load_json_arg(value: str):
    """Config argument: a path to a JSON file, '-' for stdin, or inline JSON."""
    if value == "-":
        return json.load(sys.stdin)
    if Path(value).is_file():
        return json.loads(Path(value).read_text(encoding="utf-8"))
    return json.loads(value)


def downsample(points: list, max_points: int) -> list:
    if max_points <= 0 or len(points) <= max_points:
        return points
    stride = len(points) / max_points
    picked = [points[int(i * stride)] for i in range(max_points - 1)]
    picked.append(points[-1])
    return picked


SUBMIT_MIN_INTERVAL_S = 2.5


def _submit_stamp_path(base_url: str) -> Path:
    import hashlib

    key = hashlib.md5(base_url.encode()).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / f"nt-last-submit-{key}.stamp"


def submit_throttle(client: Client):
    """Backend autosaves configs to second-resolution filenames; submits within the
    same second overwrite each other and tasks read back the wrong config.
    Enforce a minimum interval between submits (stateless CLI → stamp file)."""
    stamp = _submit_stamp_path(client.base_url)
    if stamp.exists():
        elapsed = time.time() - stamp.stat().st_mtime
        if elapsed < SUBMIT_MIN_INTERVAL_S:
            wait = SUBMIT_MIN_INTERVAL_S - elapsed
            time.sleep(wait)
    stamp.write_text(str(time.time()))


def submit_config(client: Client, config: dict, confirm_queue: bool) -> dict:
    if not isinstance(config, dict) or not config.get("model_train_type"):
        raise ApiError("config 必须是包含 model_train_type 的字典；先 schemas 查字段、validate 校验")

    warnings = check_config_warnings(config)
    if warnings:
        raise ApiError("配置存在已知坑位: " + "；".join(warnings) + "（修正后再提交）")

    busy = busy_tasks(client)
    if busy and not confirm_queue:
        summary = [{"id": t.get("id"), "status": t.get("status")} for t in busy]
        raise ApiError(
            f"已有 {len(busy)} 个任务在运行/排队: {summary}。"
            "向用户确认排队意图后加 --confirm-queue 重试。"
        )

    submit_throttle(client)
    result = client.request("POST", "/api/run", body=config)
    return {
        "task_id": result.get("task_id"),
        "queued": result.get("queued"),
        "hint": "用 log-tail / metrics 轮询进度（间隔 >= 30 秒）；排错加大 log --limit",
    }


# ---------------------------------------------------------------- commands


def cmd_version(c, a):
    return c.request("GET", "/api/version")


def cmd_schemas(c, a):
    return c.request("GET", "/api/schemas/all")


# ------------------------------------------------------------ schema helpers

SCHEMA_FIELD_RE = re.compile(r"^\s*(\w+)\s*:\s*Schema\.")
SKILL_ROOT = Path(__file__).resolve().parent.parent


def schema_pages(client: Client) -> list[dict]:
    data = client.request("GET", "/api/schemas/all")
    pages = data.get("schemas") if isinstance(data, dict) else data
    if not isinstance(pages, list):
        raise ApiError(f"schemas 响应格式异常: {type(data).__name__}")
    return [p for p in pages if isinstance(p, dict) and p.get("name") and p.get("schema")]


def _extract_call_arg(text: str, marker: str, start: int) -> str:
    """Extract raw arg of .marker( ... ) starting at start, paren-balanced."""
    i = text.find(marker, start)
    if i < 0:
        return ""
    i += len(marker)
    depth, j = 1, i
    while j < len(text) and depth:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
        j += 1
    return text[i : j - 1].strip() if depth == 0 else ""


def extract_schema_fields(schema_text: str) -> list[dict]:
    """Pull compact field info (name / default / description) out of schema JS text."""
    fields = []
    for line in schema_text.splitlines():
        m = SCHEMA_FIELD_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        body = line[m.end():]
        field = {"name": name}
        default = _extract_call_arg(body, ".default(", 0)
        if default:
            field["default"] = default[:120]
        dm = re.search(r"\.description\(\s*([\"'])(.*?)\1", body)
        if dm:
            field["description"] = dm.group(2)
        if ".required()" in body:
            field["required"] = True
        if ".hidden()" in body:
            field["hidden"] = True
        um = re.search(r"Schema\.union\(\[(.*?)\]\)", body)
        if um:
            choices = re.findall(r"[\"']([^\"']+)[\"']", um.group(1))
            if choices:
                field["choices"] = choices
        fields.append(field)
    return fields


def find_page(pages: list[dict], name: str) -> dict:
    for p in pages:
        if p["name"] == name:
            return p
    lowered = name.lower()
    hits = [p for p in pages if lowered in p["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    names = [p["name"] for p in pages]
    raise ApiError(f"页面 {name!r} 不唯一或不存在（命中 {len(hits)} 个）；可选: {names}")


def cmd_params(c, a):
    pages = schema_pages(c)
    if a.page == "":
        return {"pages": [p["name"] for p in pages], "hint": "params <page> 看字段紧凑表，--filter 过滤"}
    page = find_page(pages, a.page)
    fields = extract_schema_fields(page["schema"])
    seen = set()
    fields = [f for f in fields if (key := (f["name"], f.get("default"), f.get("description"))) not in seen and not seen.add(key)]
    if a.filter:
        kw = a.filter.lower()
        fields = [f for f in fields if kw in json.dumps(f, ensure_ascii=False).lower()]
    return {"page": page["name"], "count": len(fields), "fields": fields}


def cmd_search(c, a):
    kw = a.keyword.lower()
    out = {"keyword": a.keyword}

    param_hits = []
    seen = set()
    for p in schema_pages(c):
        for f in extract_schema_fields(p["schema"]):
            key = (p["name"], f["name"], f.get("default"), f.get("description"))
            if key in seen:
                continue
            seen.add(key)
            if kw in json.dumps(f, ensure_ascii=False).lower():
                param_hits.append({"page": p["name"], **f})
                if len(param_hits) >= a.max_matches:
                    break
    out["schema_params"] = param_hits

    doc_hits = []
    docs = [SKILL_ROOT / "SKILL.md"] + sorted((SKILL_ROOT / "reference").glob("*.md"))
    for doc in docs:
        if not doc.is_file():
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if kw in line.lower():
                doc_hits.append({"file": doc.name, "line": lineno, "text": line.strip()[:200]})
                if len(doc_hits) >= a.max_matches:
                    break
    out["docs"] = doc_hits
    out["hint"] = "字段详情: params <page> --filter <关键字>；文档原文: Read reference/<file>"
    return out


def cmd_presets(c, a):
    return c.request("GET", "/api/presets")


def cmd_saved_params(c, a):
    return c.request("GET", "/api/config/saved_params")


def cmd_gpus(c, a):
    return c.request("GET", "/api/graphic_cards")


def cmd_gpu_status(c, a):
    return c.request("GET", "/api/graphic_cards/live")


def cmd_tasks(c, a):
    tasks = [t for t in fetch_tasks(c) if isinstance(t, dict)]
    if a.status == "active":
        tasks = [t for t in tasks if t.get("status") not in TERMINAL_STATUSES]
    elif a.status == "finished":
        tasks = [t for t in tasks if t.get("status") in TERMINAL_STATUSES]
    elif not a.status:
        active = [t for t in tasks if t.get("status") not in TERMINAL_STATUSES]
        finished = [t for t in tasks if t.get("status") in TERMINAL_STATUSES]
        tasks = active + finished[-a.limit :]
    tasks = tasks[-a.limit :] if a.limit > 0 else tasks
    return {"tasks": [compact_task(t) for t in tasks], "returned": len(tasks)}


def cmd_last_task(c, a):
    tasks = fetch_tasks(c)
    if not tasks:
        raise ApiError("当前没有任何任务")

    def created(t):
        try:
            return float(t.get("created_at") or 0)
        except (TypeError, ValueError):
            return 0.0

    if any(created(t) > 0 for t in tasks):
        return compact_task(max(tasks, key=created))
    return compact_task(tasks[-1])


def cmd_status(c, a):
    return compact_task(find_task(c, a.task_id))


def cmd_config(c, a):
    return c.request("GET", f"/api/tasks/{a.task_id}/config")


def cmd_metrics(c, a):
    data = c.request("GET", f"/api/tasks/{a.task_id}/metrics")
    tags = data.get("tags") if isinstance(data, dict) else None
    if isinstance(tags, dict):
        data["tags"] = {
            k: downsample(v, a.max_points) if isinstance(v, list) else v for k, v in tags.items()
        }
    return data


def cmd_log_tail(c, a):
    limit = max(1, min(a.limit, LOG_TAIL_CAP))
    return c.request("GET", f"/api/train/log/tail/{a.task_id}", params={"limit": limit})


def cmd_grep_log(c, a):
    limit = max(1, min(a.limit, LOG_TAIL_CAP))
    tail = c.request("GET", f"/api/train/log/tail/{a.task_id}", params={"limit": limit})
    lines = tail.get("lines") or []
    needle = a.pattern.lower()
    matches = [{"line": i, "text": text} for i, text in enumerate(lines) if needle in text.lower()]
    return {
        "matches": matches[: max(1, a.max_matches)],
        "total_matches": len(matches),
        "scanned_lines": len(lines),
        "done": tail.get("done"),
    }


def cmd_overview(c, a):
    overview = {"task": compact_task(find_task(c, a.task_id))}
    try:
        metrics = c.request("GET", f"/api/tasks/{a.task_id}/metrics")
        tags = metrics.get("tags") or {}
        overview["progress"] = metrics.get("progress")
        overview["latest_metrics"] = {k: v[-1] for k, v in tags.items() if isinstance(v, list) and v}
    except ApiError as exc:
        overview["metrics_error"] = str(exc)
    tail = cmd_log_tail(c, argparse.Namespace(task_id=a.task_id, limit=a.log_lines))
    overview["log_tail"] = tail.get("lines", [])
    overview["log_done"] = tail.get("done")
    try:
        previews = c.request("GET", f"/api/tasks/{a.task_id}/previews")
        overview["preview_count"] = len(previews.get("images") or [])
    except ApiError:
        overview["preview_count"] = 0
    return overview


def cmd_previews(c, a):
    return c.request("GET", f"/api/tasks/{a.task_id}/previews")


def cmd_preview(c, a):
    name = a.name
    if not name:
        data = c.request("GET", f"/api/tasks/{a.task_id}/previews")
        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise ApiError("该任务还没有预览图（确认配置已开 enable_preview 且配了 sample_prompts）")
        name = images[-1]["name"]
    content, media_type = c.request_raw(f"/api/tasks/{a.task_id}/previews/{name}", params={"thumb": 1})
    ext = ".jpg" if "jpeg" in media_type else ".png"
    out = a.out or str(Path(tempfile.gettempdir()) / f"nt-preview-{a.task_id[:8]}-{name}{ext}")
    Path(out).write_bytes(content)
    return {"path": out, "name": name, "bytes": len(content), "hint": "用 Read 工具查看该图片文件"}


def cmd_outputs(c, a):
    return c.request("GET", f"/api/tasks/{a.task_id}/outputs")


def check_config_warnings(config: dict) -> list[str]:
    """Client-side sanity warnings for known pitfalls (non-blocking)."""
    warnings = []
    prompts = config.get("sample_prompts")
    if config.get("enable_preview") and isinstance(prompts, str) and prompts:
        if not Path(prompts).is_file():
            warnings.append(
                "sample_prompts 不是存在的文件路径——Anima 后端按文件路径解析，"
                "内联文本会导致采样静默失败（No prompt file）。先把 prompt 写成文件再传路径。"
            )
    if isinstance(config.get("learning_rate"), str):
        warnings.append("learning_rate 是字符串——Automagic 对字符串 lr 会 TypeError，请传 JSON 数值。")
    return warnings


def cmd_validate(c, a):
    config = load_json_arg(a.config)
    result = c.request(
        "POST", "/api/config/validate-import",
        body={"page_train_type": a.page_train_type, "config": config},
    )
    warnings = check_config_warnings(config)
    if warnings and isinstance(result, dict):
        result["client_warnings"] = warnings
    return result


def cmd_submit(c, a):
    return submit_config(c, load_json_arg(a.config), a.confirm_queue)


def cmd_submit_preset(c, a):
    data = c.request("GET", "/api/presets")
    presets = data.get("presets") if isinstance(data, dict) else None
    if not isinstance(presets, list):
        raise ApiError("后端未返回预设列表")
    base = None
    for p in presets:
        if isinstance(p, dict) and (p.get("metadata") or {}).get("name") == a.name:
            base = p
            break
    if base is None:
        names = [(p.get("metadata") or {}).get("name") for p in presets if isinstance(p, dict)]
        raise ApiError(f"未找到预设: {a.name}。可用: {names}")
    config = dict(base.get("data") or {})
    if a.overrides:
        config.update(load_json_arg(a.overrides))
    return submit_config(c, config, a.confirm_queue)


def _task_action(path_fmt):
    def run(c, a):
        return c.request("GET", path_fmt.format(task_id=a.task_id))

    return run


cmd_terminate = _task_action("/api/tasks/terminate/{task_id}")
cmd_resume = _task_action("/api/tasks/resume/{task_id}")
cmd_retry = _task_action("/api/tasks/retry/{task_id}")


def cmd_dataset_scan(c, a):
    return c.request("POST", "/api/dataset-editor/scan", body={"path": a.path})


def cmd_dataset_validate(c, a):
    return c.request("POST", "/api/dataset/validate", body={"path": a.path})


def cmd_tag(c, a):
    return c.request(
        "POST", "/api/interrogate",
        body={"path": a.path, "interrogator_model": a.model, "threshold": a.threshold},
    )


def cmd_tagger_status(c, a):
    return c.request("GET", "/api/tagger/status")


def cmd_browse(c, a):
    return c.request(
        "GET", "/api/path_browser/list",
        params={"path": a.path, "mode": a.mode, "name_filter": a.name_filter},
    )


def cmd_list_files(c, a):
    return c.request("GET", "/api/get_files", params={"pick_type": a.pick_type})


# ---------------------------------------------------------------- lifecycle


def _port_from_base_url(base_url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    return parsed.port or (443 if parsed.scheme == "https" else 80)


def _find_pid_by_port(port: int) -> int | None:
    """Listener pid bound to the port. POSIX via ss, Windows via netstat."""
    import subprocess

    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=10
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            parts = line.split()
            if (
                len(parts) >= 5
                and parts[0].startswith("TCP")
                and parts[1].endswith(f":{port}")
                and parts[3].upper() == "LISTENING"
            ):
                return int(parts[4])
        return None
    try:
        out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    import re

    for line in out.splitlines():
        if f":{port} " in line or f":{port}\t" in line:
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    return None


def _repo_root(a) -> Path:
    override = getattr(a, "repo", "") or os.environ.get("NT_REPO", "")
    if override:
        return Path(override)
    # default: <repo>/.opencode/skills/next-trainer/scripts/nt.py
    candidate = Path(__file__).resolve().parents[4]
    if (candidate / "run_gui.sh").is_file():
        return candidate
    raise ApiError("定位不到仓库根目录（run_gui.sh 不在默认推导位置），请用 --repo 或 NT_REPO 指定")


def cmd_health(c, a):
    """探活：API 有响应即视为活着。alive=false 时退出码为 1。"""
    try:
        data = c.request("GET", "/api/version")
        return {"alive": True, "version": data.get("version")}
    except ApiError as exc:
        return {"alive": False, "reason": str(exc)}


def cmd_start(c, a):
    """后台启动应用（run_gui.sh / run_gui.bat）。已活着则直接返回。"""
    alive = cmd_health(c, a)
    if alive["alive"]:
        return {"started": False, "already_running": True, "version": alive.get("version")}

    import subprocess

    root = _repo_root(a)
    script = root / ("run_gui.bat" if sys.platform == "win32" else "run_gui.sh")
    if not script.is_file():
        raise ApiError(f"启动脚本不存在: {script}")
    log_path = root / "logs" / "gui-agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab")

    if sys.platform == "win32":
        proc = subprocess.Popen(
            ["cmd", "/c", str(script)],
            cwd=str(root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    else:
        proc = subprocess.Popen(
            ["bash", str(script)],
            cwd=str(root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return {
        "started": True,
        "pid": proc.pid,
        "log": str(log_path),
        "hint": "首次启动可能装依赖要数分钟；用 health 轮询直到 alive=true",
    }


def cmd_stop(c, a):
    """停止应用：按 base-url 端口找监听进程，发 SIGTERM（等价 Ctrl+C，应用会自清理子进程）。

    ⚠️ 会中断正在进行的训练，调用前必须获得用户明确确认。
    """
    port = _port_from_base_url(c.base_url)
    pid = _find_pid_by_port(port)
    if pid is None:
        return {"stopped": False, "reason": f"端口 {port} 没有监听进程（应用未在运行？）"}

    import signal
    import time

    os.kill(pid, signal.SIGTERM)
    # Wait for the port to be released rather than the pid to vanish: the pid
    # may linger as an unreaped zombie, but the app closing its listener is
    # the semantically relevant "stopped" signal.
    deadline = time.monotonic() + a.wait
    while time.monotonic() < deadline:
        if _find_pid_by_port(port) is None:
            return {"stopped": True, "pid": pid}
        time.sleep(0.5)
    raise ApiError(f"SIGTERM 后 {a.wait}s 内端口 {port} 仍被进程 {pid} 占用；请人工检查后决定是否强杀")



# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nt.py", description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NT_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float, default=10.0)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, fn, **kwargs):
        p = sub.add_parser(name, **kwargs)
        p.set_defaults(fn=fn)
        return p

    add("version", cmd_version, help="后端版本号")
    add("schemas", cmd_schemas, help="全部训练页参数 schema 原文（很大，建议用 params/search）")
    p = add("params", cmd_params, help="训练页字段紧凑表：params <page> [--filter 关键字]；不带 page 列出全部页面")
    p.add_argument("page", nargs="?", default="")
    p.add_argument("--filter", default="", help="按字段名/描述/默认值过滤")
    p = add("search", cmd_search, help="聚合检索：跨全部 schema 参数 + SKILL.md + reference/ 文档")
    p.add_argument("keyword")
    p.add_argument("--max-matches", type=int, default=50)
    add("presets", cmd_presets, help="训练预设清单")
    add("saved-params", cmd_saved_params, help="WebUI 保存的参数")
    add("gpus", cmd_gpus, help="GPU 列表")
    add("gpu-status", cmd_gpu_status, help="各 GPU 实时显存占用")

    p = add("tasks", cmd_tasks, help="任务列表（紧凑版）")
    p.add_argument("--status", choices=["", "active", "finished", "all"], default="")
    p.add_argument("--limit", type=int, default=10)
    add("last-task", cmd_last_task, help="最近一次任务")

    for name, fn, helptext in (("status", cmd_status, "任务状态原文"),
                               ("config", cmd_config, "任务完整 autosave 配置（复现/对照用）"),
                               ("outputs", cmd_outputs, "产出的 safetensors 清单"),
                               ("previews", cmd_previews, "预览图文件名清单"),
                               ("terminate", cmd_terminate, "⚠️ 终止任务，先获得用户确认"),
                               ("resume", cmd_resume, "⚠️ 恢复任务，先获得用户确认"),
                               ("retry", cmd_retry, "⚠️ 重试任务，先获得用户确认")):
        p = add(name, fn, help=helptext)
        p.add_argument("task_id")

    p = add("metrics", cmd_metrics, help="loss 曲线数据点")
    p.add_argument("task_id")
    p.add_argument("--max-points", type=int, default=50)

    p = add("log-tail", cmd_log_tail, help="日志尾部（排错加大 --limit）")
    p.add_argument("task_id")
    p.add_argument("--limit", type=int, default=200)

    p = add("grep-log", cmd_grep_log, help="关键词搜日志")
    p.add_argument("task_id")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--max-matches", type=int, default=50)

    p = add("overview", cmd_overview, help="状态+最新loss+进度+日志尾+预览数 一次拿全")
    p.add_argument("task_id")
    p.add_argument("--log-lines", type=int, default=30)

    p = add("preview", cmd_preview, help="下载预览图到本地并打印路径（用 Read 看图）")
    p.add_argument("task_id")
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--out", default="")

    p = add("validate", cmd_validate, help="校验训练配置（不提交）")
    p.add_argument("page_train_type")
    p.add_argument("config", help="JSON 文件路径 / '-' 读 stdin / 内联 JSON")

    p = add("submit", cmd_submit, help="⚠️ 占用 GPU，先获得用户确认")
    p.add_argument("config", help="JSON 文件路径 / '-' 读 stdin / 内联 JSON")
    p.add_argument("--confirm-queue", action="store_true")

    p = add("submit-preset", cmd_submit_preset, help="⚠️ 占用 GPU，先获得用户确认")
    p.add_argument("name")
    p.add_argument("--overrides", default="", help="JSON 文件路径 / '-' / 内联 JSON")
    p.add_argument("--confirm-queue", action="store_true")

    p = add("dataset-scan", cmd_dataset_scan, help="数据集目录图片+caption 清单")
    p.add_argument("path")
    p = add("dataset-validate", cmd_dataset_validate, help="校验 kohya 格式数据集 toml")
    p.add_argument("path")

    p = add("tag", cmd_tag, help="WD14 打标")
    p.add_argument("path")
    p.add_argument("--model", default="wd14-convnextv2-v2")
    p.add_argument("--threshold", type=float, default=0.35)
    add("tagger-status", cmd_tagger_status, help="打标任务状态")

    p = add("browse", cmd_browse, help="服务器文件浏览")
    p.add_argument("path", nargs="?", default="")
    p.add_argument("--mode", choices=["folder", "file"], default="folder")
    p.add_argument("--name-filter", default="")

    p = add("list-files", cmd_list_files, help="列出可选择的文件（模型/数据集等）")
    p.add_argument("pick_type", help="model-file / model-saved-file / train-dir 等")

    add("health", cmd_health, help="探活：alive=false 时退出码为 1")
    p = add("start", cmd_start, help="后台启动应用（run_gui.sh/bat）")
    p.add_argument("--repo", default="", help="仓库根目录（默认从 skill 位置推导）")
    p = add("stop", cmd_stop, help="⚠️ 停止应用，会中断训练，先获得用户确认")
    p.add_argument("--wait", type=int, default=15, help="SIGTERM 后等待退出的秒数")
    p.add_argument("--repo", default="", help="保留参数，与 start 对齐")

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    client = Client(args.base_url, args.timeout)
    try:
        result = args.fn(client, args)
    except ApiError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("alive") is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
