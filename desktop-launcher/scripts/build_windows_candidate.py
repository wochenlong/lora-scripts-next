"""离线构建同一 Windows EXE 的 NSIS/便携开发候选；不签生产身份、不发布。

依赖预先安装的 Rust/Node、npm/Cargo 锁定缓存和官方 Tauri NSIS 工具缓存。
前端 ZIP 必须与编译配方吻合。输出必须是仓库之外的新目录；失败现场保留。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile


LAUNCHER = Path(__file__).resolve().parents[1]
REPO = LAUNCHER.parent


def digest(path: Path) -> dict:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return {"bytes": path.stat().st_size, "sha256": result.hexdigest()}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(command: list[str], cwd: Path = REPO) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True, encoding="utf-8").strip()


def cache_inventory(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): digest(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def source_inventory() -> dict:
    paths = []
    for name in ("src", "catalog", "scripts", "LICENSES", "src-tauri", "shell-updater"):
        for path in (LAUNCHER / name).rglob("*"):
            parts = path.relative_to(LAUNCHER).parts
            if path.is_file() and not any(p in ("target", "gen", "__pycache__") for p in parts):
                paths.append(path)
    paths.extend(LAUNCHER / name for name in ("package.json", "package-lock.json", "README.md"))
    paths.extend(REPO / name for name in ("LICENSE", "NOTICE.md", "docs/launcher/windows-delivery.md"))
    # worker 的真实编译输入位于训练器源码树，必须和主壳一样纳入冻结证明。
    paths.extend(REPO / name for name in worker_paths())
    return {path.relative_to(REPO).as_posix(): digest(path) for path in sorted(set(paths))}


def worker_paths() -> list[str]:
    source = (LAUNCHER / "src-tauri/src/engine_bridge.rs").read_text(encoding="utf-8")
    return re.findall(r'worker_file!\("([^"]+)"\)', source)


def verify_windows_tools(cache: Path) -> dict:
    """与当前CLI官方源码同一身份；存在旧文件不等于能离线使用。"""
    lock_path = LAUNCHER / "scripts/windows-tools-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["schema_version"] != 1 or lock["platform"] != "windows-x86_64":
        raise ValueError("未知Windows构建工具锁")
    package = json.loads((LAUNCHER / "node_modules/@tauri-apps/cli/package.json").read_text(encoding="utf-8"))
    binary = LAUNCHER / "node_modules/@tauri-apps/cli-win32-x64-msvc/cli.win32-x64-msvc.node"
    if package["version"] != lock["tauri_cli_version"] or digest(binary)["sha256"] != lock["tauri_cli_binary_sha256"]:
        raise ValueError("当前Tauri CLI版本或平台二进制已改变，须按该版本官方源码重新准备工具锁")
    nsis = cache / "NSIS"
    for relative, expected in lock["required_files"].items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("工具锁路径无效")
        path = nsis / name
        if digest(path) != {key: expected[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"NSIS缓存版本/固定摘要不符：{relative}；构建尚未开始，保留现状并准备准确工具")
    version = capture([str(nsis / "Bin/makensis.exe"), "/VERSION"], LAUNCHER)
    if version != lock["makensis_version_output"]:
        raise ValueError("NSIS实际版本与固定工具锁不符")
    return {"lock_sha256": digest(lock_path)["sha256"], "tauri_cli_version": package["version"],
            "tauri_cli_binary_sha256": lock["tauri_cli_binary_sha256"], "nsis_version": version,
            "verified_required_files": len(lock["required_files"]), "source_commit": lock["source"]["commit"]}


@contextmanager
def staged_bundle_resources(portable: Path, output: Path):
    """Tauri的normalize会去Windows盘符；只向bundler传src-tauri内相对路径。"""
    stage_parent = LAUNCHER / "src-tauri/target/candidate-resources"
    stage_parent.mkdir(parents=True, exist_ok=True)
    stage = stage_parent / uuid.uuid4().hex
    stage.mkdir()
    identity = {"schema_version": 1, "output": str(output.resolve()), "stage_id": stage.name}
    owner = stage / ".stage-owner.json"
    write_json(owner, identity)
    expected = {".stage-owner.json": digest(owner)}
    resources = {}
    stage_receipt = {"stage": str(stage.resolve()), "output": str(output.resolve()), "resources": {}, "cleanup": "pending"}
    try:
        for path in sorted(portable.rglob("*")):
            if not path.is_file() or path.name == "next-trainer-launcher.exe":
                continue
            relative = path.relative_to(portable)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            expected[relative.as_posix()] = digest(path)
            if digest(target) != expected[relative.as_posix()]:
                raise RuntimeError("分发资源暂存副本摘要不符")
            resources[target.relative_to(LAUNCHER / "src-tauri").as_posix()] = relative.as_posix()
        stage_receipt["resources"] = expected
        write_json(output / "resource-staging.json", stage_receipt)
        yield resources
    finally:
        # 仅删除本次唯一目录中身份未变的已知文件；不递归删除未知文件或跟随reparse。
        try:
            resolved_stage = stage.resolve()
            if resolved_stage.parent != stage_parent.resolve() or resolved_stage == stage_parent.resolve():
                raise RuntimeError("资源暂存绝对路径越界，保留现场")
            if json.loads(owner.read_text(encoding="utf-8")) != identity:
                raise RuntimeError("资源暂存归属标记变化，保留现场")
            if stage.lstat().st_file_attributes & 0x400:
                raise RuntimeError("资源暂存含reparse point，保留现场")
            paths, directories = [], [stage]
            while directories:
                for path in directories.pop().iterdir():
                    if path.lstat().st_file_attributes & 0x400:
                        raise RuntimeError("资源暂存含reparse point，保留现场")
                    paths.append(path)
                    if path.is_dir():
                        directories.append(path)
            actual = {path.relative_to(stage).as_posix(): digest(path) for path in paths if path.is_file()}
            if actual != expected:
                raise RuntimeError("资源暂存含未知文件或摘要变化，保留现场")
            for path in sorted((path for path in paths if path.is_file()), key=lambda path: len(path.parts), reverse=True):
                path.unlink()
            for path in sorted((path for path in paths if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
                path.rmdir()
            stage.rmdir()
            stage_receipt["cleanup"] = "removed_exact_owned_files"
        except Exception as error:
            stage_receipt["cleanup"] = "preserved_for_review"
            stage_receipt["cleanup_error"] = str(error)
            raise
        finally:
            write_json(output / "resource-staging.json", stage_receipt)


@contextmanager
def build_lock():
    # 与手工 Cargo 施工仍需事先协调；此锁防止本脚本的两次打包互相覆盖 target。
    import msvcrt
    path = LAUNCHER / "src-tauri" / "target" / ".candidate-build-lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("另一个候选构建持有锁；请保留 target 并等待它完成") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", required=True, type=Path, help="固定配方前端 ZIP 绝对路径")
    parser.add_argument("--output", required=True, type=Path, help="仓库之外的新绝对目录")
    parser.add_argument("--allow-dirty", action="store_true", help="允许施工候选，manifest 保存逐文件摘要与 dirty 状态")
    parser.add_argument("--preflight-only", action="store_true", help="只读核对输入与缓存，不构建或创建输出目录")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("只支持 Windows x64 原生构建")
    if not args.frontend.is_absolute() or not args.frontend.is_file():
        parser.error("--frontend 必须是现有文件的绝对路径")
    if not args.output.is_absolute() or args.output.exists():
        parser.error("--output 必须是尚不存在的绝对目录，失败现场不能覆盖")
    output = args.output.resolve()
    if output.is_relative_to(REPO):
        parser.error("构建输出必须位于仓库之外")
    for tool in ("cargo", "rustc", "node", "git"):
        if not shutil.which(tool):
            parser.error(f"缺少构建工具 {tool}")
    if os.environ.get("CARGO_TARGET_DIR") or os.environ.get("CARGO_BUILD_TARGET"):
        parser.error("请在本构建进程取消 CARGO_TARGET_DIR/CARGO_BUILD_TARGET，以使用固定 Windows target 路径")
    recipe_path = LAUNCHER / "catalog/gui-cp310-win-x64-v1.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    frontend = digest(args.frontend)
    if frontend != {key: recipe["frontend"][key] for key in ("bytes", "sha256")}:
        parser.error("前端 ZIP 不符合当前编译配方的固定 SHA256/字节数")
    engine_ids = {path.stem for path in (LAUNCHER / "catalog/engines").glob("*.json")}
    if engine_ids != {"kohya", "anima-fast", "ai-toolkit", "diffsynth"}:
        parser.error("四个指定引擎的固定锁必须齐备，不接受空目录或额外未知引擎")
    full_status = capture(["git", "status", "--porcelain=v1", "--untracked-files=all"])
    scope = ["desktop-launcher", "LICENSE", "NOTICE.md", "docs/launcher/windows-delivery.md", *worker_paths()]
    status = capture(["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *scope])
    if status and not args.allow_dirty:
        parser.error("启动器相关编译/打包输入有改动；保存基线后再构建，或显式 --allow-dirty 生成施工候选")
    cli = LAUNCHER / "node_modules/@tauri-apps/cli/tauri.js"
    cache = Path(os.environ["LOCALAPPDATA"]) / "tauri"
    try:
        tool_identity = verify_windows_tools(cache)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.error(f"Windows构建工具未通过版本/固定哈希预检：{error}")
    for path in (cli, REPO / "LICENSE", REPO / "NOTICE.md", REPO / "docs/launcher/windows-delivery.md"):
        if not path.is_file():
            parser.error(f"缺少输入 {path}")
    config = json.loads((LAUNCHER / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    if config["bundle"]["windows"]["nsis"]["installMode"] != "currentUser" or config["bundle"]["windows"]["webviewInstallMode"]["type"] != "downloadBootstrapper":
        parser.error("候选打包必须使用 currentUser 与官方 downloadBootstrapper 配置")
    preflight = {"trainer_source_commit": recipe["source_commit"], "launcher_build_commit": capture(["git", "rev-parse", "HEAD"]),
                 "frontend": frontend, "nsis_install_mode": config["bundle"]["windows"]["nsis"]["installMode"],
                 "webview_install_mode": config["bundle"]["windows"]["webviewInstallMode"], "windows_build_tools": tool_identity,
                 "network_policy": "offline-cache-only; cargo --offline; npm uses installed node_modules; bundler outbound proxy fails closed",
                 "new_network_payload_bytes": 0}
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    env = dict(os.environ)
    env.update(NEXT_TRAINER_BUNDLED_FRONTEND=str(args.frontend.resolve()), CARGO_NET_OFFLINE="true", npm_config_offline="true",
               HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9", NO_PROXY="",
               http_proxy="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9", all_proxy="http://127.0.0.1:9", no_proxy="")

    def run(name: str, command: list[str]) -> None:
        print(f"{name}: {' '.join(command)}", flush=True)
        with (logs / f"{name}.log").open("wb") as stream:
            result = subprocess.run(command, cwd=LAUNCHER, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            write_json(output / "tauri-cache-after-failure.json", cache_inventory(cache))
            raise RuntimeError(f"{name} 失败（{result.returncode}），现场与日志保留于 {output}")

    before_cache = cache_inventory(cache)
    write_json(output / "tauri-cache-before.json", before_cache)
    with build_lock():
        run("helper-build", ["cargo", "build", "--release", "--locked", "--offline", "--manifest-path", "shell-updater/Cargo.toml"])
        helper = LAUNCHER / "shell-updater/target/release/next-trainer-updater.exe"
        helper_identity = digest(helper)
        env.update(NEXT_TRAINER_UPDATER_SHA256=helper_identity["sha256"], NEXT_TRAINER_UPDATER_BYTES=str(helper_identity["bytes"]))
        run("licenses", [sys.executable, "scripts/generate_license_inventory.py"])
        inputs = source_inventory()
        inputs_digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        run("launcher-build", ["node", str(cli), "build", "--ci", "--no-bundle", "--no-sign", "--", "--locked", "--offline"])
        executable = LAUNCHER / "src-tauri/target/release/next-trainer-launcher.exe"
        executable_identity = digest(executable)
        portable = output / f"NextTrainerLauncher-{config['version']}-windows-x64"
        portable.mkdir()
        shutil.copy2(executable, portable / "next-trainer-launcher.exe")
        shutil.copy2(helper, portable / "next-trainer-updater.exe")
        for name in ("LICENSE", "NOTICE.md"):
            shutil.copy2(REPO / name, portable / name)
        shutil.copy2(REPO / "docs/launcher/windows-delivery.md", portable / "安装与恢复说明.md")
        shutil.copytree(LAUNCHER / "LICENSES", portable / "LICENSES")
        metadata = {"schema_version": 1, "kind": "development-candidate", "public_release": False,
                    "created_at": datetime.now(timezone.utc).isoformat(), "version": config["version"], **preflight,
                    "launcher_worktree_dirty": bool(status), "worktree_has_other_changes": full_status != status,
                    "launcher_source_digest": inputs_digest,
                    "catalog_digest": digest(LAUNCHER / "catalog/releases.json")["sha256"],
                    "recipe_digest": digest(recipe_path)["sha256"], "trainer_frontend": frontend,
                    "signed_fixture_digest": digest(LAUNCHER / "catalog/signed-fixtures-v1.json")["sha256"],
                    "launcher": executable_identity, "helper": helper_identity,
                    "catalog_signature": "embedded catalog plus public test fixtures; production key/channel not configured",
                    "windows_code_signature": "unsigned-development-candidate",
                    "validation": {"construction": "build-only", "final_validation": "pending M6", "clean_windows": "not-run",
                                   "missing_webview2": "not-run", "engine_real_install": "not-run-at-build", "gpu_training": "not-run-at-build"},
                    "tool_versions": {tool: capture(command, LAUNCHER) for tool, command in {
                        "rustc": ["rustc", "--version"], "cargo": ["cargo", "--version"], "node": ["node", "--version"],
                        "tauri": ["node", str(cli), "--version"]}.items()}}
        write_json(portable / "build-manifest.json", metadata)
        write_json(output / "source-inputs.json", inputs)
        (output / "git-status-scoped.txt").write_text(status + "\n", encoding="utf-8")
        (output / "git-status-all.txt").write_text(full_status + "\n", encoding="utf-8")
        bundle_config = output / "bundle.config.json"
        with staged_bundle_resources(portable, output) as resources:
            # 来源为Rust构建目录内相对路径；目标仍为EXE同级固定名字。
            write_json(bundle_config, {"bundle": {"resources": resources}})
            # 禁止 bundler 修改已锁定 EXE；NSIS 与便携包使用完全相同的二进制。
            bundle_started = time.time()
            run("nsis-bundle", ["node", str(cli), "bundle", "--ci", "--bundles", "nsis", "--no-sign", "--no-binary-patching", "--config", str(bundle_config)])
        if digest(executable) != executable_identity or source_inventory() != inputs:
            raise RuntimeError("构建期间 EXE 或源输入发生变化，保留候选但拒绝冻结")
        nsis_root = LAUNCHER / "src-tauri/target/release/bundle/nsis"
        installers = [path for path in nsis_root.glob("*.exe") if path.stat().st_mtime >= bundle_started - 2]
        if not installers:
            raise RuntimeError("NSIS 命令返回成功但未发现安装器")
        installer_dir = output / "installers"
        installer_dir.mkdir()
        for installer in installers:
            shutil.copy2(installer, installer_dir / installer.name)
        package = output / (portable.name + "-portable.zip")
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(portable.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output))
        after_cache = cache_inventory(cache)
        write_json(output / "tauri-cache-after.json", after_cache)
        changed_cache = {name: value for name, value in after_cache.items() if before_cache.get(name) != value}
        if changed_cache:
            raise RuntimeError("离线打包期间 Tauri 工具缓存出现新字节，保留现场并要求核对来源/网络计量")
        artifacts = {path.relative_to(output).as_posix(): digest(path) for path in [package, *installer_dir.glob("*.exe")]}
        write_json(output / "delivery-manifest.json", {"build": metadata, "artifacts": artifacts, "cache_changes": changed_cache,
                   "cache_measurement": "file hashes and byte lengths; not a network traffic counter; outbound disabled for this build"})
        (output / "SHA256SUMS.txt").write_text("".join(f"{record['sha256']}  {name}\n" for name, record in sorted(artifacts.items())), encoding="utf-8")
        print(json.dumps({"output": str(output), "artifacts": artifacts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
