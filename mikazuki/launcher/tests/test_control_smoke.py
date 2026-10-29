from __future__ import annotations

import hashlib
import asyncio
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mikazuki.launcher import control
from mikazuki.launcher.catalog import wheels_from_pylock
from mikazuki.launcher.recipes import ENGINES, recipe
from mikazuki.launcher.runtime import ControlError, RuntimeLayout, atomic_json, relative, sha_file, workspace_lease
from mikazuki.launcher.routes import create_router


class EngineFixture:
    """替代系统调用的微型两包环境；归档/哈希/状态/事务均运行真实代码。"""

    def __init__(self, root: Path, engine="kohya"):
        self.root = root
        root.mkdir()
        (root / ".launcher-workspace").write_text("next-trainer-desktop-v1", encoding="utf-8")
        self.request = {"schema_version": 1, "root": str(root), "release_id": "fixture-v1", "engine_id": engine}
        self.layout = RuntimeLayout(root, "fixture-v1", engine)
        self.assets = {}
        self.wheels = []
        for name in ("fixture_alpha", "fixture_beta"):
            path = root / (name + "-1.0-py3-none-any.whl")
            with zipfile.ZipFile(path, "w") as stream:
                stream.writestr(name + ".py", "VALUE = 'original'\n")
                stream.writestr(name + "-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: " + name + "\nVersion: 1.0\n")
                stream.writestr(name + "-1.0.dist-info/RECORD", "")
            self.wheels.append({"name": name, "version": "1.0", **self.asset(path)})
        archive = root / "python-fixture.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("python.exe", b"fixture base interpreter")
        pydata = b"fixture base interpreter"
        pyfile = {"bytes": len(pydata), "sha256": hashlib.sha256(pydata).hexdigest()}
        uv = root / "uv.exe"
        uv.write_bytes(b"fixture uv")
        source_root = self.layout.source_root / "vendor" / "fixture"
        source_root.mkdir(parents=True)
        (source_root / "train.py").write_text("print('fixture')\n", encoding="utf-8")
        self.lock = {"schema_version": 1, "engine_id": engine, "platform": "windows-x86_64", "recipe_sha256": recipe(engine)["recipe_sha256"], "python": {"version": recipe(engine)["python"], "executable_relative": "python.exe", **pyfile, "files": {"python.exe": pyfile}, "archive": self.asset(archive)}, "uv": self.asset(uv), "wheels": self.wheels, "source": {"trainer_relative": "vendor/fixture", "entry": "train.py", "files": {"train.py": {"bytes": (source_root / "train.py").stat().st_size, "sha256": sha_file(source_root / "train.py")}}}}
        lockpath = root / "fixed-engine-lock.json"
        atomic_json(lockpath, self.lock)
        self.request.update(lock_path=str(lockpath), lock_sha256=sha_file(lockpath))

    def asset(self, path):
        descriptor = {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path), "url": "https://example.invalid/" + path.name}
        self.assets[descriptor["sha256"]] = path.read_bytes()
        return descriptor

    def materialize(self, assets):
        for item in assets:
            path = self.root / "cache" / "engine-assets" / item["sha256"] / item["filename"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.assets[item["sha256"]])

    def run(self, command, layout, operation, timeout=1800):
        if "venv" in command:
            layout.python.parent.mkdir(parents=True)
            layout.python.write_bytes(b"fixture environment interpreter")
            (layout.environment_root / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
            return
        site = control._site_root(layout.environment_root)
        site.mkdir(parents=True, exist_ok=True)
        for path in command:
            if not str(path).endswith(".whl"):
                continue
            with zipfile.ZipFile(path) as stream:
                entries = []
                info_dir = ""
                for name in stream.namelist():
                    destination = site / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(stream.read(name))
                    entries.append(name + ",,\n")
                    if name.endswith(".dist-info/RECORD"):
                        info_dir = name
                (site / info_dir).write_text("".join(entries), encoding="utf-8")

    def install(self):
        planned = control.plan(self.request, installing=True)
        self.materialize(planned["missing_assets"])
        with patch.object(control, "_run", self.run):
            return control.repair_apply({**self.request, "plan": planned, "plan_sha256": planned["plan_sha256"]})


class ControlSmoke(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nt-engine-smoke-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_four_engines_install_inspect_targeted_repair(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                fixture = EngineFixture(self.root / engine, engine)
                installed = fixture.install()
                first = installed["state"]
                self.assertEqual(control.inspect_readonly(fixture.request)["installation"], "ready")
                target = RuntimeLayout(fixture.root, "fixture-v1", engine, first["instance_id"])
                package = control._site_root(target.environment_root) / "fixture_alpha.py"
                package.write_text("damaged", encoding="utf-8")
                report = control.inspect_readonly(fixture.request)
                self.assertEqual(report["installation"], "damaged")
                plan = control.plan(fixture.request)
                self.assertEqual(plan["packages"], ["fixture_alpha"])
                with patch.object(control, "_run", fixture.run):
                    repaired = control.repair_apply({**fixture.request, "plan": plan, "plan_sha256": plan["plan_sha256"]})
                self.assertEqual(repaired["state"]["generation"], 2)
                self.assertTrue((target.state_root / first["receipt_relative"]).is_file())
                self.assertEqual(control.inspect_readonly(fixture.request)["installation"], "ready")

    def test_rebuild_keeps_old_source_and_receipt(self):
        fixture = EngineFixture(self.root / "rebuild")
        old = fixture.install()["state"]
        target = RuntimeLayout(fixture.root, "fixture-v1", "kohya", old["instance_id"])
        prior_source = (target.engine_source_root / "train.py").read_bytes()
        plan = control.plan({**fixture.request, "rebuild": True}, installing=True)
        with patch.object(control, "_run", fixture.run):
            changed = control.repair_apply({**fixture.request, "plan": plan, "plan_sha256": plan["plan_sha256"]})
        self.assertNotEqual(changed["state"]["instance_id"], old["instance_id"])
        self.assertEqual((target.engine_source_root / "train.py").read_bytes(), prior_source)
        self.assertTrue((target.state_root / old["receipt_relative"]).is_file())

    def test_failed_repair_restores_preexisting_damage_and_allows_retry(self):
        fixture = EngineFixture(self.root / "recover")
        state = fixture.install()["state"]
        target = RuntimeLayout(fixture.root, "fixture-v1", "kohya", state["instance_id"])
        package = control._site_root(target.environment_root) / "fixture_alpha.py"
        package.write_text("damage before repair", encoding="utf-8")
        plan = control.plan(fixture.request)
        def failing(*args, **kwargs):
            fixture.run(*args, **kwargs)
            raise ControlError("fixture_failure", "failure after offline install")
        with patch.object(control, "_run", failing), self.assertRaises(ControlError):
            control.repair_apply({**fixture.request, "plan": plan, "plan_sha256": plan["plan_sha256"]})
        self.assertTrue(control.inspect_readonly(fixture.request)["state"]["dirty"])
        recovered = control.recover(fixture.request)
        self.assertEqual(recovered["status"], "restored")
        self.assertEqual(recovered["installation"], "damaged")
        self.assertEqual(package.read_text(encoding="utf-8"), "damage before repair")
        retry = control.plan(fixture.request)
        with patch.object(control, "_run", fixture.run):
            control.repair_apply({**fixture.request, "plan": retry, "plan_sha256": retry["plan_sha256"]})
        self.assertEqual(control.inspect_readonly(fixture.request)["installation"], "ready")

    def test_untargeted_modification_remains_dirty(self):
        fixture = EngineFixture(self.root / "untouched")
        state = fixture.install()["state"]
        target = RuntimeLayout(fixture.root, "fixture-v1", "kohya", state["instance_id"])
        site = control._site_root(target.environment_root)
        (site / "fixture_alpha.py").write_text("damage", encoding="utf-8")
        plan = control.plan(fixture.request)
        def invasive(*args, **kwargs):
            fixture.run(*args, **kwargs)
            (site / "fixture_beta.py").write_text("unauthorized", encoding="utf-8")
        with patch.object(control, "_run", invasive), self.assertRaisesRegex(ControlError, "非目标"):
            control.repair_apply({**fixture.request, "plan": plan, "plan_sha256": plan["plan_sha256"]})
        self.assertTrue(control.inspect_readonly(fixture.request)["state"]["dirty"])

    def test_worker_isolated_start_and_readonly_missing(self):
        worker = Path(control.__file__).with_name("worker.py")
        completed = subprocess.run([sys.executable, "-I", "-S", str(worker)], input='{"schema_version":1,"action":"capabilities"}\n', capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(json.loads(completed.stdout)["result"]["engines"]), 4)
        root = self.root / "missing"
        result = control.inspect_readonly({"root": str(root), "release_id": "fixture-v1", "engine_id": "kohya"})
        self.assertEqual(result["installation"], "missing")
        self.assertFalse(root.exists())
        for path in ("a//b", "../bad", "C:/outside", "x\\bad"):
            with self.assertRaises(ControlError):
                relative(path)

    def test_cross_process_lease_is_exclusive(self):
        fixture = EngineFixture(self.root / "lease")
        code = "from pathlib import Path; from mikazuki.launcher.runtime import ControlError,RuntimeLayout,workspace_lease; x=RuntimeLayout(Path(" + repr(str(fixture.root)) + "),'fixture-v1','kohya');\ntry:\n with workspace_lease(x): print('unexpected')\nexcept ControlError as error:\n print(error.code)\n raise SystemExit(5)"
        with workspace_lease(fixture.layout):
            completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        self.assertEqual(completed.returncode, 5, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "workspace_busy")

    def test_failed_first_install_can_explicitly_rebuild(self):
        fixture = EngineFixture(self.root / "failed-first")
        plan = control.plan(fixture.request, installing=True)
        fixture.materialize(plan["assets"])
        with patch.object(control, "_run", side_effect=ControlError("fixture_failure", "failed before venv")), self.assertRaises(ControlError):
            control.repair_apply({**fixture.request, "plan": plan, "plan_sha256": plan["plan_sha256"]})
        self.assertEqual(control.recover(fixture.request)["status"], "requires_rebuild")
        rebuild = control.plan({**fixture.request, "rebuild": True}, installing=True)
        with patch.object(control, "_run", fixture.run):
            ready = control.repair_apply({**fixture.request, "plan": rebuild, "plan_sha256": rebuild["plan_sha256"]})
        self.assertEqual(ready["status"], "succeeded")
        self.assertNotEqual(ready["state"]["instance_id"], plan["instance_id"])

    def test_web_adapter_uses_trusted_context_and_same_core(self):
        from fastapi import FastAPI
        import httpx
        fixture = EngineFixture(self.root / "web")
        fixture.install()
        context = {"schema_version": 1, "root": str(fixture.root), "release_id": "fixture-v1", "profile_id": "default", "engine_catalog": {"kohya": {"lock_path": fixture.request["lock_path"], "sha256": fixture.request["lock_sha256"]}}}
        app = FastAPI()
        app.include_router(create_router(lambda: context, allow_mutations=True), prefix="/api")
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
                response = await client.get("/api/launcher/engines/kohya/inspect")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["installation"], "ready")
                response = await client.post("/api/launcher/engines/kohya/plan", json={"lock_path": "C:/outside"})
                self.assertEqual(response.status_code, 422)
                response = await client.post("/api/launcher/engines/kohya/plan", json={})
                self.assertEqual(response.status_code, 200)
                digest = response.json()["plan_sha256"]
                response = await client.post("/api/launcher/engines/kohya/apply", json={"plan_sha256": digest})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "no_changes")
        asyncio.run(run())

    def test_catalog_reports_exact_wheel_gap(self):
        path = self.root / "pylock.fixture.toml"
        path.write_text('lock-version="1.0"\n[[packages]]\nname="small"\nversion="1"\nwheels=[{url="https://example.invalid/small-1-py3-none-any.whl",size=11,hashes={sha256="' + "a" * 64 + '"}}]\n[[packages]]\nname="source-only"\nversion="2"\nsdist={url="https://example.invalid/source.tar.gz",size=12,hashes={sha256="' + "b" * 64 + '"}}\n', encoding="utf-8")
        wheels, gaps = wheels_from_pylock(path, "cp310")
        self.assertEqual(wheels[0]["name"], "small")
        self.assertEqual(gaps[0]["name"], "source-only")
        self.assertEqual(gaps[0]["version"], "2")

    def test_existing_training_settings_select_managed_instances(self):
        from mikazuki.launcher.bindings import active_layout, managed_status, reject_legacy_mutation
        for engine, package in (("kohya", "kohya"), ("anima-fast", "anima_fast"), ("ai-toolkit", "ai_toolkit"), ("diffsynth", "diffsynth")):
            with self.subTest(engine=engine):
                fixture = EngineFixture(self.root / ("binding-" + engine), engine)
                state = fixture.install()["state"]
                context = {"schema_version": 1, "root": str(fixture.root), "release_id": "fixture-v1", "profile_id": "reviewed-profile", "engine_catalog": {engine: {"lock_path": fixture.request["lock_path"], "sha256": fixture.request["lock_sha256"]}}}
                with patch.dict(os.environ, {"NEXT_TRAINER_LAUNCHER_CONTEXT": json.dumps(context)}):
                    layout = active_layout(engine)
                    self.assertEqual(layout.instance_id, state["instance_id"])
                    self.assertEqual(layout.profile_id, "reviewed-profile")
                    settings = importlib.import_module("mikazuki.engines." + package + ".settings")
                    runtime = settings.discover_runtime() if engine in {"anima-fast", "ai-toolkit"} else settings.runtime()
                    self.assertEqual(runtime.python, layout.python)
                    self.assertEqual(managed_status(engine)["state"], "ready")
                    if engine == "kohya":
                        self.assertEqual(settings.main_env_python_candidates(Path.cwd()), [])
                    with self.assertRaises(ValueError):
                        reject_legacy_mutation()


if __name__ == "__main__":
    unittest.main()
