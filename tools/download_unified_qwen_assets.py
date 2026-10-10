"""U1：在独立新目录下载已锁定的两个 Qwen 图文候选及 CPU runtime。

默认拒绝已有目录；--resume 仅续接本工具建立且输入锁未变化的目录。
下载使用显式代理、.part/Range、有界重试，全部 size/SHA 校验后才生成
locked-candidates.json。不读取用户配置、凭据或已有模型，不启动模型。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_ROOT = Path("E:/OpenSourceTeamWork/workspace/tools/nl-caption-dev-analysis-20261010")
DEFAULT_RUNTIME_LOCK = PROJECT_ROOT / "docs/evidence/natural-language-captioning/phase-4-real-evaluation/phase5-frozen-inputs.json"
OWNER = "dataset-nl-unified-qwen-assets-v1"
MIN_FREE_BYTES = 30 * 1024**3
RUNTIME_SHA = "4ac11772e7f9a313346ff2f4212b0608dd181130df81b9070cef377102faba8f"
EXECUTABLE_SHA = "32d43779061d318ab36d0cf8156f314f81ac7e5b805298b7fe9facf3cf0cc82d"
RUNTIME_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b11327/llama-b11327-bin-win-cpu-x64.zip"
CANDIDATES = (
    ("qwen3-vl-2b", "Qwen/Qwen3-VL-2B-Instruct-GGUF", "52d6c8ffea26cc873ac5ad116f8631268d7eb503",
     "Qwen3VL-2B-Instruct-Q4_K_M.gguf", "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"),
    ("qwen3.5-2b", "unsloth/Qwen3.5-2B-GGUF", "f6d5376be1edb4d416d56da11e5397a961aca8ae",
     "Qwen3.5-2B-Q4_K_M.gguf", "mmproj-F16.gguf"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def safe_path(path, root=None):
    path = Path(path).absolute()
    if root is not None:
        path.relative_to(root.absolute())
        path.resolve().relative_to(root.resolve())
    for current in (path, *path.parents):
        if current.exists() or current.is_symlink():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            require(not current.is_symlink() and not attributes & 0x400,
                    "asset paths cannot contain symbolic links or junctions")
    return path


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_plan(metadata_root, runtime_lock):
    """Read local lock inputs only; no model or runtime paths are reused."""
    plan = {"schema_version": 1, "owner": OWNER, "candidates": [], "input_sources": []}
    for identifier, repository, revision, model, projector in CANDIDATES:
        path = metadata_root / (repository.replace("/", "--") + "--metadata.json")
        metadata = read_json(path)
        require(metadata.get("id") == repository and metadata.get("revision") == revision,
                "candidate metadata repository/revision differs from the approved candidate")
        files = []
        for filename in (model, projector):
            matches = [item for item in metadata.get("assets", []) if item.get("name") == filename]
            require(len(matches) == 1, "candidate metadata must contain exactly one locked file")
            item = matches[0]
            size = item.get("size")
            sha = item.get("sha256") or item.get("lfs", {}).get("sha256")
            require(type(size) is int and size > 0 and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha),
                    "candidate file requires a positive size and SHA256")
            if item.get("lfs", {}).get("size") is not None:
                require(item["lfs"]["size"] == size, "metadata LFS and asset sizes differ")
            files.append({"filename": filename, "size_bytes": size, "sha256": sha,
                          "url": f"https://huggingface.co/{repository}/resolve/{revision}/{quote(filename)}"})
        plan["candidates"].append({"id": identifier, "repository": repository, "revision": revision,
                                   "license": "Apache-2.0", "quantization": "Q4_K_M", "files": files})
        plan["input_sources"].append({"path": str(path.absolute()), "sha256": digest(path)})
    raw = read_json(runtime_lock)
    runtime = raw.get("runtime", raw)
    require(runtime.get("version") == "b11327" and runtime.get("url") == RUNTIME_URL
            and runtime.get("size_bytes") == 19275534 and runtime.get("archive_sha256") == RUNTIME_SHA
            and runtime.get("executable_sha256") == EXECUTABLE_SHA,
            "runtime input differs from the approved b11327 CPU lock")
    plan["runtime"] = {"version": "b11327", "url": RUNTIME_URL, "filename": "llama-b11327-bin-win-cpu-x64.zip",
                       "size_bytes": 19275534, "sha256": RUNTIME_SHA, "executable_sha256": EXECUTABLE_SHA}
    plan["input_sources"].append({"path": str(runtime_lock.absolute()), "sha256": digest(runtime_lock)})
    return plan


def valid_file(path, asset):
    return path.is_file() and path.stat().st_size == asset["size_bytes"] and digest(path) == asset["sha256"]


def download(session, asset, target, root, attempts):
    safe_path(target, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(valid_file(target, asset), "completed asset differs from its input lock; original preserved")
        return {"relative_path": target.relative_to(root).as_posix(), **asset, "verified_existing_owned_file": True}
    partial = target.with_name(target.name + ".part")
    safe_path(partial, root)
    failures = []
    for attempt in range(1, attempts + 1):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset >= asset["size_bytes"]:
                if valid_file(partial, asset):
                    os.replace(partial, target)
                    return {"relative_path": target.relative_to(root).as_posix(), **asset,
                            "attempts": attempt, "range_resume": True, "failures": failures}
                partial.rename(partial.with_name(partial.name + ".invalid-" + uuid.uuid4().hex))
                offset = 0
            headers = {"User-Agent": OWNER, "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with session.get(asset["url"], headers=headers, stream=True, timeout=(30, 60)) as response:
                require(response.status_code in {200, 206}, f"download HTTP status {response.status_code}")
                require(response.headers.get("Content-Encoding", "identity").lower() in {"identity", ""},
                        "download must not use transport compression")
                if response.status_code == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    require(match is not None and int(match[1]) == offset and int(match[3]) == asset["size_bytes"]
                            and offset <= int(match[2]) < asset["size_bytes"], "download range differs from its input lock")
                    mode = "ab" if offset else "wb"
                else:
                    # Servers may ignore Range; restart this part, never append.
                    offset, mode = 0, "wb"
                written = offset
                with partial.open(mode) as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        require(written + len(chunk) <= asset["size_bytes"], "download exceeds its locked size")
                        stream.write(chunk)
                        written += len(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
            require(written == asset["size_bytes"], "download is incomplete")
            require(digest(partial) == asset["sha256"], "download SHA256 differs from its input lock")
            os.replace(partial, target)
            return {"relative_path": target.relative_to(root).as_posix(), **asset,
                    "downloaded_at": now(), "attempts": attempt, "range_resume": bool(offset), "failures": failures}
        except (requests.RequestException, OSError, ValueError) as error:
            # Provider exception strings can contain signed URLs. Record only
            # safe local validation text or the exception class, never headers.
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            failures.append({"attempt": attempt, "reason": reason})
            write_json(target.with_name(target.name + ".download-failures.json"), {"asset": asset, "failures": failures})
            print(json.dumps({"asset": target.name, "attempt": attempt, "failed": reason}), flush=True)
            if attempt == attempts:
                raise RuntimeError(f"download failed after {attempts} attempts: {target.name}") from None
            time.sleep(min(attempt * 2, 6))
    raise RuntimeError("unreachable download state")


def extract_runtime(archive, root, runtime):
    destination = root / "runtime"
    safe_path(destination, root)
    if destination.exists():
        executables = list(destination.rglob("llama-server.exe"))
        require(len(executables) == 1 and digest(executables[0]) == runtime["executable_sha256"],
                "existing owned runtime differs from its input lock")
        return executables[0]
    staging = root / ("runtime-extract-" + uuid.uuid4().hex)
    staging.mkdir()
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        require(len(entries) <= 5000 and sum(item.file_size for item in entries) <= 2 * 1024**3,
                "runtime archive exceeds extraction bounds")
        names = set()
        for entry in entries:
            normalized = entry.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            require(not path.is_absolute() and not any(part in {"..", ""} or ":" in part for part in path.parts),
                    "runtime archive contains a traversal path")
            require(all(not part.endswith((".", " ")) and part.split(".")[0].upper() not in {
                "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
            } for part in path.parts), "runtime archive contains a nonportable Windows path")
            require(not stat.S_ISLNK(entry.external_attr >> 16), "runtime archive contains a symbolic link")
            portable = normalized.rstrip("/").casefold()
            require(portable not in names, "runtime archive contains duplicate paths")
            names.add(portable)
            safe_path(staging.joinpath(*path.parts), root)
        for entry in entries:
            target = staging.joinpath(*PurePosixPath(entry.filename.replace("\\", "/")).parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as source_file, target.open("xb") as target_file:
                    shutil.copyfileobj(source_file, target_file, 1024 * 1024)
        executables = list(staging.rglob("llama-server.exe"))
        require(len(executables) == 1 and digest(executables[0]) == runtime["executable_sha256"],
                "runtime executable differs from its input lock")
    relative = executables[0].relative_to(staging)
    staging.rename(destination)
    return destination / relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="全新独立资产根目录")
    parser.add_argument("--metadata-root", type=Path, default=DEFAULT_METADATA_ROOT)
    parser.add_argument("--runtime-lock", type=Path, default=DEFAULT_RUNTIME_LOCK)
    parser.add_argument("--proxy", default="http://127.0.0.1:11809")
    parser.add_argument("--attempts", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--resume", action="store_true", help="仅续接本工具拥有且输入锁不变的失败目录")
    parser.add_argument("--candidate", choices=[item[0] for item in CANDIDATES], help="只下载指定候选；选型锁进ownership，不复用不同选型根")
    args = parser.parse_args()
    require(urlparse(args.proxy).scheme == "http" and urlparse(args.proxy).hostname in {"127.0.0.1", "localhost"}
            and urlparse(args.proxy).port is not None, "proxy must be an explicit loopback HTTP proxy")
    plan = load_plan(args.metadata_root, args.runtime_lock)
    if args.candidate:
        plan["candidates"] = [item for item in plan["candidates"] if item["id"] == args.candidate]
    root = safe_path(args.root)
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    require(shutil.disk_usage(ancestor).free >= MIN_FREE_BYTES, "at least 30 GiB of free disk space is required")
    owner_path = root / ".unified-qwen-download-owner.json"
    if root.exists():
        require(args.resume and root.is_dir() and owner_path.is_file(), "asset root already exists; new roots are required")
        owner = read_json(safe_path(owner_path, root))
        require(owner.get("owner") == OWNER and owner.get("lock_sha256") == fingerprint(plan),
                "resume root is not owned by this tool or its input lock changed")
    else:
        require(not args.resume, "resume requires an existing owned root")
        root.mkdir(parents=True, exist_ok=False)
        write_json(owner_path, {"owner": OWNER, "lock_sha256": fingerprint(plan), "created_at": now()})
        write_json(root / "locked-download-inputs.json", plan)
    # An observation timeout never authorizes restarting the same live writer.
    # A leftover lock after a process crash is preserved for explicit review.
    process_lock = safe_path(root / ".download-running.lock", root)
    try:
        descriptor = os.open(process_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("download root has a running/stale lock; inspect its PID before retrying") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock_stream:
        lock_stream.write(str(os.getpid()) + "\n")
        lock_stream.flush()
        os.fsync(lock_stream.fileno())
    report = {"owner": OWNER, "started_at": now(), "passed": False, "receipts": []}
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": args.proxy, "https": args.proxy}
    try:
        runtime = plan["runtime"]
        archive = root / "archives" / runtime["filename"]
        report["receipts"].append(download(session, runtime, archive, root, args.attempts))
        executable = extract_runtime(archive, root, runtime)
        result = {"schema_version": 1, "kind": "locked-qwen-probe-candidates", "runtime": {
            "executable_path": str(executable), "executable_sha256": runtime["executable_sha256"],
            "version": runtime["version"], "archive_path": str(archive), "archive_sha256": runtime["sha256"],
            "source": runtime["url"], "url": runtime["url"], "size_bytes": runtime["size_bytes"]}, "candidates": []}
        for candidate in plan["candidates"]:
            paths = []
            for asset in candidate["files"]:
                path = root / "candidates" / candidate["id"] / asset["filename"]
                report["receipts"].append(download(session, asset, path, root, args.attempts))
                paths.append(path)
            model, projector = candidate["files"]
            result["candidates"].append({"id": candidate["id"], "model_path": str(paths[0]), "mmproj_path": str(paths[1]),
                "model_sha256": model["sha256"], "mmproj_sha256": projector["sha256"],
                "revision": candidate["revision"], "repository": candidate["repository"], "license": candidate["license"],
                "quantization": candidate["quantization"],
                "model_size_bytes": model["size_bytes"], "mmproj_size_bytes": projector["size_bytes"],
                "sizes": {"model": model["size_bytes"], "mmproj": projector["size_bytes"]},
                "urls": {"model": model["url"], "mmproj": projector["url"]}, "files": candidate["files"]})
            write_json(root / "download-report.json", report)
        write_json(root / "locked-candidates.json", result)
        report.update(passed=True, finished_at=now(), output_sha256=digest(root / "locked-candidates.json"))
        write_json(root / "download-report.json", report)
        print(json.dumps({"passed": True, "manifest": str(root / "locked-candidates.json")}), flush=True)
    except BaseException as error:
        report.update(finished_at=now(), error_type=type(error).__name__)
        write_json(root / "download-report.json", report)
        raise
    finally:
        session.close()
        process_lock.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, requests.RequestException, zipfile.BadZipFile) as error:
        print(json.dumps({"passed": False, "error": str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__}), file=sys.stderr)
        sys.exit(1)
