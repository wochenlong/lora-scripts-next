"""同一只读/计划/执行核心供桌面、网页和 CLI 调用。所有下载在外部受控层完成。"""
from __future__ import annotations

import base64
from contextvars import ContextVar
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile

from .recipes import capabilities, recipe
from .runtime import ControlError, RuntimeLayout, atomic_json, canonical, digest_json, engine_activity, engine_lease, guard, is_reparse, read_json, relative, sha_file


MAX_FILE = 8 * 1024 * 1024 * 1024
MAX_STATE_FILES = 200000
_CANCEL_PATH = ContextVar("launcher_cancel_path", default=None)


def _layout(request, instance_id=""):
    return RuntimeLayout(Path(request["root"]), request["release_id"], request["engine_id"], instance_id, request.get("profile_id", "default"))


def _file(path: Path, root: Path) -> dict:
    guard(path, root)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ControlError("invalid_file", f"不是限额内普通文件：{path}")
    return {"bytes": path.stat().st_size, "sha256": sha_file(path)}


def _derived_bytecode(name):
    return name.endswith(".pyc") or "__pycache__" in Path(name).parts


def _state(layout):
    path = layout.checked(layout.state_file)
    if not path.exists():
        return None
    state = read_json(path)
    if state.get("schema_version") != 1 or state.get("engine_id") != layout.engine_id or state.get("release_id") != layout.release_id:
        raise ControlError("incompatible_state", "引擎状态身份或 schema 不支持")
    RuntimeLayout(layout.root, layout.release_id, layout.engine_id, state["instance_id"], state.get("profile_id", "default"))
    if not isinstance(state.get("generation"), int) or state["generation"] < 1:
        raise ControlError("incompatible_state", "引擎 generation 无效")
    if not isinstance(state.get("validated_generation"), int) or not 0 <= state["validated_generation"] <= state["generation"] or not isinstance(state.get("dirty"), bool):
        raise ControlError("incompatible_state", "引擎验证代次或 dirty 标记无效")
    return state


