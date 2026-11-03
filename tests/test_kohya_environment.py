from pathlib import Path


def test_kohya_training_environment_includes_scipy():
    from mikazuki.engines.kohya.environment import TRAINING_DEPS

    assert any(item == "scipy" or item.startswith("scipy=") for item in TRAINING_DEPS)


def test_kohya_training_environment_includes_moss_compatible_stack():
    from mikazuki.engines.kohya.environment import TRAINING_DEPS

    assert "accelerate==1.15.0" in TRAINING_DEPS
    assert "transformers==5.17.0" in TRAINING_DEPS
    assert "diffusers[torch]==0.40.0" in TRAINING_DEPS
    assert "safetensors==0.8.0" in TRAINING_DEPS
    assert "huggingface-hub==1.32.0" in TRAINING_DEPS
    assert "tokenizers==0.23.1" in TRAINING_DEPS


def test_kohya_install_plan_installs_scipy(tmp_path):
    from mikazuki.download_sources import DownloadSources
    from mikazuki.engines.kohya.environment import install_commands
    from mikazuki.engines.kohya.settings import Runtime

    commands = install_commands(Runtime(Path(tmp_path)), DownloadSources())
    assert any("scipy" in command for command in commands)


def test_kohya_audit_checks_scipy():
    from mikazuki.engines.kohya.environment import audit_python

    source = audit_python.__code__.co_consts
    assert any("scipy" in value for value in source if isinstance(value, str))


def test_main_requirements_include_uv_for_managed_engine_installs():
    root = Path(__file__).resolve().parents[1]
    reqs = [
        line.strip().split("#", 1)[0].strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8-sig").splitlines()
    ]
    assert any(item == "uv" or item.startswith(("uv=", "uv>", "uv<")) for item in reqs if item)


def test_kohya_audit_reports_transformers_and_tokenizers_versions():
    from mikazuki.engines.kohya.environment import audit_python

    source = audit_python.__code__.co_consts
    assert any("transformers" in value and "tokenizers" in value for value in source if isinstance(value, str))


def _satisfying_versions():
    from packaging.utils import canonicalize_name
    from mikazuki.engines.kohya.environment import pinned_requirements

    versions = {}
    for req in pinned_requirements():
        if not req.specifier:
            versions[canonicalize_name(req.name)] = "1.0"
            continue
        for spec in req.specifier:
            if spec.operator == "==":
                versions[canonicalize_name(req.name)] = spec.version
                break
            if spec.operator in (">=", ">"):
                versions[canonicalize_name(req.name)] = spec.version
                break
            if spec.operator in ("<", "<="):
                versions[canonicalize_name(req.name)] = "1.0"
                break
    return versions


def test_pinned_requirements_skip_foreign_platform_markers():
    import sys
    from mikazuki.engines.kohya.environment import pinned_requirements

    names = {req.name for req in pinned_requirements()}
    if not sys.platform == "win32":
        assert "triton-windows" not in names


def test_compute_drift_empty_when_all_pins_satisfied():
    from mikazuki.engines.kohya.environment import compute_drift

    assert compute_drift(_satisfying_versions()) == []


def test_compute_drift_flags_mismatch_and_missing():
    from packaging.utils import canonicalize_name
    from mikazuki.engines.kohya.environment import compute_drift, pinned_requirements

    versions = _satisfying_versions()
    versions[canonicalize_name("transformers")] = "4.51.3"
    versions.pop(canonicalize_name("lycoris-lora"), None)

    drift = compute_drift(versions)

    by_name = {d["name"]: d for d in drift}
    assert by_name["transformers"]["installed"] == "4.51.3"
    assert by_name["transformers"]["spec"] == "==5.17.0"
    assert by_name["lycoris-lora"]["installed"] is None
    assert "accelerate" not in by_name


def test_compute_drift_accepts_torch_local_version():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from mikazuki.engines.kohya.environment import compute_drift, _torch_requirements

    versions = _satisfying_versions()
    local = {}
    for spec in _torch_requirements():
        requirement = Requirement(spec)
        exact = next(item.version for item in requirement.specifier if item.operator == "==")
        local[canonicalize_name(requirement.name)] = f"{exact}+cu130"
    versions.update(local)

    drift = compute_drift(versions)

    assert not any(canonicalize_name(d["name"]) in local for d in drift)


def test_upgrade_commands_split_torch_index_and_skip_when_empty(tmp_path):
    from mikazuki.download_sources import DownloadSources
    from mikazuki.engines.kohya.environment import upgrade_commands, main_env_upgrade_commands
    from mikazuki.engines.kohya.settings import Runtime

    rt = Runtime(tmp_path)
    sources = DownloadSources()
    assert upgrade_commands(rt, sources, []) == []
    assert main_env_upgrade_commands(tmp_path / "python", sources, []) == []

    drift = [
        {"name": "transformers", "spec": "==5.17.0", "installed": "4.51.3"},
        {"name": "torch", "spec": "==2.13.0", "installed": "2.7.0"},
    ]
    commands = upgrade_commands(rt, sources, drift)
    assert len(commands) == 2
    torch_cmd, deps_cmd = commands
    assert "torch==2.13.0" in torch_cmd and "transformers==5.17.0" not in torch_cmd
    assert "transformers==5.17.0" in deps_cmd and "torch==2.13.0" not in deps_cmd

    main_cmds = main_env_upgrade_commands(tmp_path / "python", sources, drift)
    assert len(main_cmds) == 1
    assert main_cmds[0][1:3] == ["-m", "pip"]
    assert "transformers==5.17.0" in main_cmds[0] and "torch==2.13.0" in main_cmds[0]


def test_compute_drift_normalizes_installed_package_names():
    from mikazuki.engines.kohya.environment import compute_drift

    versions = _satisfying_versions()
    versions["huggingface_hub"] = versions.pop("huggingface-hub")
    versions["lycoris_lora"] = versions.pop("lycoris-lora")

    drift = compute_drift(versions)

    assert not any(d["name"] in {"huggingface-hub", "lycoris-lora"} for d in drift)


def test_moss_stack_error_gates_transformers_major():
    from mikazuki.engines.kohya.environment import moss_stack_error

    assert moss_stack_error({"transformers": "5.17.0"}) is None
    assert moss_stack_error({"transformers": "5.0.0"}) is None
    assert "transformers 5.x" in moss_stack_error({"transformers": "4.51.3"})
    assert "transformers 5.x" in moss_stack_error({"transformers": "garbage"})
    assert "transformers 5.x" in moss_stack_error({})
    assert "transformers 5.x" in moss_stack_error(None)


def test_moss_stack_error_prefers_qwen35_capability_flag():
    from mikazuki.engines.kohya.environment import moss_stack_error

    assert moss_stack_error({"transformers": "4.51.3", "qwen35": True}) is None
    assert "transformers 5.x" in moss_stack_error({"transformers": "5.17.0", "qwen35": False})
