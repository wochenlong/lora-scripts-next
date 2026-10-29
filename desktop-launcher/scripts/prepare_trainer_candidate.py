"""从已 push 的完整提交准备新 trainer_source、编译前端与成组身份更新。

默认只输出候选，不修改工作树。--apply 只提交显式身份文件白名单并先备份。
不重解 GUI 依赖、不重建安装树索引、不修改引擎锁、不签署生产清单。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import urllib.request
import zipfile


CATALOG_FILES = [
    "desktop-launcher/catalog/gui-candidate-source-v1.json",
    "desktop-launcher/catalog/gui-cp310-win-x64-v1.json",
    "desktop-launcher/catalog/releases.json",
    "desktop-launcher/catalog/gui-cp310-installed-files-v2.json",
    "desktop-launcher/catalog/gui-cp310-managed-venv-v1.json",
]
RUST_FILES = [
    "desktop-launcher/src-tauri/src/source_integrity.rs",
    "desktop-launcher/src-tauri/src/gui_registration_integrity.rs",
    "desktop-launcher/src-tauri/src/gui_registration.rs",
    "desktop-launcher/src-tauri/src/gui_rebuild.rs",
    "desktop-launcher/src-tauri/src/gui_binding_switch.rs",
    "desktop-launcher/src-tauri/src/instances.rs",
    "desktop-launcher/src-tauri/src/signed_catalog.rs",
]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def safe_relative(name):
    if not name or "\\" in name or ":" in name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("归档路径不安全：" + name)
    return PurePosixPath(name)


def inventory(path, prefix=""):
    files, seen, seen_folded = {}, set(), set()
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = entry.filename.rstrip("/")
            safe_relative(name)
            if name in seen or name.casefold() in seen_folded or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("归档包含重复、大小写别名或链接")
            seen.add(name)
            seen_folded.add(name.casefold())
            if entry.is_dir():
                continue
            if not entry.filename.startswith(prefix):
                raise ValueError("归档不属于固定提交前缀")
            local = entry.filename[len(prefix):]
            safe_relative(local)
            value = hashlib.sha256()
            with archive.open(entry) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(block)
            files[local] = {"bytes": entry.file_size, "sha256": value.hexdigest()}
    return files


def run(command, cwd, log, timeout=600, env=None):
    with log.open("wb") as output:
        completed = subprocess.run([str(item) for item in command], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise RuntimeError("命令失败，查看 " + str(log))


def prepare(args):
    if not re.fullmatch("[a-f0-9]{40}", args.commit):
        raise ValueError("--commit 必须是已 push 的完整小写40位提交")
    repo = args.repo.resolve()
    output = args.output.absolute()
    build = args.build_root.absolute()
    if output.exists() or build.exists() or not output.parent.is_dir() or not build.parent.is_dir():
        raise ValueError("output 和 build-root 必须是已有父目录下的新目录")
    # Node/npm及源码均在父任务提供的固定构建环境执行，保持工作树零 npm 改动。
    node = args.node.resolve()
    npm_cli = args.npm_cli.resolve()
    version = subprocess.check_output([str(node), "--version"], text=True).strip()
    if not re.fullmatch(r"v22\.[0-9]+\.[0-9]+", version):
        raise ValueError("trainer frontend 要求 Node 22，实际为 " + version)
    output.mkdir()
    build.mkdir()
    before = {name: (repo / name).read_bytes() for name in CATALOG_FILES + RUST_FILES}
    recipe = json.loads(before[CATALOG_FILES[1]])
    catalog = json.loads(before[CATALOG_FILES[2]])
    old_source = json.loads(before[CATALOG_FILES[0]])
    old_recipe_sha = hashlib.sha256(before[CATALOG_FILES[1]]).hexdigest()
    old_index_sha = hashlib.sha256(before[CATALOG_FILES[3]]).hexdigest()
    old_managed_sha = hashlib.sha256(before[CATALOG_FILES[4]]).hexdigest()
    url = "https://codeload.github.com/wochenlong/lora-scripts-next/zip/" + args.commit
    archive = output / "trainer-source.zip"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": args.proxy, "http": args.proxy}))
    received = 0
    started = time.monotonic()
    with opener.open(urllib.request.Request(url, headers={"Accept-Encoding": "identity"}), timeout=45) as response, archive.open("xb") as target:
        if response.status != 200:
            raise RuntimeError("固定提交归档不可获取，请先完成 push")
        while chunk := response.read(1024 * 1024):
            received += len(chunk)
            if received > 200 * 1024 * 1024 or time.monotonic() - started > 300:
                raise RuntimeError("源码下载超出200MiB/300秒固定限额")
            target.write(chunk)
    prefix = "lora-scripts-next-" + args.commit + "/"
    original = inventory(archive, prefix)
    with zipfile.ZipFile(archive) as source:
        requirements = source.read(prefix + "requirements.txt")
        version_text = source.read(prefix + "VERSION").decode("utf-8-sig").strip()
        if hashlib.sha256(requirements).hexdigest() != recipe["requirements"]["input_sha256"] or len(requirements) != recipe["requirements"]["input_bytes"]:
            raise ValueError("GUI requirements 已改变；必须单独重解依赖和重新审查可信索引，禁止本脚本复用旧闭包")
        for entry in source.infolist():
            if entry.is_dir():
                continue
            local = entry.filename[len(prefix):]
            destination = build / local
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as input, destination.open("xb") as target:
                shutil.copyfileobj(input, target, 1024 * 1024)
    frontend_root = build / "frontend"
    build_env = dict(os.environ)
    build_env["PATH"] = str(node.parent) + os.pathsep + build_env.get("PATH", "")
    run([node, npm_cli, "ci", "--no-audit", "--no-fund"], frontend_root, output / "npm-ci.log", env=build_env)
    run([node, npm_cli, "run", "build"], frontend_root, output / "npm-build.log", env=build_env)
    dist = frontend_root / "dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("新编译前端缺少 index.html")
    frontend = output / "frontend.zip"
    with zipfile.ZipFile(frontend, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(dist.rglob("*")):
            if path.is_symlink():
                raise ValueError("前端产物不得包含链接")
            if not path.is_file():
                continue
            relative = path.relative_to(dist).as_posix()
            safe_relative(relative)
            item = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(item, path.read_bytes())
    frontend_files = inventory(frontend)
    source_files = {name: item for name, item in original.items() if not name.startswith("frontend/dist/")}
    source_files.update({"frontend/dist/" + name: item for name, item in frontend_files.items()})
    manifest = {"schema_version": 1, "source_commit": args.commit, "source_archive_sha256": digest(archive), "source_archive_bytes": archive.stat().st_size,
                "frontend_sha256": digest(frontend), "frontend_bytes": frontend.stat().st_size, "expected_file_count": len(source_files),
                "expected_file_bytes": sum(item["bytes"] for item in source_files.values()), "files": [{"path": name, **item} for name, item in sorted(source_files.items())]}
    recipe["source_commit"] = args.commit
    recipe["frontend"].update(sha256=digest(frontend), bytes=frontend.stat().st_size, unpacked_bytes=sum(item["bytes"] for item in frontend_files.values()), files=len(frontend_files))
    recipe["budget"]["asset_bytes"] = recipe["budget"]["wheel_bytes"] + recipe["python"]["archive"]["bytes"] + recipe["tool_uv"]["bytes"] + recipe["frontend"]["bytes"]
    recipe_bytes = encoded(recipe)
    recipe_sha = hashlib.sha256(recipe_bytes).hexdigest()
    source_release = dict(catalog["releases"][0])
    source_release.update(id="dev-" + args.commit, channel="dev", commit=args.commit, version=version_text)
    source_release["archive"] = {"url": url, "sha256": digest(archive), "bytes": archive.stat().st_size, "unpacked_bytes": sum(item["bytes"] for item in original.values())}
    catalog["releases"] = [source_release, *[item for item in catalog["releases"] if item["id"] != source_release["id"]]]
    proposals = {CATALOG_FILES[0]: encoded(manifest), CATALOG_FILES[1]: recipe_bytes, CATALOG_FILES[2]: encoded(catalog)}
    # 文件闭包及模板完全不变，仅因源码/前端新身份而更新其父配方摘要。
    for path in CATALOG_FILES[3:]:
        raw = before[path]
        if raw.count(old_recipe_sha.encode()) != 1:
            raise ValueError("可信索引父配方摘要不是唯一字段：" + path)
        proposals[path] = raw.replace(old_recipe_sha.encode(), recipe_sha.encode())
    index_sha = hashlib.sha256(proposals[CATALOG_FILES[3]]).hexdigest()
    managed_sha = hashlib.sha256(proposals[CATALOG_FILES[4]]).hexdigest()
    for path in RUST_FILES:
        text = before[path].decode("utf-8")
        for old, new in ((old_recipe_sha, recipe_sha), (old_index_sha, index_sha), (old_managed_sha, managed_sha)):
            text = text.replace(old, new)
        if path.endswith("/source_integrity.rs"):
            text = text.replace(old_source["source_commit"], args.commit).replace(old_source["source_archive_sha256"], digest(archive)).replace(old_source["frontend_sha256"], digest(frontend))
            for field in ("source_archive_bytes", "frontend_bytes", "expected_file_count", "expected_file_bytes"):
                old, new = old_source[field], manifest[field]
                # Rust 数字允许下划线；逐字面量替换，禁止模糊子串替换。
                text = re.sub(r"(?<![a-zA-Z0-9_])" + "_?".join(str(old)) + r"(?![a-zA-Z0-9_])", str(new), text)
        proposals[path] = text.encode("utf-8")
    staged = output / "identity-proposals"
    for name, value in proposals.items():
        target = staged / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    receipt = {"schema_version": 1, "status": "prepared", "commit": args.commit, "source": {"url": url, "path": str(archive), "bytes": archive.stat().st_size, "sha256": digest(archive)},
               "frontend": {"path": str(frontend), **recipe["frontend"]}, "node": version, "build_root": str(build), "recipe_sha256": recipe_sha,
               "index_sha256": index_sha, "managed_venv_sha256": managed_sha, "before": {name: hashlib.sha256(value).hexdigest() for name, value in before.items()},
               "proposals": {name: hashlib.sha256(value).hexdigest() for name, value in proposals.items()}, "gui_dependency_closure": "unchanged verified requirements; fixed wheels/python/uv/index payload retained",
               "required_followup": ["Regenerate public signed-fixtures-v1.json for the new recipe/release using its existing public test key, never production credentials", "Refresh registration-index provenance/generator parent recipe SHA after reviewing the proposed identities", "Build same final EXE with NEXT_TRAINER_BUNDLED_FRONTEND pointing to this frontend.zip", "Run required final native smoke checks; preparation is not runtime acceptance"]}
    if args.apply:
        backup = output / "identity-backup"
        for name in proposals:
            if (repo / name).read_bytes() != before[name]:
                raise RuntimeError("身份文件在准备期间发生变化，拒绝覆盖：" + name)
        for name, value in proposals.items():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(before[name])
            (repo / name).write_bytes(value)
        receipt["status"] = "applied_identity_allowlist"
    (output / "candidate-receipt.json").write_bytes(encoded(receipt))
    print(json.dumps(receipt, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="准备已发布完整提交的 trainer_source 候选与身份白名单")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--npm-cli", type=Path, required=True)
    parser.add_argument("--proxy", default="http://127.0.0.1:11809")
    parser.add_argument("--apply", action="store_true", help="备份后仅应用固定身份文件白名单；其余产物保留output")
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