def _asset(layout, item):
    digest = item["sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ControlError("invalid_asset", "资产摘要格式不支持")
    if not isinstance(item["filename"], str) or len(relative(item["filename"]).parts) != 1 or not isinstance(item["bytes"], int) or not 0 < item["bytes"] <= MAX_FILE:
        raise ControlError("invalid_asset", "资产文件名不支持")
    path = layout.checked(layout.root / "cache" / "engine-assets" / digest / item["filename"])
    if not path.is_file() or _file(path, layout.root) != {"bytes": item["bytes"], "sha256": digest}:
        raise ControlError("asset_missing", f"固定资产未下载或摘要不符：{item['filename']}")
    return path


def _lock(layout, request):
    """lock 路径及摘要由已验签清单/Rust 内置信任根提供，不能从待修树生成。"""
    lock_path = layout.checked(Path(request["lock_path"]))
    if sha_file(lock_path) != request["lock_sha256"]:
        raise ControlError("lock_identity_changed", "引擎锁文件摘要已变化")
    lock = read_json(lock_path)
    expected = recipe(layout.engine_id)
    if lock.get("schema_version") != 1 or lock.get("engine_id") != layout.engine_id or lock.get("recipe_sha256") != expected["recipe_sha256"]:
        raise ControlError("lock_recipe_mismatch", "资产锁不属于当前固定配方")
    if lock.get("platform") != "windows-x86_64" or not lock.get("wheels") or not lock.get("python", {}).get("version"):
        raise ControlError("incomplete_lock", "资产锁未固定平台、解释器与依赖闭包")
    if lock["python"]["version"].split(".")[:2] != expected["python"].split(".")[:2]:
        raise ControlError("incompatible_python", "资产锁解释器与固定配方 ABI 不符")
    for wheel in lock["wheels"]:
        relative(wheel["filename"])
        if not wheel["filename"].endswith(".whl"):
            raise ControlError("incomplete_lock", "不允许运行未锁定的源码构建")
    if len({w["name"] for w in lock["wheels"]}) != len(lock["wheels"]):
        raise ControlError("incomplete_lock", "同一依赖只能锁定一个版本")
    source = lock.get("source", {})
    if not source.get("files") or source.get("entry") not in source["files"]:
        raise ControlError("incomplete_lock", "源码入口必须列入固定文件清单")
    for files in (source["files"], lock["python"].get("files", {})):
        if len(files) > MAX_STATE_FILES:
            raise ControlError("tree_limit", "锁文件超过文件数上限")
        for name, value in files.items():
            relative(name)
            if not isinstance(value.get("bytes"), int) or value["bytes"] < 0 or value["bytes"] > MAX_FILE or not re.fullmatch("[a-f0-9]{64}", value.get("sha256", "")):
                raise ControlError("incomplete_lock", "固定文件摘要格式无效")
    relative(lock["python"]["executable_relative"])
    return lock


def _receipt(layout, state):
    expected_relative = f"instances/{state['instance_id']}/{state['validated_generation']}.json"
    if state.get("receipt_relative") != expected_relative:
        raise ControlError("receipt_identity", "收据必须属于当前实例已验证代次")
    path = layout.checked(layout.state_root / relative(expected_relative))
    if not path.is_file() or sha_file(path) != state.get("receipt_sha256"):
        raise ControlError("receipt_missing_or_changed", "引擎收据缺失或摘要变化，禁止写入")
    result = read_json(path)
    if any(result.get(name) != state.get(name) for name in ("engine_id", "release_id", "instance_id", "recipe_sha256", "lock_sha256")) or result.get("generation") != state["validated_generation"]:
        raise ControlError("receipt_identity", "引擎收据与当前绑定不一致")
    return result


def inspect_readonly(request):
    layout = _layout(request)
    fixed = recipe(layout.engine_id)
    report = {"schema_version": 1, "engine_id": layout.engine_id, "layout": layout.as_dict(), "recipe": fixed,
              "installation": "missing", "import": "not_checked", "gpu": "not_checked", "training": "not_checked", "actions": [], "issues": [], "network_bytes": 0, "activity": engine_activity(layout)}
    try:
        state = _state(layout)
        if state is None:
            report["actions"] = ["plan_install"]
            # 无登记但存在命名空间里的实体不能声称未安装。
            if layout.state_root.exists():
                report["installation"] = "unknown"
                report["issues"].append({"code": "missing_binding", "message": "引擎目录存在但缺少绑定，先审查恢复计划"})
            return report
        current = _layout(request, state["instance_id"])
        if state.get("recipe_sha256") != fixed["recipe_sha256"]:
            raise ControlError("recipe_changed", "当前源码配方与已安装实例不同，需显式新实例重建")
        report.update(layout=current.as_dict(), state=state, installation="damaged" if state.get("dirty") or state.get("pending") else "ready")
        if state.get("pending"):
            report.update(actions=["recover", "plan_install"], issues=[{"code": "pending_recovery", "message": "引擎事务未结束；可恢复或显式新实例重建"}])
            return report
        if state.get("validated_generation") != state["generation"] or state.get("status") != "ready":
            raise ControlError("unvalidated_generation", "引擎代次未验证")
        receipt = _receipt(current, state)
        broken = []
        for area, files in receipt["files"].items():
            root = current.environment_root if area == "environment" else current.engine_source_root
            for name, expected in files.items():
                path = current.checked(root / relative(name))
                if not path.is_file() or _file(path, current.root) != expected:
                    broken.append({"area": area, "path": name, "package": receipt.get("package_files", {}).get(name) if area == "environment" else None})
            extras = set(_tree(root, current.root)) - set(files)
            broken.extend({"area": area, "path": name, "package": None, "unexpected": True} for name in sorted(extras))
        for name, expected in receipt.get("base_python_files", {}).items():
            path = current.checked(current.base_python_root / relative(name))
            if not path.is_file() or _file(path, current.root) != expected:
                broken.append({"area": "base_python", "path": name, "package": None})
        if broken:
            report["installation"] = "damaged"
            report["issues"].extend(broken)
        report["actions"] = ["plan_repair"] if broken or state.get("dirty") else ["probe_execute", "plan_repair"]
        if state.get("pending"):
            report["actions"] = ["recover"]
        report["layers"] = {"installed": report["installation"], "import": "not_checked", "gpu": "skip + CR-004", "training": "skip + CR-004"}
        return report
    except (OSError, ValueError, KeyError, TypeError, ControlError) as error:
        report.update(installation="unknown", actions=[])
        report["issues"].append({"code": getattr(error, "code", "inspection_failed"), "message": str(error)})
        return report


def _tree(root: Path, workspace: Path) -> dict:
    result = {}
    if not root.exists():
        return result
    guard(root, workspace)
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            guard(Path(directory) / name, workspace)
        for name in files:
            path = Path(directory) / name
            if path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            guard(path, workspace)
            result[path.relative_to(root).as_posix()] = _file(path, workspace)
            if len(result) > MAX_STATE_FILES:
                raise ControlError("tree_limit", "引擎闭包超过文件数上限")
    return result


def _site_root(environment):
    if os.name == "nt":
        return environment / "Lib" / "site-packages"
    candidates = list((environment / "lib").glob("python*/site-packages"))
    return candidates[0] if len(candidates) == 1 else environment / "lib" / "missing-site-packages"


def _wheel_inventory(layout, lock, verify_packages=None):
    site = _site_root(layout.environment_root)
    files = {}
    packages = {}
    for wheel in lock["wheels"]:
        normalized = wheel["name"].replace("-", "_").lower()
        candidates = [p for p in site.glob("*.dist-info") if p.name.lower().startswith(normalized + "-")]
        if len(candidates) != 1:
            raise ControlError("package_record_missing", f"缺少唯一包记录：{wheel['name']}")
        record = candidates[0] / "RECORD"
        guard(record, layout.root)
        if verify_packages is None or wheel["name"] in verify_packages:
            with zipfile.ZipFile(_asset(layout, wheel)) as bundle:
                seen = set()
                for info in bundle.infolist():
                    if info.is_dir():
                        continue
                    member = relative(info.filename).as_posix()
                    if member in seen or info.file_size > MAX_FILE or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                        raise ControlError("unsafe_wheel", "wheel 包含重复、超限或链接成员")
                    seen.add(member)
                    if member.endswith(".dist-info/RECORD"):
                        continue
                    parts = member.split("/")
                    if parts[0].endswith(".data"):
                        if len(parts) < 3 or parts[1] not in {"purelib", "platlib", "data", "scripts", "headers"}:
                            raise ControlError("unsupported_wheel_scheme", "wheel 安装布局不支持")
                        if parts[1] in {"scripts", "headers"}:
                            # 由固定 uv 安装器重写脚本；随后收据记录最终字节。
                            continue
                        installed = (site if parts[1] in {"purelib", "platlib"} else layout.environment_root).joinpath(*parts[2:])
                    else:
                        installed = site / relative(member)
                    digest = hashlib.sha256()
                    with bundle.open(info) as stream:
                        for payload in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(payload)
                    expected = {"bytes": info.file_size, "sha256": digest.hexdigest()}
                    if _file(installed, layout.root) != expected:
                        raise ControlError("wheel_payload_changed", f"安装内容不匹配锁定 wheel：{member}")
        for row in csv.reader(io.StringIO(record.read_text(encoding="utf-8"))):
            if not row:
                continue
            path = Path(os.path.abspath(site / row[0]))
            guard(path, layout.environment_root)
            if path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            name = path.relative_to(layout.environment_root).as_posix()
            files[name] = _file(path, layout.root)
            packages[name] = wheel["name"]
    return files, packages


def _source_files(lock):
    return lock.get("source", {}).get("files", {})


def _observe(layout, lock, verify_packages=None):
    files, packages = _wheel_inventory(layout, lock, verify_packages)
    for path in [layout.python, layout.environment_root / "pyvenv.cfg"]:
        files[path.relative_to(layout.environment_root).as_posix()] = _file(path, layout.root)
    # 整棵实例均纳入收据，额外注入文件不能成为未观测的导入路径。
    files.update(_tree(layout.environment_root, layout.root))
    source = {}
    for name, value in _source_files(lock).items():
        path = layout.checked(layout.engine_source_root / relative(name))
        actual = _file(path, layout.root)
        if actual != value:
            raise ControlError("source_integrity", f"引擎源码不符合固定来源：{name}")
        source[name] = actual
    if lock.get("source", {}).get("entry") not in source:
        raise ControlError("source_entry_missing", "引擎入口未列入固定源码闭包")
    return {"files": {"environment": files, "source": source}, "package_files": packages}


def _assets(lock):
    return [lock["uv"].get("archive", lock["uv"]), *lock["wheels"], *([lock["python"]["archive"]] if lock["python"].get("archive") else []), *([lock["source"]["archive"]] if lock.get("source", {}).get("archive") else [])]


def plan(request, installing=False):
    layout = _layout(request)
    lock = _lock(layout, request)
    state = _state(layout)
    if installing and state and not request.get("rebuild"):
        raise ControlError("already_installed", "已有引擎请使用精准修复或显式重建")
    if not installing and not state:
        raise ControlError("missing_binding", "缺少引擎绑定；不能猜测已有环境所有权")
    if state and state.get("pending") and not (installing and request.get("rebuild")):
        raise ControlError("pending_recovery", "存在未结束事务，请先恢复")
    issues = [] if installing else inspect_readonly(request)["issues"]
    if any("code" in issue for issue in issues):
        raise ControlError("unsafe_state", "状态或收据未知，拒绝生成可写计划")
    if not installing and state["recipe_sha256"] != lock["recipe_sha256"]:
        raise ControlError("recipe_changed", "配方升级必须显式新实例重建")
    if not installing and state.get("lock_sha256") != request["lock_sha256"]:
        raise ControlError("lock_changed", "依赖锁变化必须显式新实例重建")
    if any(issue.get("unexpected") for issue in issues):
        raise ControlError("unexpected_files", "存在未登记文件，保留现场并显式重建")
    packages = sorted({issue["package"] for issue in issues if issue.get("package")})
    source_paths = sorted(issue["path"] for issue in issues if issue.get("area") == "source")
    python_damage = any(issue.get("area") == "base_python" or (issue.get("area") == "environment" and not issue.get("package")) for issue in issues)
    if python_damage and not installing:
        raise ControlError("interpreter_damaged", "解释器控制文件损坏，请先修复基础 Python 或显式重建实例")
    instance = request.get("candidate_instance_id", "t" + uuid.uuid4().hex[:15]) if installing else state["instance_id"]
    next_layout = _layout(request, instance)
    needed = _assets(lock) if installing else [lock["uv"].get("archive", lock["uv"]), *(w for w in lock["wheels"] if w["name"] in packages), *([lock["source"]["archive"]] if source_paths and lock.get("source", {}).get("archive") else [])]
    missing = []
    for item in needed:
        try:
            _asset(next_layout, item)
        except ControlError:
            missing.append(item)
    result = {"schema_version": 1, "engine_id": layout.engine_id, "release_id": layout.release_id, "profile_id": layout.profile_id, "kind": "install" if installing else "repair", "rebuild": bool(request.get("rebuild")), "recipe_sha256": lock["recipe_sha256"], "lock_sha256": request["lock_sha256"], "prior_state_sha256": digest_json(state), "instance_id": instance, "expected_generation": state["generation"] if state else 0, "packages": packages, "source_paths": source_paths,
              "assets": needed, "missing_assets": missing, "download_bytes": sum(a["bytes"] for a in missing), "write_roots": [str(next_layout.environment_root), str(next_layout.engine_source_root), str(next_layout.base_python_root), str(next_layout.state_root)], "profile_writes": [], "main_env_fallback": False,
              "status": "assets_required" if missing else "ready", "issues": issues}
    result["plan_sha256"] = digest_json(result)
    return result


def _run(command, layout, operation, timeout=1800):
    env = {k: v for k, v in os.environ.items() if k.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PIP_NO_INDEX="1", UV_OFFLINE="1", UV_LINK_MODE="copy", UV_PYTHON_DOWNLOADS="never", UV_PYTHON_INSTALL_DIR=str(layout.base_python_root), UV_CACHE_DIR=str(layout.root / "cache" / "uv-engines"), TEMP=str(operation), TMP=str(operation))
    log = layout.checked(operation / "commands.jsonl")
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"command": [str(x) for x in command], "at": time.time()}, ensure_ascii=False) + "\n")
    with (operation / "stdout.log").open("ab") as stdout, (operation / "stderr.log").open("ab") as stderr:
        process = subprocess.Popen([str(x) for x in command], cwd=str(layout.root), env=env, stdout=stdout, stderr=stderr, creationflags=0x08000200 if os.name == "nt" else 0, start_new_session=os.name != "nt")
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            cancel_path = _CANCEL_PATH.get()
            cancelled = cancel_path is not None and cancel_path.exists()
            if cancelled or time.monotonic() > deadline:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=0x08000000, timeout=15)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
                raise ControlError("cancelled" if cancelled else "command_timeout", "受管命令及其子进程已停止，事务保留待恢复")
            time.sleep(0.1)
    if process.returncode:
        raise ControlError("command_failed", f"受管命令退出 {process.returncode}；日志：{operation}")


