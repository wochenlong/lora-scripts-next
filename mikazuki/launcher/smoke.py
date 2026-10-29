"""最终包的固定四引擎微型夹具。只模拟 uv；不安装训练依赖或执行训练。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mikazuki.launcher import control
from mikazuki.launcher.recipes import ENGINES, recipe
from mikazuki.launcher.runtime import ControlError, RuntimeLayout, atomic_json, guard, sha_file


class TinyFixture:
    def __init__(self, root, engine):
        self.root = root
        root.mkdir()
        (root / ".launcher-workspace").write_text("next-trainer-desktop-v1", encoding="utf-8")
        self.request = {"schema_version": 1, "root": str(root), "release_id": "fixture-v1", "engine_id": engine}
        self.assets = {}
        self.layout = RuntimeLayout(root, "fixture-v1", engine)
        wheels = []
        for package in ("fixture_alpha", "fixture_beta"):
            path = root / (package + "-1.0-py3-none-any.whl")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(package + ".py", "VALUE = 'original'\n")
                archive.writestr(package + "-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: " + package + "\nVersion: 1.0\n")
                archive.writestr(package + "-1.0.dist-info/RECORD", "")
            wheels.append({"name": package, "version": "1.0", **self.asset(path)})
        python_archive = root / "python-fixture.zip"
        python_bytes = b"fixture base interpreter - never executed"
        with zipfile.ZipFile(python_archive, "w") as archive:
            archive.writestr("python.exe", python_bytes)
        python_file = {"bytes": len(python_bytes), "sha256": hashlib.sha256(python_bytes).hexdigest()}
        uv = root / "uv-fixture.exe"
        uv.write_bytes(b"fixture uv - never executed")
        source = self.layout.source_root / "tiny"
        source.mkdir(parents=True)
        (source / "train.py").write_text("print('fixture - never executed')\n", encoding="utf-8")
        lock = {"schema_version": 1, "engine_id": engine, "platform": "windows-x86_64", "recipe_sha256": recipe(engine)["recipe_sha256"], "python": {"version": recipe(engine)["python"], "executable_relative": "python.exe", **python_file, "files": {"python.exe": python_file}, "archive": self.asset(python_archive)}, "uv": self.asset(uv), "wheels": wheels, "source": {"entry": "train.py", "trainer_relative": "tiny", "files": {"train.py": {"bytes": (source / "train.py").stat().st_size, "sha256": sha_file(source / "train.py")}}}}
        lockpath = root / "tiny.lock.json"
        atomic_json(lockpath, lock)
        self.request.update(lock_path=str(lockpath), lock_sha256=sha_file(lockpath))

    def asset(self, path):
        result = {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path), "url": "embedded:" + path.name}
        self.assets[result["sha256"]] = path.read_bytes()
        return result

    def materialize(self, assets):
        for item in assets:
            path = self.root / "cache/engine-assets" / item["sha256"] / item["filename"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.assets[item["sha256"]])

    def simulated_uv(self, command, layout, operation, timeout=1800):
        if "venv" in command:
            layout.python.parent.mkdir(parents=True)
            layout.python.write_bytes(b"fixture environment interpreter - never executed")
            (layout.environment_root / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
            return
        site = control._site_root(layout.environment_root)
        site.mkdir(parents=True, exist_ok=True)
        for path in command:
            if not str(path).endswith(".whl"):
                continue
            with zipfile.ZipFile(path) as archive:
                entries, record = [], ""
                for name in archive.namelist():
                    target = site / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
                    entries.append(name + ",,\n")
                    if name.endswith(".dist-info/RECORD"):
                        record = name
                (site / record).write_text("".join(entries), encoding="utf-8")

    def apply(self, planned, invasive=False):
        original = control._run
        def run(*args, **kwargs):
            self.simulated_uv(*args, **kwargs)
            if invasive:
                state = control._state(self.layout)
                target = RuntimeLayout(self.root, "fixture-v1", self.layout.engine_id, state["instance_id"])
                (control._site_root(target.environment_root) / "fixture_beta.py").write_text("unexpected change\n", encoding="utf-8")
        control._run = run
        try:
            return control.repair_apply({**self.request, "plan": planned, "plan_sha256": planned["plan_sha256"]})
        finally:
            control._run = original

    def exercise(self, guard_case=False):
        plan = control.plan(self.request, installing=True)
        self.materialize(plan["assets"])
        installed = self.apply(plan)
        state = installed["state"]
        before = control.inspect_readonly(self.request)
        target = RuntimeLayout(self.root, "fixture-v1", self.layout.engine_id, state["instance_id"])
        site = control._site_root(target.environment_root)
        beta_sha = sha_file(site / "fixture_beta.py")
        (site / "fixture_alpha.py").write_text("damage\n", encoding="utf-8")
        damaged = control.inspect_readonly(self.request)
        repair_plan = control.plan(self.request)
        if repair_plan["packages"] != ["fixture_alpha"]:
            raise ControlError("fixture_target", "微型夹具精准包范围不符")
        repaired = self.apply(repair_plan)
        report = control.inspect_readonly(self.request)
        if before["installation"] != "ready" or damaged["installation"] != "damaged" or report["installation"] != "ready" or repaired["state"]["generation"] != 2 or sha_file(site / "fixture_beta.py") != beta_sha:
            raise ControlError("fixture_assertion", "微型夹具安装、修复或非目标保护失败")
        result = {"engine_id": self.layout.engine_id, "status": "pass", "install": installed["status"], "damaged": damaged["installation"], "repair_packages": repair_plan["packages"], "generation": 2, "installation": report["installation"], "beta_unchanged": True}
        if guard_case:
            (site / "fixture_alpha.py").write_text("damage again\n", encoding="utf-8")
            plan = control.plan(self.request)
            try:
                self.apply(plan, invasive=True)
            except ControlError as error:
                dirty = control._state(self.layout)
                if error.code != "untargeted_file_changed" or not dirty["dirty"]:
                    raise
                result["untargeted_guard"] = {"status": "pass", "code": error.code, "dirty": True}
            else:
                raise ControlError("fixture_guard_missing", "非目标变更未被阻止")
        return result


def run(action, root):
    if action != "engine-fixture-v1" or not root.is_absolute() or root.parent == root:
        raise ControlError("fixture_contract", "只接受固定 engine-fixture-v1 动作和独立绝对根")
    root = Path(os.path.abspath(root))
    guard(root, root.parent)
    if root.exists() or not root.parent.is_dir():
        raise ControlError("fixture_root_exists", "微型夹具根必须为已有父目录下尚不存在的新目录")
    root.mkdir()
    start = time.monotonic()
    results = [TinyFixture(root / engine, engine).exercise() for engine in ENGINES]
    guard_result = TinyFixture(root / "untargeted-guard", "kohya").exercise(guard_case=True)["untargeted_guard"]
    value = {"action": action, "status": "pass", "root": str(root), "simulation": True, "simulation_scope": "uv command execution replaced by fixed tiny two-package writer; real control/archive/hash/state/transaction functions", "engines": results, "untargeted_guard": guard_result, "elapsed_seconds": round(time.monotonic() - start, 3), "network_bytes": 0, "engine_installation": "skip + CR-004", "real_imports": "skip + CR-004", "gpu": "skip + CR-004", "training": "skip + CR-004"}
    atomic_json(root / "fixture-result.json", value)
    return value


def main():
    try:
        if len(sys.argv) == 1:
            raw = sys.stdin.buffer.readline(65537)
            if len(raw) > 65536:
                raise ControlError("fixture_request_limit", "微型夹具请求超过64KiB")
            request = json.loads(raw)
            if not isinstance(request, dict) or set(request) != {"schema_version", "action", "root"} or request.get("schema_version") != 1:
                raise ControlError("fixture_protocol", "微型夹具只接受固定协议字段")
            action, root = request["action"], Path(request["root"])
        else:
            parser = argparse.ArgumentParser()
            parser.add_argument("--action", choices=["engine-fixture-v1"], required=True)
            parser.add_argument("--root", type=Path, required=True)
            args = parser.parse_args()
            action, root = args.action, args.root
        result = {"schema_version": 1, "ok": True, "result": run(action, root)}
        status = 0
    except Exception as error:
        result = {"schema_version": 1, "ok": False, "simulation": True, "error": {"code": getattr(error, "code", "fixture_error"), "message": str(error)}}
        status = 1
    print(json.dumps(result, ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
