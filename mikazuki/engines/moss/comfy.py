"""Comfy-style single-file MOSS inputs → native Diffusers layout for upstream.

Upstream ``library/moss/loader.py`` only loads via ``from_pretrained`` on
``MOSS-Image-{Base,SFT}/{transformer,text_encoder,vae,tokenizer}``. Comfy users
typically keep DiT / TE / VAE as flat ``.safetensors`` plus a tokenizer folder.

This module validates those headers against the native key contract (or the
Comfy-Org fused-``qkv`` variant), then materializes a staging tree. Native-key
files prefer hardlink/symlink/copy; fused ``layers.*.proj.qkv`` weights are
split into ``q`` / ``k`` / ``v`` once into the staging transformer file so the
pinned anima_lora entrypoints keep working (#474).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from .inputs import (
    component_headers,
    read_json,
    tensor_header,
    text_encoder_keys,
    transformer_shapes,
    vae_sentinel_shapes,
)

NATIVE_CONFIGS = Path(__file__).resolve().parent / "native_configs"
WEIGHT_NAMES = {
    "transformer": "diffusion_pytorch_model.safetensors",
    "text_encoder": "model.safetensors",
    "vae": "diffusion_pytorch_model.safetensors",
}
# Bump when remap math or accepted fused layouts change.
REMAP_SCHEME = "moss-comfy-qkv-split-v1"
QKV_KEY_RE = re.compile(r"^(layers\.\d+\.proj)\.qkv\.weight$")


def _link_or_copy(src: Path, dest: Path) -> str:
    """Prefer hardlink, then symlink, then copy. Returns the method used."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    try:
        os.link(src, dest)
        return "hardlink"
    except OSError:
        pass
    try:
        dest.symlink_to(src, target_is_directory=src.is_dir())
        return "symlink"
    except OSError:
        pass
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    return "copy"


def resolve_weight_file(path: Path, field: str) -> Path:
    """One safetensors file, or a directory with exactly one unsharded candidate."""
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.safetensors"))
        indices = sorted(path.glob("*.safetensors.index.json"))
        if indices:
            raise ValueError(
                f"{field}: Comfy 模式请提供合并后的单文件权重；分片索引请先合并或改用原生目录模式 / "
                f"use a single merged .safetensors (not a sharded index): {path}"
            )
        if len(files) != 1:
            raise ValueError(f"{field}: 目录内需要恰好一个 .safetensors / need exactly one weight file: {path}")
        path = files[0]
    if not path.is_file() or path.suffix != ".safetensors":
        raise ValueError(f"{field}: 请选择 .safetensors 文件 / choose a .safetensors file: {path}")
    return path


def _assert_headers(headers: dict, expected_shapes: dict, field: str, *, subset: bool = False) -> None:
    if subset:
        missing = [key for key, shape in expected_shapes.items() if headers.get(key, {}).get("shape") != shape]
        if missing:
            raise ValueError(
                f"{field}: missing/wrong tensors ({len(missing)}) / 缺少或尺寸不符的权重: "
                + ", ".join(missing[:8])
                + ("…" if len(missing) > 8 else "")
            )
        return
    if set(headers) != set(expected_shapes):
        extra = sorted(set(headers) - set(expected_shapes))[:5]
        missing = sorted(set(expected_shapes) - set(headers))[:5]
        raise ValueError(
            f"{field}: key set mismatch / 键名集合与原生 MOSS 不一致"
            + (f"; missing={missing}" if missing else "")
            + (f"; extra={extra}" if extra else "")
        )
    bad = [key for key, shape in expected_shapes.items() if headers[key]["shape"] != shape]
    if bad:
        raise ValueError(f"{field}: shape mismatch / 尺寸不匹配: {', '.join(bad[:8])}")