def _copy_archive(archive, destination, manifest, strip_prefix, workspace, paths=None):
    names = set(manifest if paths is None else paths)
    if strip_prefix and not strip_prefix.endswith("/"):
        raise ControlError("unsafe_archive_prefix", "归档前缀必须以斜线结束")
    seen = set()
    copied = set()
    count = 0
    with zipfile.ZipFile(archive) if zipfile.is_zipfile(archive) else tarfile.open(archive, "r:*") as bundle:
        zipped = isinstance(bundle, zipfile.ZipFile)
        entries = bundle.infolist() if zipped else bundle
        for entry in entries:
            count += 1
            if count > MAX_STATE_FILES:
                raise ControlError("tree_limit", "归档成员超过限额")
            name = entry.filename if zipped else entry.name
            directory = entry.is_dir() if zipped else entry.isdir()
            relative(name.rstrip("/"))
            link = ((entry.external_attr >> 16) & 0o170000) == 0o120000 if zipped else not (entry.isfile() or entry.isdir())
            size = entry.file_size if zipped else entry.size
            if name in seen or link or size > MAX_FILE:
                raise ControlError("unsafe_archive", "归档有重复、链接、特殊或超限成员")
            seen.add(name)
            if directory or not name.startswith(strip_prefix):
                continue
            local = name[len(strip_prefix):]
            if local not in names:
                continue
            expected = manifest[local]
            if size != expected["bytes"]:
                raise ControlError("archive_hash", f"归档文件长度不符：{local}")
            target = guard(destination / relative(local), workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            source = bundle.open(entry) if zipped else bundle.extractfile(entry)
            with source, target.open("wb") as output:
                for value in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(value)
                    output.write(value)
            if digest.hexdigest() != expected["sha256"]:
                raise ControlError("archive_hash", f"归档文件摘要不符：{local}")
            if not zipped and os.name != "nt":
                target.chmod(entry.mode & 0o777)
            copied.add(local)
    if copied != names:
        raise ControlError("archive_missing_files", "归档未包含全部固定文件")


def _prepare_python(layout, lock):
    fixed = lock["python"]
    manifest = fixed.get("files", {fixed["executable_relative"]: {"bytes": fixed["bytes"], "sha256": fixed["sha256"]}})
    if fixed.get("archive"):
        if layout.base_python_root.exists():
            raise ControlError("base_python_collision", "新实例的基础 Python 路径已存在")
        _copy_archive(_asset(layout, fixed["archive"]), layout.base_python_root, manifest, fixed.get("strip_prefix", ""), layout.root)
    for name, expected in manifest.items():
        if _file(layout.checked(layout.base_python_root / relative(name)), layout.root) != expected:
            raise ControlError("base_python_damaged", "基础 Python 不符合固定文件清单")
    # 官方归档包含预编译缓存；查询解释器会因安装路径/mtime重建缓存。
    # 归档本身仍逐文件验真，运行收据只承诺解释器/stdlib源/扩展等原始文件。
    return {name: value for name, value in manifest.items() if not _derived_bytecode(name)}


def _prepare_uv(layout, lock):
    fixed = lock["uv"]
    if not fixed.get("archive"):
        return _asset(layout, fixed)
    # 不同引擎可并行安装；工具解压也落在各自锁保护的命名空间。
    root = layout.checked(layout.root / "cache" / "engine-tools" / layout.engine_id / fixed["sha256"])
    target = layout.checked(root / "uv.exe")
    expected = {"bytes": fixed["bytes"], "sha256": fixed["sha256"]}
    if not target.is_file() or _file(target, layout.root) != expected:
        member = relative(fixed["archive_member"]).as_posix()
        prefix = member[:-len("uv.exe")] if member.endswith("uv.exe") else ""
        if not member.endswith("uv.exe"):
            raise ControlError("tool_entry", "uv 归档入口必须是 uv.exe")
        _copy_archive(_asset(layout, fixed["archive"]), root, {"uv.exe": expected}, prefix, layout.root)
    return target


def _copy_source(layout, lock, paths=None):
    source = lock["source"]
    names = paths if paths is not None else list(source["files"])
    if source.get("archive"):
        _copy_archive(_asset(layout, source["archive"]), layout.engine_source_root, source["files"], source.get("strip_prefix", ""), layout.root, names)
    else:
        origin = layout.checked(layout.source_root if source["trainer_relative"] == "." else layout.source_root / relative(source["trainer_relative"]))
        for name in names:
            src = guard(origin / relative(name), layout.root)
            if _file(src, layout.root) != source["files"][name]:
                raise ControlError("source_hash", f"发布源码摘要不符：{name}")
            target = layout.checked(layout.engine_source_root / relative(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)


def _snapshot(layout, receipt, packages, paths, operation):
    entries = []
    for name, expected in receipt["files"]["environment"].items():
        if receipt["package_files"].get(name) in packages:
            entries.append(("environment", name))
    entries += [("source", name) for name in paths]
    saved = []
    for area, name in entries:
        root = layout.environment_root if area == "environment" else layout.engine_source_root
        path = layout.checked(root / relative(name))
        target = layout.checked(operation / "snapshot" / area / relative(name))
        if path.exists():
            fingerprint = _file(path, layout.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            saved.append({"area": area, "path": name, "existed": True, **fingerprint})
        else:
            saved.append({"area": area, "path": name, "existed": False})
    atomic_json(operation / "snapshot.json", saved)
    atomic_json(operation / "baseline.json", {"environment": _tree(layout.environment_root, layout.root), "source": _tree(layout.engine_source_root, layout.root)})


def repair_apply(request):
    initial = request["plan"]
    unsigned = dict(initial)
    claimed = unsigned.pop("plan_sha256", None)
    if claimed != digest_json(unsigned) or claimed != request.get("plan_sha256"):
        raise ControlError("plan_digest", "修复计划摘要不符")
    layout = _layout(request)
    with engine_lease(layout):
        lock = _lock(layout, request)
        current = plan({**request, "candidate_instance_id": initial["instance_id"], "rebuild": initial.get("rebuild", False)}, installing=initial["kind"] == "install")
        # 缓存下载是计划执行的一部分；只容许缺失列表减少到零。
        dynamic = {"missing_assets", "download_bytes", "status", "plan_sha256"}
        identity = lambda value: {key: item for key, item in value.items() if key not in dynamic}
        if identity(current) != identity(initial) or current["missing_assets"]:
            raise ControlError("plan_stale", "事实、绑定或资产已改变，请重新审查计划")
        if initial["kind"] == "repair" and not initial["issues"]:
            return {"status": "no_changes", "state": _state(layout), "installation": "ready", "import": "not_checked"}
        state = _state(layout)
        target = _layout(request, initial["instance_id"])
        operation = target.checked(target.state_root / "operations" / ("op-" + uuid.uuid4().hex))
        operation.mkdir(parents=True)
        atomic_json(operation / "plan.json", initial)
        old = state
        if state:
            atomic_json(operation / "old-binding.json", state)
        if initial["kind"] == "install":
            if any(path.exists() for path in (target.environment_root, target.engine_source_root, target.base_python_root)):
                raise ControlError("instance_collision", "新环境固定路径已存在")
            prior_receipt = None
            untouched = {}
        else:
            prior_receipt = _receipt(target, state)
            untouched = {name: value for name, value in prior_receipt["files"]["environment"].items() if prior_receipt["package_files"].get(name) not in initial["packages"]}
            _snapshot(target, prior_receipt, initial["packages"], initial["source_paths"], operation)
        previous = {key: old[key] for key in ("instance_id", "generation", "validated_generation", "receipt_relative", "receipt_sha256") if key in old} if old else None
        state = {"schema_version": 1, "engine_id": target.engine_id, "release_id": target.release_id, "profile_id": target.profile_id, "instance_id": target.instance_id, "generation": initial["expected_generation"] + 1, "validated_generation": 0, "recipe_sha256": lock["recipe_sha256"], "lock_sha256": request["lock_sha256"], "python_version": lock["python"]["version"], "python_root": str(target.base_python_root), "environment_root": str(target.environment_root), "source_root": str(target.engine_source_root), "status": "pending", "dirty": True, "pending": str(operation.relative_to(target.root).as_posix()), "previous": previous}
        atomic_json(target.state_file, state)
        try:
            uv = _prepare_uv(target, lock)
            if initial["kind"] == "install":
                base_files = _prepare_python(target, lock)
                base = target.checked(target.base_python_root / relative(lock["python"]["executable_relative"]))
                _run([uv, "venv", "--offline", "--no-python-downloads", "--python", base, target.environment_root], target, operation)
                _copy_source(target, lock)
            else:
                base_files = prior_receipt.get("base_python_files", {})
            wheels = lock["wheels"] if initial["kind"] == "install" else [w for w in lock["wheels"] if w["name"] in initial["packages"]]
            if wheels:
                command = [uv, "pip", "install", "--offline", "--no-deps", "--no-index", "--python", target.python]
                if initial["kind"] == "repair":
                    command += ["--reinstall"]
                _run([*command, *[_asset(target, wheel) for wheel in wheels]], target, operation)
            if initial["source_paths"]:
                _copy_source(target, lock, initial["source_paths"])
            observed = _observe(target, lock, None if initial["kind"] == "install" else initial["packages"])
            for name, expected in untouched.items():
                if observed["files"]["environment"].get(name) != expected:
                    raise ControlError("untargeted_file_changed", f"精准修复修改了非目标文件：{name}")
            receipt = {"schema_version": 1, "engine_id": target.engine_id, "release_id": target.release_id, "profile_id": target.profile_id, "instance_id": target.instance_id, "generation": state["generation"], "recipe_sha256": lock["recipe_sha256"], "lock_sha256": request["lock_sha256"], **observed, "base_python_files": base_files, "import": "not_checked", "gpu": "skip + CR-004", "training": "skip + CR-004"}
            record = target.checked(target.state_root / "instances" / target.instance_id / (str(state["generation"]) + ".json"))
            atomic_json(record, receipt)
            state.update(validated_generation=state["generation"], dirty=False, status="ready", pending=None, receipt_relative=record.relative_to(target.state_root).as_posix(), receipt_sha256=sha_file(record))
            atomic_json(target.state_file, state)
            atomic_json(operation / "result.json", {"status": "succeeded", "generation": state["generation"]})
            return {"status": "succeeded", "state": state, "operation": str(operation), "installation": "ready", "import": "not_checked", "gpu": "skip + CR-004", "training": "skip + CR-004"}
        except BaseException as error:
            state["status"] = "interrupted" if getattr(error, "code", "") == "cancelled" else "failed"
            atomic_json(target.state_file, state)
            atomic_json(operation / "result.json", {"status": "failed", "code": getattr(error, "code", "execution_failed"), "message": str(error)})
            raise


def recover(request):
    layout = _layout(request)
    with engine_lease(layout):
        state = _state(layout)
        if not state or not state.get("pending"):
            raise ControlError("no_pending_operation", "没有可恢复的引擎事务")
        target = _layout(request, state["instance_id"])
        operation = layout.checked(layout.root / relative(state["pending"]))
        snapshot = operation / "snapshot.json"
        old_path = operation / "old-binding.json"
        if not old_path.exists():
            # 首次安装中断只保留不可启用候选，不反向授信为已安装。
            return {"status": "requires_rebuild", "dirty": True, "operation": str(operation), "reason": "新安装未有已验证旧绑定；保留现场并显式重建"}
        old = read_json(old_path)
        if not snapshot.exists():
            # 重建写入的是新实例，旧实例从未参与写操作。
            atomic_json(target.state_file, old)
            atomic_json(operation / "recovery.json", {"status": "restored_binding", "generation": old["generation"]})
            return {"status": "restored_binding", "state": old, "installation": inspect_readonly(request)["installation"]}
        for item in read_json(snapshot):
            root = target.environment_root if item["area"] == "environment" else target.engine_source_root
            path = target.checked(root / relative(item["path"]))
            if item["existed"]:
                backup = target.checked(operation / "snapshot" / item["area"] / relative(item["path"]))
                if _file(backup, target.root) != {"bytes": item["bytes"], "sha256": item["sha256"]}:
                    raise ControlError("snapshot_changed", "修复快照已变化，禁止恢复")
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(backup, path)
            elif path.exists():
                guard(path, target.root)
                path.unlink()
        baseline = read_json(operation / "baseline.json")
        for area, expected_files in baseline.items():
            tree_root = target.environment_root if area == "environment" else target.engine_source_root
            current_files = _tree(tree_root, target.root)
            for extra in set(current_files) - set(expected_files):
                target.checked(tree_root / relative(extra)).unlink()
            if _tree(tree_root, target.root) != expected_files:
                raise ControlError("restore_not_validated", "快照未完整恢复事务前字节，保持 dirty")
        atomic_json(target.state_file, old)
        report = inspect_readonly(request)
        atomic_json(operation / "recovery.json", {"status": "restored", "generation": old["generation"]})
        return {"status": "restored", "state": old, "installation": report["installation"]}


def probe_execute(request):
    layout = _layout(request)
    with engine_lease(layout):
        report = inspect_readonly(request)
        if report["installation"] != "ready":
            raise ControlError("engine_not_ready", "引擎未验证或 dirty，不能执行探测")
        state = _state(layout)
        current = _layout(request, state["instance_id"])
        temporary = current.checked(current.state_root / "probes" / uuid.uuid4().hex)
        temporary.mkdir(parents=True)
        scope = request.get("probe_scope", "imports")
        if scope not in {"metadata", "imports", "cuda"}:
            raise ControlError("unsupported_probe", "只支持 metadata、imports、cuda 探测")
        modules = recipe(current.engine_id)["imports"] if scope != "metadata" else []
        code = "\n".join([
            "import sys,json,importlib,importlib.metadata as m",
            "sys.path.insert(0," + repr(str(current.engine_source_root)) + ")",
            "facts={'prefix':sys.prefix,'base_prefix':sys.base_prefix,'python':sys.version,'versions':{d.metadata['Name']:d.version for d in m.distributions() if d.metadata.get('Name')},'imports':{},'gpu':'not_checked'}",
            "for name in " + repr(modules) + ":",
            " try: importlib.import_module(name); facts['imports'][name]={'status':'ready'}",
            " except Exception as error: facts['imports'][name]={'status':'failed','error':str(error)[:1000]}",
            "if " + repr(scope == "cuda") + ":",
            " try:",
            "  import torch",
            "  facts['gpu']={'available':torch.cuda.is_available(),'devices':torch.cuda.device_count(),'cuda':torch.version.cuda}",
            " except Exception as error: facts['gpu']={'error':str(error)[:1000]}",
            "print(json.dumps(facts))",
        ])
        _run([current.python, "-I", "-B", "-c", code], current, temporary, timeout=120)
        output = (temporary / "stdout.log").read_text(encoding="utf-8", errors="replace")
        facts = json.loads(output.strip().splitlines()[-1])
        if Path(facts["prefix"]).resolve() != current.environment_root.resolve():
            raise ControlError("wrong_interpreter", "探测解释器前缀不属于受管实例")
        import_status = "metadata_only" if scope == "metadata" else "failed" if any(value["status"] != "ready" for value in facts["imports"].values()) else "ready"
        value = {"status": "failed" if import_status == "failed" else "ready", "facts": facts, "import": import_status, "gpu": facts["gpu"], "training": "not_checked", "scope": scope}
        atomic_json(temporary / "result.json", value)
        return value


def dispatch(request):
    if not isinstance(request, dict) or request.get("schema_version", 1) != 1:
        raise ControlError("protocol_version", "worker 协议版本不支持")
    action = request.get("action")
    _CANCEL_PATH.set(None)
    if request.get("cancel_file"):
        layout = _layout(request)
        _CANCEL_PATH.set(guard(Path(request["cancel_file"]), layout.root / "state"))
    if action == "capabilities":
        return capabilities()
    if action == "recipe":
        return recipe(request["engine_id"])
    if action == "inspect_readonly":
        return inspect_readonly(request)
    if action == "availability":
        return engine_activity(_layout(request))
    if action in {"plan_install", "plan_repair"}:
        return plan(request, installing=action == "plan_install")
    if action == "repair_apply":
        return repair_apply(request)
    if action == "recover":
        return recover(request)
    if action == "probe_execute":
        return probe_execute(request)
    raise ControlError("unsupported_action", "不支持该 worker 动作")
