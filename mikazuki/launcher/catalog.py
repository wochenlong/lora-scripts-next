"""发布期资产锁生成工具；运行期 worker 不联网、不解析浮动依赖。

resolve 只生成元数据锁；finalize 要求解释器、源码和预制 wheel 的完整来源，
成功才产生可交付的 executable engine lock。源码包构建在发布流水线单独完成。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.parse
import urllib.request
import zipfile

from .recipes import ENGINES, recipe
from .runtime import ControlError, atomic_json, digest_json, relative, sha_file


def asset(path: Path, url: str) -> dict:
    if not url.startswith("https://"):
        raise ControlError("publisher_asset_url", "发布资产必须有 HTTPS 来源")
    return {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path), "url": url}


def archive_manifest(path: Path, prefix: str = "") -> dict:
    result = {}
    seen = set()
    if prefix and not prefix.endswith("/"):
        raise ControlError("publisher_prefix", "归档前缀必须以斜线结束")
    with zipfile.ZipFile(path) if zipfile.is_zipfile(path) else tarfile.open(path, "r:*") as stream:
        zipped = isinstance(stream, zipfile.ZipFile)
        for entry in stream.infolist() if zipped else stream:
            name = entry.filename if zipped else entry.name
            relative(name.rstrip("/"))
            directory = entry.is_dir() if zipped else entry.isdir()
            special = ((entry.external_attr >> 16) & 0o170000) == 0o120000 if zipped else not (entry.isfile() or directory)
            if special or name in seen:
                raise ControlError("publisher_archive", "发布归档不得有链接、特殊或重复成员")
            seen.add(name)
            if directory or not name.startswith(prefix):
                continue
            local = relative(name[len(prefix):]).as_posix()
            data = stream.read(entry) if zipped else stream.extractfile(entry).read()
            result[local] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if not result:
        raise ControlError("publisher_empty_archive", "归档中没有前缀匹配文件")
    return result


def wheel_rank(filename: str, python_abi: str) -> int:
    try:
        interpreter, abi, platform = filename.removesuffix(".whl").rsplit("-", 3)[1:]
    except ValueError:
        return -1
    if platform not in {"any", "win_amd64"}:
        return -1
    target = int(python_abi[2:])
    tags = interpreter.split(".")
    if python_abi in tags and abi in {python_abi, "abi3", "none"}:
        return 100 + (platform == "win_amd64")
    if abi == "abi3" and any(t.startswith("cp") and t[2:].isdigit() and int(t[2:]) <= target for t in tags):
        return 80
    if abi == "none" and ("py3" in tags or "py" + python_abi[2:] in tags):
        return 50
    return -1


def wheels_from_pylock(path: Path, python_abi: str, overrides: list | None = None) -> tuple[list, list]:
    import tomllib
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("lock-version") != "1.0":
        raise ControlError("publisher_pylock", "仅支持 PEP 751 pylock 1.0")
    replacement = {item["name"]: item for item in overrides or []}
    wheels, unresolved = [], []
    for package in data.get("packages", []):
        if package["name"] in replacement:
            wheels.append(replacement.pop(package["name"]))
            continue
        choices = []
        for wheel in package.get("wheels", []):
            url = wheel.get("url", "")
            filename = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
            rank = wheel_rank(filename, python_abi)
            digest = wheel.get("hashes", {}).get("sha256", "")
            if rank >= 0 and url.startswith("https://") and re.fullmatch("[a-f0-9]{64}", digest) and isinstance(wheel.get("size"), int):
                choices.append((rank, filename, {"name": package["name"], "version": package["version"], "filename": filename, "url": url, "bytes": wheel["size"], "sha256": digest}))
        if choices:
            wheels.append(sorted(choices, key=lambda item: (item[0], item[1]))[-1][2])
        else:
            compatible = [item for item in package.get("wheels", []) if wheel_rank(urllib.parse.unquote(Path(urllib.parse.urlparse(item.get("url", "")).path).name), python_abi) >= 0]
            unresolved.append({"name": package["name"], "version": package.get("version"), "reason": "wheel_metadata_incomplete" if compatible else "no_locked_windows_wheel", "sdist": package.get("sdist"), "build_policy": "publisher completes size/hash metadata or builds verified sdist with pinned backend; publish wheel and pass override descriptor"})
    wheels.extend(replacement.values())
    return sorted(wheels, key=lambda value: value["name"]), unresolved


def complete_wheel_metadata(pylock: Path, python_abi: str, overrides: list | None = None) -> list:
    """发布期只取 JSON/HEAD/单字节 Range，不为元数据下载 Torch wheel。"""
    import tomllib
    wheels, gaps = wheels_from_pylock(pylock, python_abi, overrides)
    packages = {item["name"]: item for item in tomllib.loads(pylock.read_text(encoding="utf-8"))["packages"]}
    opener = urllib.request.build_opener()
    for gap in gaps:
        if gap["reason"] != "wheel_metadata_incomplete":
            raise ControlError("publisher_unresolved_wheels", json.dumps(gap, ensure_ascii=False))
        package = packages[gap["name"]]
        candidates = [item for item in package["wheels"] if wheel_rank(urllib.parse.unquote(Path(urllib.parse.urlparse(item.get("url", "")).path).name), python_abi) >= 0]
        selected = max(candidates, key=lambda item: wheel_rank(urllib.parse.unquote(Path(urllib.parse.urlparse(item["url"]).path).name), python_abi))
        url = selected["url"]
        if not url.startswith("https://"):
            raise ControlError("publisher_asset_url", "元数据补全只接受 HTTPS wheel")
        filename = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
        digest = selected.get("hashes", {}).get("sha256")
        size = selected.get("size")
        if not digest:
            metadata_url = "https://pypi.org/pypi/" + package["name"] + "/" + package["version"] + "/json"
            with opener.open(metadata_url, timeout=40) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
            if len(payload) > 8 * 1024 * 1024:
                raise ControlError("publisher_metadata_limit", "包 JSON 元数据超过限额")
            artifact = next((item for item in json.loads(payload)["urls"] if item["filename"] == filename), None)
            if not artifact:
                raise ControlError("publisher_asset_unknown", "PyPI 元数据没有对应 wheel")
            url, digest, size = artifact["url"], artifact["digests"]["sha256"], artifact["size"]
        if not size:
            with opener.open(urllib.request.Request(url, method="HEAD", headers={"Accept-Encoding": "identity"}), timeout=40) as response:
                size = int(response.headers.get("Content-Length", "0"))
            if not size:
                with opener.open(urllib.request.Request(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}), timeout=40) as response:
                    if response.status != 206:
                        raise ControlError("publisher_range_unsupported", "远端不支持元数据 Range；拒绝下载完整 wheel")
                    size = int(response.headers["Content-Range"].split("/")[-1])
                    response.read(1)
        if not re.fullmatch("[a-f0-9]{64}", digest) or not isinstance(size, int) or size <= 0:
            raise ControlError("publisher_metadata_invalid", "wheel 元数据仍不完整")
        wheels.append({"name": package["name"], "version": package["version"], "filename": filename, "url": url, "bytes": size, "sha256": digest})
    return sorted(wheels, key=lambda value: value["name"])


def resolve(engine_id: str, destination: Path, uv: Path, extra_requirements: list[Path], find_links: list[str], omit: list[str]) -> dict:
    fixed = recipe(engine_id)
    destination.mkdir(parents=True, exist_ok=True)
    requirements = [item for item in fixed["requirements"] if not any(re.split(r"[<>=!~ @\[]", item, 1)[0].lower() == name.lower() for name in omit)]
    source = destination / f"{engine_id}.requirements.in"
    source.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    output = destination / f"pylock.{engine_id}.toml"
    command = [str(uv), "pip", "compile", str(source), *[str(path) for path in extra_requirements], "--python-platform", "x86_64-pc-windows-msvc", "--python-version", fixed["python"], "--no-build", "--index", "https://download.pytorch.org/whl/" + fixed["cuda"], "--index-strategy", "unsafe-best-match", "--format", "pylock.toml", "--output-file", str(output)]
    for location in find_links:
        command.extend(["--find-links", location])
    atomic_json(destination / f"{engine_id}.recipe.json", fixed)
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    (destination / f"{engine_id}.resolve.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    result = {"schema_version": 1, "engine_id": engine_id, "recipe_sha256": fixed["recipe_sha256"], "command": command, "returncode": completed.returncode, "status": "metadata_resolved" if completed.returncode == 0 else "metadata_resolution_failed", "omitted_direct_packages": omit, "pylock": str(output), "runtime_installation": "not_run", "torch_payload": "not_installed"}
    if completed.returncode == 0:
        wheels, unresolved = wheels_from_pylock(output, fixed["python_abi"])
        result.update(wheels=wheels, unresolved=unresolved)
    else:
        result["reason"] = completed.stderr[-5000:]
    atomic_json(destination / f"{engine_id}.resolution.json", result)
    return result


def finalize(engine_id: str, pylock: Path, publisher: dict, destination: Path) -> dict:
    fixed = recipe(engine_id)
    wheels = complete_wheel_metadata(pylock, fixed["python_abi"], publisher.get("wheel_overrides"))
    python = dict(publisher["python"])
    python_path = Path(python.pop("archive_path"))
    python["archive"] = asset(python_path, python.pop("archive_url"))
    python["files"] = archive_manifest(python_path, python.get("strip_prefix", ""))
    if python["executable_relative"] not in python["files"]:
        raise ControlError("publisher_python_entry", "解释器入口不在固定文件清单")
    python.update(python["files"][python["executable_relative"]])
    source = dict(publisher["source"])
    if source.get("upstream_commit") != fixed["upstream_commit"]:
        raise ControlError("publisher_source_commit", "源码必须符合随包固定提交")
    if source.get("archive_path"):
        source_path = Path(source.pop("archive_path"))
        source["archive"] = asset(source_path, source.pop("archive_url"))
        source["files"] = archive_manifest(source_path, source.get("strip_prefix", ""))
    else:
        root = Path(source.pop("directory"))
        source["files"] = {p.relative_to(root).as_posix(): {"bytes": p.stat().st_size, "sha256": sha_file(p)} for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}
    if source.get("entry", fixed["entry"]) not in source["files"]:
        raise ControlError("publisher_source_entry", "引擎入口不在固定源码清单")
    source.setdefault("entry", fixed["entry"])
    uv = publisher["uv"]
    if uv.get("archive_path"):
        uv_fixed = {"filename": "uv.exe", "bytes": Path(uv["path"]).stat().st_size, "sha256": sha_file(Path(uv["path"])), "archive": asset(Path(uv["archive_path"]), uv["archive_url"]), "archive_member": uv["archive_member"]}
        raw = archive_manifest(Path(uv["archive_path"]))
        if raw.get(uv["archive_member"]) != {"bytes": uv_fixed["bytes"], "sha256": uv_fixed["sha256"]}:
            raise ControlError("publisher_uv_entry", "uv.exe 不符合固定官方 ZIP 的文件")
    else:
        uv_fixed = asset(Path(uv["path"]), uv["url"])
    lock = {"schema_version": 1, "engine_id": engine_id, "recipe_sha256": fixed["recipe_sha256"], "platform": "windows-x86_64", "python": python, "source": source, "uv": uv_fixed, "wheels": wheels, "provenance": {"pylock_sha256": sha_file(pylock), "publisher_descriptor_sha256": digest_json(publisher)}, "validation": {"installation": "not_run", "gpu": "skip + CR-004", "training": "skip + CR-004"}}
    atomic_json(destination, lock)
    return {"status": "executable_lock_created", "path": str(destination), "sha256": sha_file(destination), "wheels": len(wheels), "runtime_installation": "not_run"}


def main():
    parser = argparse.ArgumentParser(description="生成随包引擎配方的 Windows 平台依赖锁")
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("resolve")
    command.add_argument("--engine", choices=ENGINES, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--uv", type=Path, required=True)
    command.add_argument("--requirements", type=Path, action="append", default=[])
    command.add_argument("--find-links", action="append", default=[])
    command.add_argument("--omit", action="append", default=[])
    command = sub.add_parser("finalize")
    command.add_argument("--engine", choices=ENGINES, required=True)
    command.add_argument("--pylock", type=Path, required=True)
    command.add_argument("--publisher", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "resolve":
        result = resolve(args.engine, args.output, args.uv, args.requirements, args.find_links, args.omit)
    else:
        result = finalize(args.engine, args.pylock, json.loads(args.publisher.read_text(encoding="utf-8")), args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] != "metadata_resolution_failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