def dit_layout_from_headers(headers: dict) -> str:
    """Return ``native`` or ``fused_qkv`` (Comfy-Org packs fuse proj q/k/v)."""
    has_qkv = "layers.0.proj.qkv.weight" in headers
    has_q = "layers.0.proj.q.weight" in headers
    if has_qkv and has_q:
        raise ValueError(
            "dit_path: mixed native and fused qkv keys / 同时存在 qkv 与拆分的 q/k/v，无法判断布局"
        )
    if has_qkv and not has_q:
        return "fused_qkv"
    if has_q and not has_qkv:
        return "native"
    raise ValueError("dit_path: unrecognized transformer layout / 无法识别 DiT 键名布局")


def fused_qkv_transformer_shapes() -> dict:
    """Native shapes with each layer's q/k/v replaced by a fused ``qkv`` weight."""
    shapes = dict(transformer_shapes())
    for i in range(42):
        for name in ("q", "k", "v"):
            del shapes[f"layers.{i}.proj.{name}.weight"]
        shapes[f"layers.{i}.proj.qkv.weight"] = [9216, 3072]
    return shapes


def assert_dit_headers(headers: dict, field: str) -> str:
    layout = dit_layout_from_headers(headers)
    expected = fused_qkv_transformer_shapes() if layout == "fused_qkv" else transformer_shapes()
    _assert_headers(headers, expected, field)
    return layout


def split_fused_qkv_state(tensors: dict) -> dict:
    """Split ``layers.N.proj.qkv.weight`` → ``q`` / ``k`` / ``v`` (chunk dim 0)."""
    result = {}
    split = 0
    for key, tensor in tensors.items():
        match = QKV_KEY_RE.fullmatch(key)
        if not match:
            result[key] = tensor
            continue
        if getattr(tensor, "ndim", None) != 2 or int(tensor.shape[0]) % 3 != 0:
            raise ValueError(f"{key}: expected 2D weight with out_features divisible by 3, got {list(tensor.shape)}")
        q_w, k_w, v_w = tensor.chunk(3, dim=0)
        prefix = match.group(1)
        result[f"{prefix}.q.weight"] = q_w.contiguous()
        result[f"{prefix}.k.weight"] = k_w.contiguous()
        result[f"{prefix}.v.weight"] = v_w.contiguous()
        split += 1
    if split != 42:
        raise ValueError(f"dit_path: expected 42 fused qkv layers, found {split} / 融合 qkv 层数应为 42")
    return result


def rewrite_fused_qkv_dit(src: Path, dest: Path) -> dict:
    """Load a fused-qkv DiT, write native-key safetensors beside the staging tree."""
    from safetensors import safe_open
    from safetensors.torch import save_file

    print(f"[moss-comfy] rewriting fused qkv DiT → native keys: {src}", flush=True)
    loaded = {}
    with safe_open(src, framework="pt", device="cpu") as handle:
        for key in handle.keys():
            loaded[key] = handle.get_tensor(key)
    remapped = split_fused_qkv_state(loaded)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    save_file(remapped, str(dest))
    print(f"[moss-comfy] wrote remapped DiT ({len(remapped)} tensors): {dest}", flush=True)
    return {"remap_scheme": REMAP_SCHEME, "fused_qkv_layers": 42, "tensors": len(remapped)}


