"""MOSS integration contracts. Sparse synthetic headers, mocked process boundary.

No downloaded tensors, training, model imports or training-environment installs.
Set MOSS_UPSTREAM_SOURCE to the pinned checkout to exercise its real parser too.
"""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from mikazuki.engines.moss.adapter import adapt_config, argv_for, dump_config
from mikazuki.engines.moss.inputs import (
    cache_identity, source_pairs, tensor_header, text_encoder_keys,
    transformer_shapes, vae_sentinel_shapes, validate_cache, write_cache_identity,
)
from mikazuki.engines.moss.launcher import build_train_spec, pipeline_commands
from mikazuki.engines.moss.manifest import UPSTREAM
from mikazuki.engines.moss.preflight import check_inputs, run_preflight
from mikazuki.engines.moss.settings import Runtime

FIXTURES = Path(__file__).parent / "fixtures" / "moss"


def sparse_tensors(path, shapes, *, dtype="BF16", metadata=None):
    """Only headers occupy disk; sparse holes stand in for nonexistent tensors."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header, offset = {}, 0
    for key, shape in shapes.items():
        end = offset + math.prod(shape) * {"BF16": 2, "F16": 2, "F32": 4, "I8": 1}[dtype]
        header[key] = {"shape": shape, "dtype": dtype, "data_offsets": [offset, end]}
        offset = end
    if metadata is not None:
        header["__metadata__"] = metadata
    raw = json.dumps(header).encode()
    with path.open("wb") as stream:
        stream.write(struct.pack("<Q", len(raw)) + raw)
        stream.truncate(8 + len(raw) + offset)


@pytest.fixture
def configured(tmp_path):
    rt = Runtime(tmp_path)
    root = tmp_path / "models" / "moss_image" / "MOSS-Image-Base"
    for component in ("transformer", "text_encoder", "vae"):
        (root / component).mkdir(parents=True)
        (root / component / "config.json").write_text((FIXTURES / f"{component}_config.json").read_text())
    sparse_tensors(root / "transformer/diffusion_pytorch_model.safetensors", transformer_shapes())
    te = {key: [1] for key in text_encoder_keys()}
    te["language_model.embed_tokens.weight"] = [248320, 4096]
    sparse_tensors(root / "text_encoder/model.safetensors", te)
    sparse_tensors(root / "vae/diffusion_pytorch_model.safetensors", vae_sentinel_shapes(), dtype="F32")
    (root / "tokenizer").mkdir()
    (root / "tokenizer/tokenizer.json").write_text("{}")
    (root / "tokenizer/tokenizer_config.json").write_text('{"chat_template":"{{ messages }}"}')
    dataset = tmp_path / "images"
    dataset.mkdir()
    Image.new("RGB", (32, 48), "blue").save(dataset / "sample.png")
    (dataset / "sample.txt").write_text("中文 caption", encoding="utf-8")
    config = {"model_train_type": "moss-image-anima-lora", "model_dir": "models/moss_image", "src": "images",
              "output_dir": "output", "output_name": "moss_test", "epochs": 2, "rank": 8, "lr": 0.0002}
    return rt, config


def make_cache(adapted):
    cache = Path(adapted.train["cache"])
    for stem, (_, caption_hash) in source_pairs(adapted.cache["src"]).items():
        sparse_tensors(cache / f"{stem}_32x48.moss_latent.safetensors", {"latent": [128, 3, 2]}, dtype="F32")
        sparse_tensors(cache / f"{stem}.moss_te.safetensors", {"embeds": [12, 4096]}, metadata={
            "caption_sha256": caption_hash, "max_text_tokens": str(adapted.cache["max_text_tokens"]),
        })
    write_cache_identity(adapted)


def test_official_metadata_keys_match_pinned_source_contract():
    assert set(json.loads((FIXTURES / "transformer_keys.json").read_text())) == set(transformer_shapes())
    official = json.loads((FIXTURES / "text_encoder_keys.json").read_text())
    assert {key for key in official if key.startswith("language_model.")} == text_encoder_keys()


def test_native_values_paths_and_offline_launch(configured, monkeypatch):
    rt, config = configured
    adapted = adapt_config({**config, "compile": False, "grad_checkpointing": False, "alpha": 4, "blocks_to_swap": 40}, rt)
    facts = check_inputs(adapted)
    assert facts["model_format"] == "native-diffusers" and facts["total_steps"] == 2
    assert adapted.train["rank"] == 8 and adapted.train["lr"] == 0.0002
    assert adapted.train["alpha"] == 4 and adapted.train["blocks_to_swap"] == 40
    assert adapted.train["output"] == str(rt.project_root / "output/moss_test.safetensors")
    commands = pipeline_commands(rt, adapted)
    assert commands[0][:8] == [str(rt.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.cache"]
    assert commands[1][:8] == [str(rt.python), "-E", "-s", "-u", "-X", "utf8", "-m", "scripts.moss.train"]
    assert "--no-compile" in commands[1] and "--no-grad_checkpointing" in commands[1]
    assert "--src" in commands[0] and "--resolution" in commands[0]
    assert "--src" not in commands[1] and "--output_dir" not in commands[1]
    monkeypatch.setenv("PYTHONPATH", "/host/packages")
    monkeypatch.setenv("PYTHONHOME", "/host/python")
    spec = build_train_spec(rt, dump_config(adapted, rt.project_root / "autosave", "case"), ["2"])
    assert spec.cwd == rt.source and spec.env["CUDA_VISIBLE_DEVICES"] == "2"
    assert spec.env["HF_HUB_OFFLINE"] == "1" and spec.env["TRANSFORMERS_OFFLINE"] == "1"
    assert "PYTHONPATH" not in spec.env and "PYTHONHOME" not in spec.env


@pytest.mark.parametrize("field,value", [
    ("rank", 0), ("rank", 1.5), ("epochs", -1), ("max_steps", -1), ("lr", 0),
    ("lr", float("nan")), ("lr", float("inf")), ("alpha", 0), ("resolution", 15),
    ("max_text_tokens", 4097), ("log_every", 0), ("warmup_ratio", 1.1),
    ("caption_dropout", -0.1), ("sigma_cutoff", 0), ("sigma_uniform", 1.1),
    ("sigma_s", 0), ("blocks_to_swap", 41), ("model", "anima"), ("lora_dtype", "fp8"),
    ("vae_dtype", "fp16"), ("compile", "yes"), ("targets", "["), ("targets", "no_matching_layer"),
    ("output_name", "../escape"), ("train_batch_size", 2), ("network_args", ["foo=bar"]),
    ("optimizer_type", "AdamW"), ("resume", "/prior/state"), ("quantization", "int8"),
])
def test_invalid_inputs_are_rejected(configured, field, value):
    rt, config = configured
    result = run_preflight({**config, field: value}, rt)
    assert not result["ok"] and result["errors"]


def test_duration_and_single_gpu_contract(configured):
    rt, config = configured
    with pytest.raises(ValueError, match="epochs/max_steps"):
        adapt_config({**config, "epochs": 0, "max_steps": 0}, rt)
    adapted = adapt_config({**config, "epochs": 0, "max_steps": 7}, rt)
    assert check_inputs(adapted)["total_steps"] == 7
    assert check_inputs(adapt_config({**config, "max_steps": 1}, rt))["total_steps"] == 1
    with pytest.raises(ValueError, match="GPU"):
        build_train_spec(rt, "config.json", ["0", "1"])


def test_missing_model_component_and_wrong_text_prefix(configured):
    rt, config = configured
    te = rt.project_root / "models/moss_image/MOSS-Image-Base/text_encoder/model.safetensors"
    te.unlink()
    result = run_preflight(config, rt)
    assert not result["ok"] and "text_encoder" in result["errors"][0]
    sparse_tensors(te, {"model.language_model.embed_tokens.weight": [248320, 4096]})
    result = run_preflight(config, rt)
    assert not result["ok"] and "language_model" in result["errors"][0]


def test_sft_uses_base_auxiliary_components(configured):
    import shutil
    rt, config = configured
    source = rt.project_root / "models/moss_image/MOSS-Image-Base/transformer"
    target = source.parent.parent / "MOSS-Image-SFT/transformer"
    target.mkdir(parents=True)
    (target / "config.json").write_text((source / "config.json").read_text())
    # Hardlink the sparse synthetic file instead of copying its holes.
    os.link(source / "diffusion_pytorch_model.safetensors", target / "diffusion_pytorch_model.safetensors")
    assert run_preflight({**config, "model": "sft"}, rt)["ok"]
    shutil.rmtree(source.parent / "tokenizer")
    assert not run_preflight({**config, "model": "sft"}, rt)["ok"]


def test_wrong_dit_keys_quantization_and_shards_fail(configured):
    rt, config = configured
    folder = rt.project_root / "models/moss_image/MOSS-Image-Base/transformer"
    path = folder / "diffusion_pytorch_model.safetensors"
    sparse_tensors(path, {"wrong.weight": [1]})
    assert "keys" not in run_preflight(config, rt).get("facts", {})
    assert not run_preflight(config, rt)["ok"]
    sparse_tensors(path, transformer_shapes(), dtype="I8")
    assert "quantized" in run_preflight(config, rt)["errors"][0]
    path.unlink()
    (folder / "diffusion_pytorch_model.safetensors.index.json").write_text(json.dumps({"weight_map": {"key": "absent.safetensors"}}))
    assert "shard" in run_preflight(config, rt)["errors"][0]


def test_dataset_caption_validation_and_upstream_stem_collision(configured):
    rt, config = configured
    src = rt.project_root / "images"
    (src / "sample.txt").unlink()
    assert "caption" in run_preflight(config, rt)["errors"][0]
    (src / "sample.txt").write_text("caption")
    for relative in ("x/image", "y/image", "x__image"):
        path = src / f"{relative}.png"
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (16, 16)).save(path)
        path.with_suffix(".txt").write_text("caption")
    with pytest.raises(ValueError, match="colliding"):
        source_pairs(src)


def test_cache_provenance_orphans_and_shapes(configured):
    rt, config = configured
    adapted = adapt_config(config, rt)
    make_cache(adapted)
    assert validate_cache(adapted, completed=True)["cache_pairs"] == 1
    identity = Path(adapted.train["cache"]) / ".next-moss-cache.json"
    identity.unlink()
    with pytest.raises(ValueError, match="provenance"):
        validate_cache(adapted)
    write_cache_identity(adapted)
    assert json.loads(identity.read_text()) == cache_identity(adapted)
    cache = identity.parent
    sparse_tensors(cache / "removed_32x48.moss_latent.safetensors", {"latent": [128, 3, 2]}, dtype="F32")
    with pytest.raises(ValueError, match="orphan"):
        validate_cache(adapted)
    (cache / "removed_32x48.moss_latent.safetensors").unlink()
    sparse_tensors(cache / "sample.moss_te.safetensors", {"embeds": [12, 8]})
    with pytest.raises(ValueError, match="embedding shape"):
        validate_cache(adapted, completed=True)


def test_cached_only_mode_and_output_collision(configured):
    rt, config = configured
    original = adapt_config(config, rt)
    make_cache(original)
    cached = adapt_config({**config, "run_preprocess": False, "cache_dir": original.train["cache"]}, rt)
    assert len(pipeline_commands(rt, cached)) == 1
    assert check_inputs(cached)["total_steps"] == 2
    output = Path(cached.train["output"])
    output.parent.mkdir()
    output.touch()
    with pytest.raises(ValueError, match="output exists"):
        check_inputs(cached)


def test_import_export_roundtrip_and_cross_family_redirect(configured):
    from mikazuki.utils.config_import import validate_config_import
    from mikazuki.utils.config_export import normalize_config_for_export
    rt, config = configured
    exported, warnings = normalize_config_for_export(config, page_train_type="moss-image-anima-lora")
    result = validate_config_import("moss-image-anima-lora", exported)
    assert result["result"] == "ok" and not warnings
    assert result["config"]["rank"] == 8
    redirected = validate_config_import("sd3-lora", exported)
    assert redirected["result"] == "redirect"
    assert "moss-image" in json.dumps(redirected)
    assert adapt_config(result["config"], rt).train["rank"] == 8


@pytest.mark.parametrize("frontend_fixture", [False, True])
def test_api_preflight_dry_run_and_run_stop_at_task_boundary(configured, monkeypatch, frontend_fixture):
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    from mikazuki.engines.moss import routes, run
    from mikazuki.tasks import TaskStatus
    rt, config = configured
    if frontend_fixture:
        # The frontend test asserts this exact payload is produced by the
        # real schema -> serializeModel -> buildTrainingConfig chain.
        config = json.loads((FIXTURES / "form-submission.json").read_text())
    monkeypatch.chdir(rt.project_root)
    monkeypatch.setattr(run, "runtime", lambda: rt)
    monkeypatch.setattr(routes, "runtime", lambda: rt)
    monkeypatch.setattr(run, "check_runtime", lambda _rt: None)
    monkeypatch.setattr(routes, "check_runtime", lambda _rt: None)
    monkeypatch.setattr(run, "assert_idle", lambda **_kwargs: None)
    captured, submitted = [], []
    def create(command, env, **kwargs):
        captured.append({"command": command, "env": env, **kwargs})
        return SimpleNamespace(task_id="mock-moss-task", status=TaskStatus.CREATED)
    monkeypatch.setattr(run.tm, "create_task", create)
    monkeypatch.setattr(run.tm, "submit", submitted.append)
    client = TestClient(app)
    assert client.post("/api/engines/moss/preflight", json=config).json()["status"] == "success"
    dry = client.post("/api/engines/moss/dry-run", json=config).json()
    assert dry["status"] == "success" and not dry["data"]["training_started"]
    assert captured == [] and submitted == []
    response = client.post("/api/run", json={**config, "gpu_ids": ["1"]}).json()
    assert response["status"] == "success", response
    assert len(captured) == len(submitted) == 1
    assert captured[0]["metadata"]["backend"] == "moss"
    assert captured[0]["metadata"]["train_type"] == "moss-image-anima-lora"
    assert captured[0]["env"]["CUDA_VISIBLE_DEVICES"] == "1"
    saved = json.loads(Path(captured[0]["metadata"]["engine_config_path"]).read_text(encoding="utf-8"))
    assert saved == dry["data"]["config"]
    assert captured[0]["metadata"]["pipeline_commands"] == dry["data"]["commands"]
    assert saved["train"]["rank"] == 8 and saved["cache"]["src"] == str(rt.project_root / "images")
    failure = client.post("/api/run", json={**config, "rank": 0}).json()
    assert failure["status"] == "fail" and len(captured) == 1


@pytest.mark.parametrize("frontend_fixture", [False, True])
def test_actual_pinned_upstream_parser_without_ml_imports(configured, frontend_fixture):
    source = os.environ.get("MOSS_UPSTREAM_SOURCE")
    if not source:
        pytest.skip("Set MOSS_UPSTREAM_SOURCE to the pinned moss_lora checkout (no model/ML install needed)")
    source = Path(source)
    assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == UPSTREAM["commit"]
    rt, config = configured
    if frontend_fixture:
        config = json.loads((FIXTURES / "form-submission.json").read_text())
    adapted = adapt_config({**config, "epochs": 0, "max_steps": 3, "alpha": 12, "compile": False, "grad_checkpointing": False}, rt)
    program = '''
import json, sys, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
# Only the unrelated download catalog dependency is stubbed. The request
# dataclasses, argparse implementation and environment resolver are genuine.
catalog = types.ModuleType("library.downloads")
catalog.MOSS_DIR = "moss_image"
catalog.MOSS_VARIANT_DIRS = {"base": "MOSS-Image-Base", "sft": "MOSS-Image-SFT"}
catalog.default_moss_dir = lambda: Path("models/moss_image")
sys.modules["library.downloads"] = catalog
from library.moss.requests import CacheRequest, TrainRequest
arguments = json.load(sys.stdin)
cache = CacheRequest.from_argv(arguments["cache"])
train = TrainRequest.from_argv(arguments["train"])
assert CacheRequest.from_argv(cache.to_argv()) == cache
assert TrainRequest.from_argv(train.to_argv()) == train
assert not {"torch", "transformers", "diffusers", "numpy", "PIL", "safetensors"} & set(sys.modules)
print(json.dumps({"cache": vars(cache), "train": vars(train)}))
'''
    result = subprocess.run([sys.executable, "-c", program, str(source)],
                            input=json.dumps({"cache": argv_for(adapted.cache), "train": argv_for(adapted.train)}),
                            text=True, capture_output=True, check=True)
    parsed = json.loads(result.stdout)
    for group in ("cache", "train"):
        for key, value in getattr(adapted, group).items():
            assert parsed[group][key] == value, (group, key)
    assert parsed["train"]["rank"] == 8 and parsed["train"]["alpha"] == 12
    assert parsed["train"]["epochs"] == 0 and parsed["train"]["max_steps"] == 3
    assert parsed["train"]["compile"] is False and parsed["train"]["grad_checkpointing"] is False


def test_reserved_empty_stem_and_cache_only_identity(configured):
    rt, config = configured
    adapted = adapt_config(config, rt)
    make_cache(adapted)
    config.pop("src")
    cached = adapt_config({**config, "run_preprocess": False, "cache_dir": adapted.train["cache"]}, rt)
    assert validate_cache(cached, completed=True)["cache_pairs"] == 1
    identity = Path(adapted.train["cache"]) / ".next-moss-cache.json"
    data = json.loads(identity.read_text())
    data["model_dir"] = "/different/model"
    identity.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identity changed"):
        validate_cache(cached, completed=True)
    src = rt.project_root / "images"
    (src / "sample.png").rename(src / "_empty.png")
    (src / "sample.txt").rename(src / "_empty.txt")
    with pytest.raises(ValueError, match="reserved"):
        source_pairs(src)


@pytest.mark.parametrize("suffix", [".json", "_e1.safetensors", "_e25.safetensors"])
def test_all_upstream_output_artifacts_are_protected(configured, suffix):
    rt, config = configured
    adapted = adapt_config(config, rt)
    output = Path(adapted.train["output"])
    output.parent.mkdir()
    output.with_name(output.stem + suffix).touch()
    assert "output exists" in run_preflight(config, rt)["errors"][0]


def test_queued_output_namespace_is_reserved(configured, monkeypatch):
    from mikazuki.engines.moss.run import check_queued_outputs, tm
    from mikazuki.tasks import TaskStatus
    rt, config = configured
    adapted = adapt_config(config, rt)
    task = SimpleNamespace(status=TaskStatus.QUEUED, metadata={
        "backend": "moss", "output_dir": str(rt.project_root / "output"), "output_name": "moss_test",
    })
    monkeypatch.setattr(tm, "tasks", {"queued": task})
    with pytest.raises(ValueError, match="reserved"):
        check_queued_outputs(adapted)
    adapted.train["output"] = str(rt.project_root / "output/moss_test_e1.safetensors")
    with pytest.raises(ValueError, match="reserved"):
        check_queued_outputs(adapted)


def test_header_rejects_truncated_tensors(tmp_path):
    path = tmp_path / "broken.safetensors"
    sparse_tensors(path, {"embeds": [2, 4096]})
    with path.open("r+b") as stream:
        stream.truncate(path.stat().st_size - 1)
    with pytest.raises(ValueError, match="truncated"):
        tensor_header(path)


def test_moss_dataset_is_guarded_while_queued(tmp_path, monkeypatch):
    import toml
    from mikazuki.datasets import inuse
    root = tmp_path / "datasets"
    dataset = root / "moss-experiment"
    dataset.mkdir(parents=True)
    config_path = tmp_path / "moss.toml"
    config_path.write_text(toml.dumps({"model_train_type": "moss-image-anima-lora", "src": str(dataset)}))
    monkeypatch.setattr(inuse.tm, "dump", lambda: [{"status": "QUEUED", "metadata": {"config_path": str(config_path)}}])
    assert inuse.datasets_in_use(root) == {"moss-experiment"}


def test_progress_only_recognizes_training_lines():
    from mikazuki.engines.moss.progress import read_progress
    assert read_progress(["text 1/4 sample: 16 tokens", "latents 1/4 sample: 32x48"], {}) == {}
    result = read_progress(["  progress 3/8 epoch 1/2 loss 0.1234 eta 0:01:02"], {})
    assert result == {"step": 3, "total_steps": 8, "epoch": 1, "total_epochs": 2, "percent": 37, "loss": 0.1234, "eta": "0:01:02"}
    assert read_progress(["progress 3/8 epoch 1/2 loss 0.1234 eta 0:01:02"], {"kind": "moss_install"}) == {}


@pytest.mark.parametrize("cache", ["images", "images/cache"])
def test_crop_cache_cannot_live_inside_dataset(configured, cache):
    rt, config = configured
    result = run_preflight({**config, "cache_dir": cache, "save_crops": True}, rt)
    assert not result["ok"] and "save_crops" in result["errors"][0]


def test_incomplete_or_wrong_vae_shape_is_rejected(configured):
    rt, config = configured
    file = rt.project_root / "models/moss_image/MOSS-Image-Base/vae/diffusion_pytorch_model.safetensors"
    shapes = vae_sentinel_shapes()
    shapes.pop("encoder.conv_out.weight")
    sparse_tensors(file, shapes)
    assert "vae" in run_preflight(config, rt)["errors"][0]
    shapes = vae_sentinel_shapes()
    shapes["bn.running_mean"] = [32]
    sparse_tensors(file, shapes)
    assert "vae" in run_preflight(config, rt)["errors"][0]


@pytest.mark.parametrize("preprocess", [False, True])
def test_pipeline_stops_at_mocked_child_boundary(configured, monkeypatch, preprocess):
    from mikazuki.engines.moss import entry
    rt, config = configured
    initial = adapt_config(config, rt)
    make_cache(initial)
    adapted = adapt_config({**config, "cache_dir": initial.train["cache"], "run_preprocess": preprocess}, rt)
    def request(values):
        return SimpleNamespace(to_argv=lambda: argv_for(values))
    monkeypatch.setattr(entry, "validate_requests", lambda value: (request(value.cache) if preprocess else None, request(value.train)))
    calls = []
    def fake_child(command, **kwargs):
        calls.append(command)
        assert kwargs == {"cwd": rt.source, "check": True}
        if "scripts.moss.cache" in command:
            make_cache(adapted)
        else:
            assert "scripts.moss.train" in command
    entry.execute_pipeline(rt, adapted, runner=fake_child)
    assert calls == pipeline_commands(rt, adapted)
    assert not Path(adapted.train["output"]).exists()
    assert not rt.python.exists()


def test_cache_child_failure_prevents_train(configured, monkeypatch):
    from mikazuki.engines.moss import entry
    rt, config = configured
    adapted = adapt_config(config, rt)
    monkeypatch.setattr(entry, "validate_requests", lambda value: (SimpleNamespace(to_argv=lambda: argv_for(value.cache)), SimpleNamespace(to_argv=lambda: argv_for(value.train))))
    calls = []
    def failed_child(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)
    with pytest.raises(subprocess.CalledProcessError):
        entry.execute_pipeline(rt, adapted, runner=failed_child)
    assert len(calls) == 1 and "scripts.moss.cache" in calls[0]
    assert not Path(adapted.train["output"]).exists()


def test_resolution_is_an_area_cap_not_forced_square_grid(configured):
    rt, config = configured
    adapted = adapt_config({**config, "resolution": 1000}, rt)
    assert adapted.cache["resolution"] == 1000
    assert check_inputs(adapted)["dataset_pairs"] == 1


@pytest.mark.parametrize("raw", [b"12", b"[]", b'{"__metadata__":null}'])
def test_malformed_header_structure_is_a_validation_error(tmp_path, raw):
    path = tmp_path / "bad-header.safetensors"
    path.write_bytes(struct.pack("<Q", len(raw)) + raw)
    with pytest.raises(ValueError, match="Invalid safetensors"):
        tensor_header(path)


def test_malformed_text_config_is_reported_without_crashing(configured):
    rt, config = configured
    path = rt.project_root / "models/moss_image/MOSS-Image-Base/text_encoder/config.json"
    data = json.loads(path.read_text())
    data["text_config"] = None
    path.write_text(json.dumps(data))
    assert "text_encoder" in run_preflight(config, rt)["errors"][0]


def _comfy_flat_files(rt):
    """Lay out Comfy-style single files beside the existing native fixture tree."""
    import shutil

    base = rt.project_root / "models/moss_image/MOSS-Image-Base"
    comfy = rt.project_root / "models/moss_comfy"
    comfy.mkdir(parents=True, exist_ok=True)
    dit = comfy / "dit.safetensors"
    te = comfy / "text_encoder.safetensors"
    vae = comfy / "vae.safetensors"
    tokenizer = comfy / "tokenizer"
    for src, dest in (
        (base / "transformer/diffusion_pytorch_model.safetensors", dit),
        (base / "text_encoder/model.safetensors", te),
        (base / "vae/diffusion_pytorch_model.safetensors", vae),
    ):
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        os.link(src, dest)
    if tokenizer.exists():
        if tokenizer.is_symlink() or tokenizer.is_file():
            tokenizer.unlink()
        else:
            shutil.rmtree(tokenizer)
    shutil.copytree(base / "tokenizer", tokenizer)
    return {
        "model_input_mode": "comfyui_files",
        "dit_path": str(dit.relative_to(rt.project_root)),
        "text_encoder_path": str(te.relative_to(rt.project_root)),
        "vae_path": str(vae.relative_to(rt.project_root)),
        "tokenizer_path": str(tokenizer.relative_to(rt.project_root)),
    }


def test_comfy_files_preflight_materializes_native_layout(configured):
    rt, config = configured
    comfy = _comfy_flat_files(rt)
    payload = {**config, **comfy}
    payload.pop("model_dir", None)
    result = run_preflight(payload, rt)
    assert result["ok"], result["errors"]
    facts = result["facts"]
    assert facts["model_format"] == "comfyui_files"
    staging = Path(facts["model_dir"])
    assert (staging / "MOSS-Image-Base/transformer/diffusion_pytorch_model.safetensors").is_file()
    assert (staging / "MOSS-Image-Base/text_encoder/config.json").is_file()
    assert (staging / "MOSS-Image-Base/vae/diffusion_pytorch_model.safetensors").is_file()
    assert (staging / "MOSS-Image-Base/tokenizer/tokenizer_config.json").is_file()
    assert (staging / ".next-moss-comfy.json").is_file()
    adapted = adapt_config(payload, rt)
    assert adapted.model_input_mode == "comfyui_files"
    assert adapted.comfy_paths is not None
    assert check_inputs(adapted)["model_format"] == "comfyui_files"


def test_comfy_sft_requires_separate_dit_and_stages_variant(configured):
    rt, config = configured
    comfy = _comfy_flat_files(rt)
    payload = {**config, **comfy, "model": "sft"}
    payload.pop("model_dir", None)
    assert "sft_dit_path" in run_preflight(payload, rt)["errors"][0]
    sft = rt.project_root / "models/moss_comfy/sft_dit.safetensors"
    os.link(rt.project_root / "models/moss_comfy/dit.safetensors", sft)
    payload["sft_dit_path"] = str(sft.relative_to(rt.project_root))
    result = run_preflight(payload, rt)
    assert result["ok"], result["errors"]
    staging = Path(result["facts"]["model_dir"])
    assert (staging / "MOSS-Image-SFT/transformer/diffusion_pytorch_model.safetensors").is_file()
    assert (staging / "MOSS-Image-Base/text_encoder/model.safetensors").is_file()


def test_comfy_rejects_stripped_text_prefix_and_sharded_dit(configured):
    rt, config = configured
    comfy = _comfy_flat_files(rt)
    payload = {**config, **comfy}
    payload.pop("model_dir", None)
    te = rt.project_root / "models/moss_comfy/text_encoder.safetensors"
    sparse_tensors(te, {"embed_tokens.weight": [248320, 4096]})
    assert "language_model" in run_preflight(payload, rt)["errors"][0]
    te_ok = {key: [1] for key in text_encoder_keys()}
    te_ok["language_model.embed_tokens.weight"] = [248320, 4096]
    sparse_tensors(te, te_ok)
    dit_dir = rt.project_root / "models/moss_comfy/dit_shards"
    dit_dir.mkdir(exist_ok=True)
    (dit_dir / "diffusion_pytorch_model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"layers.0.proj.q.weight": "part.safetensors"}})
    )
    payload["dit_path"] = str(dit_dir.relative_to(rt.project_root))
    assert "单文件" in run_preflight(payload, rt)["errors"][0] or "single" in run_preflight(payload, rt)["errors"][0].lower()


def test_fused_qkv_headers_accepted_and_split_state(configured):
    from mikazuki.engines.moss.comfy import (
        assert_dit_headers,
        fused_qkv_transformer_shapes,
        split_fused_qkv_state,
        validate_comfy_components,
    )

    class _Chunkable:
        def __init__(self, rows):
            self._rows = rows
            self.shape = (len(rows), len(rows[0]) if rows else 0)
            self.ndim = 2

        def chunk(self, parts, dim=0):
            assert dim == 0 and parts == 3 and len(self._rows) % 3 == 0
            step = len(self._rows) // 3
            return tuple(_Chunkable(self._rows[i * step:(i + 1) * step]) for i in range(3))

        def contiguous(self):
            return self

        def __eq__(self, other):
            return isinstance(other, _Chunkable) and self._rows == other._rows

    rt, _config = configured
    comfy = _comfy_flat_files(rt)
    dit = rt.project_root / "models/moss_comfy/dit.safetensors"
    sparse_tensors(dit, fused_qkv_transformer_shapes())
    headers, _ = tensor_header(dit)
    assert assert_dit_headers(headers, "dit_path") == "fused_qkv"
    facts = validate_comfy_components(
        {
            "dit_path": str(dit),
            "text_encoder_path": str(rt.project_root / comfy["text_encoder_path"]),
            "vae_path": str(rt.project_root / comfy["vae_path"]),
            "tokenizer_path": str(rt.project_root / comfy["tokenizer_path"]),
        },
        model="base",
        needs_text=True,
        needs_vae=True,
    )
    assert facts["dit_layout"] == "fused_qkv"
    assert facts["dit_remap"]

    base_rows = [[i, i + 1, i + 2, i + 3] for i in range(12)]
    base = _Chunkable(base_rows)
    fused = {f"layers.{i}.proj.qkv.weight": base for i in range(42)}
    remapped = split_fused_qkv_state(fused)
    assert "layers.0.proj.qkv.weight" not in remapped
    assert remapped["layers.0.proj.q.weight"].shape == (4, 4)
    assert remapped["layers.0.proj.q.weight"] == _Chunkable(base_rows[:4])
    assert remapped["layers.0.proj.k.weight"] == _Chunkable(base_rows[4:8])
    assert remapped["layers.0.proj.v.weight"] == _Chunkable(base_rows[8:])
    assert len([k for k in remapped if k.endswith(".q.weight")]) == 42


def test_preview_prompt_text_materializes_caption_file(configured):
    rt, config = configured
    adapted = adapt_config(
        {
            **config,
            "preview_every_epochs": 1,
            "preview_prompt": "a custom moss preview",
            "preview_prompt_file": "",
            "blocks_to_swap": 0,
        },
        rt,
    )
    prompt = Path(adapted.train["preview_prompt_file"])
    assert prompt.is_file()
    assert prompt.read_text(encoding="utf-8").strip() == "a custom moss preview"
    assert adapted.train["preview_caption_sha256"]


def test_comfy_dry_run_and_cache_identity_bind_source_files(configured, monkeypatch):
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    from mikazuki.engines.moss import routes, run

    rt, config = configured
    comfy = _comfy_flat_files(rt)
    payload = {**config, **comfy}
    payload.pop("model_dir", None)
    monkeypatch.chdir(rt.project_root)
    monkeypatch.setattr(run, "runtime", lambda: rt)
    monkeypatch.setattr(routes, "runtime", lambda: rt)
    monkeypatch.setattr(routes, "check_runtime", lambda _rt: None)
    client = TestClient(app)
    dry = client.post("/api/engines/moss/dry-run", json=payload).json()
    assert dry["status"] == "success", dry
    assert dry["data"]["facts"]["model_format"] == "comfyui_files"
    assert dry["data"]["config"]["model_input_mode"] == "comfyui_files"
    assert dry["data"]["config"]["comfy_paths"]
    adapted = adapt_config(payload, rt)
    make_cache(adapted)
    identity = json.loads((Path(adapted.train["cache"]) / ".next-moss-cache.json").read_text())
    assert identity["model_format"] == "comfyui_files"
    assert any(item[0] == "dit_path" for item in identity["assets"])