def validate_comfy_components(paths: dict, *, model: str, needs_text: bool, needs_vae: bool) -> dict:
    """Header-only validation for Comfy-style single files + tokenizer dir."""
    dit = resolve_weight_file(paths["dit_path"], "dit_path")
    dit_headers, _ = tensor_header(dit)
    dit_layout = assert_dit_headers(dit_headers, "dit_path")

    facts = {
        "model_format": "comfyui_files",
        "dit_path": str(dit),
        "dit_layout": dit_layout,
        "transformer_tensors": len(dit_headers),
        "validation": "header-only; tensors not loaded",
        "model_variant": model,
    }
    if dit_layout == "fused_qkv":
        facts["dit_remap"] = REMAP_SCHEME

    if needs_text:
        te = resolve_weight_file(paths["text_encoder_path"], "text_encoder_path")
        te_headers, _ = tensor_header(te)
        if "language_model.embed_tokens.weight" not in te_headers:
            raise ValueError(
                "text_encoder_path: 需要保留 language_model.* 前缀的原生 Qwen3.5 权重；"
                "去掉前缀的纯文本导出不受支持 / keep native language_model.* keys"
            )
        if te_headers.get("language_model.embed_tokens.weight", {}).get("shape") != [248320, 4096]:
            raise ValueError("text_encoder_path: embed_tokens shape must be [248320, 4096]")
        if not text_encoder_keys().issubset(te_headers):
            missing = sorted(text_encoder_keys() - set(te_headers))[:8]
            raise ValueError(
                "text_encoder_path: missing native language_model.* weights / 缺少原生权重: "
                + ", ".join(missing)
            )
        tokenizer = Path(paths["tokenizer_path"])
        if not tokenizer.is_dir():
            raise ValueError(f"tokenizer_path: 需要 tokenizer 目录 / tokenizer directory required: {tokenizer}")
        for filename in ("tokenizer.json", "tokenizer_config.json"):
            read_json(tokenizer / filename)
        token_config = read_json(tokenizer / "tokenizer_config.json")
        if not token_config.get("chat_template") and not (tokenizer / "chat_template.jinja").is_file():
            raise ValueError("tokenizer_path: MOSS chat template is missing / 缺少 MOSS 对话模板")
        facts.update(text_encoder_path=str(te), tokenizer_path=str(tokenizer.resolve()))

    if needs_vae:
        vae = resolve_weight_file(paths["vae_path"], "vae_path")
        vae_headers, _ = tensor_header(vae)
        _assert_headers(vae_headers, vae_sentinel_shapes(), "vae_path", subset=True)
        facts["vae_path"] = str(vae)

    if model == "sft":
        sft = resolve_weight_file(paths["sft_dit_path"], "sft_dit_path")
        sft_headers, _ = tensor_header(sft)
        sft_layout = assert_dit_headers(sft_headers, "sft_dit_path")
        facts["sft_dit_path"] = str(sft)
        facts["sft_dit_layout"] = sft_layout
        if sft_layout == "fused_qkv":
            facts["sft_dit_remap"] = REMAP_SCHEME

    return facts


def _write_config(dest: Path, name: str) -> None:
    source = NATIVE_CONFIGS / f"{name}_config.json"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _stage_component(root: Path, component: str, weight: Path | None, *, link_tokenizer: Path | None = None) -> list[str]:
    methods = []
    directory = root / component
    if component == "tokenizer":
        assert link_tokenizer is not None
        if directory.exists():
            if directory.is_symlink() or directory.is_file():
                directory.unlink()
            else:
                shutil.rmtree(directory)
        methods.append(_link_or_copy(link_tokenizer.resolve(), directory))
        return methods
    assert weight is not None
    directory.mkdir(parents=True, exist_ok=True)
    _write_config(directory / "config.json", component)
    methods.append(_link_or_copy(weight.resolve(), directory / WEIGHT_NAMES[component]))
    return methods


def _stage_transformer(root: Path, weight: Path, *, layout: str) -> list[str]:
    directory = root / "transformer"
    directory.mkdir(parents=True, exist_ok=True)
    _write_config(directory / "config.json", "transformer")
    dest = directory / WEIGHT_NAMES["transformer"]
    if layout == "fused_qkv":
        rewrite_fused_qkv_dit(weight.resolve(), dest)
        return ["remap-qkv"]
    return [_link_or_copy(weight.resolve(), dest)]


def _staging_reusable(staging_root: Path, resolved: dict, *, model: str, dit_layout: str, sft_layout: str | None) -> bool:
    meta_path = staging_root / ".next-moss-comfy.json"
    weight = staging_root / "MOSS-Image-Base" / "transformer" / WEIGHT_NAMES["transformer"]
    if not meta_path.is_file() or not weight.is_file():
        return False
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected_scheme = REMAP_SCHEME if dit_layout == "fused_qkv" else None
    if (
        data.get("paths") != resolved
        or data.get("model") != model
        or data.get("dit_layout") != dit_layout
        or data.get("remap_scheme") != expected_scheme
    ):
        return False
    if model == "sft":
        sft_weight = staging_root / "MOSS-Image-SFT" / "transformer" / WEIGHT_NAMES["transformer"]
        if not sft_weight.is_file() or data.get("sft_dit_layout") != sft_layout:
            return False
        sft_scheme = REMAP_SCHEME if sft_layout == "fused_qkv" else None
        if data.get("sft_remap_scheme") != sft_scheme:
            return False
    return True


def materialize_comfy_layout(paths: dict, *, model: str, staging_root: Path) -> Path:
    """Build ``staging_root/MOSS-Image-Base`` (+ optional SFT) and return parent model_dir."""
    staging_root = Path(staging_root)
    dit = resolve_weight_file(paths["dit_path"], "dit_path")
    text_encoder = resolve_weight_file(paths["text_encoder_path"], "text_encoder_path")
    vae = resolve_weight_file(paths["vae_path"], "vae_path")
    tokenizer = Path(paths["tokenizer_path"]).resolve()
    sft_dit = resolve_weight_file(paths["sft_dit_path"], "sft_dit_path") if model == "sft" else None
    dit_headers, _ = tensor_header(dit)
    dit_layout = assert_dit_headers(dit_headers, "dit_path")
    sft_layout = None
    if sft_dit is not None:
        sft_headers, _ = tensor_header(sft_dit)
        sft_layout = assert_dit_headers(sft_headers, "sft_dit_path")
    resolved = {
        "dit_path": str(dit), "text_encoder_path": str(text_encoder),
        "vae_path": str(vae), "tokenizer_path": str(tokenizer),
    }
    if sft_dit is not None:
        resolved["sft_dit_path"] = str(sft_dit)
    if _staging_reusable(staging_root, resolved, model=model, dit_layout=dit_layout, sft_layout=sft_layout):
        return staging_root
    if staging_root.exists():
        shutil.rmtree(staging_root)
    base = staging_root / "MOSS-Image-Base"
    methods = []
    methods += _stage_transformer(base, dit, layout=dit_layout)
    methods += _stage_component(base, "text_encoder", text_encoder)
    methods += _stage_component(base, "vae", vae)
    methods += _stage_component(base, "tokenizer", None, link_tokenizer=tokenizer)
    if model == "sft":
        sft = staging_root / "MOSS-Image-SFT"
        methods += _stage_transformer(sft, sft_dit, layout=sft_layout or "native")
    # Smoke-check the staged native layout with the existing directory validators.
    component_headers(base / "transformer")
    component_headers(base / "text_encoder", text=True)
    component_headers(base / "vae")
    meta = {
        "paths": resolved,
        "model": model,
        "dit_layout": dit_layout,
        "remap_scheme": REMAP_SCHEME if dit_layout == "fused_qkv" else None,
        "link_methods": methods,
    }
    if sft_layout is not None:
        meta["sft_dit_layout"] = sft_layout
        meta["sft_remap_scheme"] = REMAP_SCHEME if sft_layout == "fused_qkv" else None
    (staging_root / ".next-moss-comfy.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return staging_root


def comfy_layout_digest(paths: dict, *, model: str) -> str:
    payload = []
    for key in ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path", "sft_dit_path"):
        raw = paths.get(key)
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            stat = path.stat()
            payload.append([key, str(path.resolve()), stat.st_size, stat.st_mtime_ns])
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    stat = child.stat()
                    payload.append([key, str(child.resolve()), stat.st_size, stat.st_mtime_ns])
    payload.append(["model", model])
    payload.append(["remap_scheme", REMAP_SCHEME])
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16]
