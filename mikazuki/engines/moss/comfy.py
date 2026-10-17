"""Comfy-style single-file MOSS inputs → native Diffusers layout for upstream.

Upstream ``library/moss/loader.py`` only loads via ``from_pretrained`` on
``MOSS-Image-{Base,SFT}/{transformer,text_encoder,vae,tokenizer}``. Comfy users
typically keep DiT / TE / VAE as flat ``.safetensors`` plus a tokenizer folder.
This module validates those headers against the native key contract, then
materializes a staging tree (links preferred) so training can keep using the
pinned anima_lora entrypoints without rewriting weights (#474).
"""
from __future__ import annotations

import hashlib
import json
import os
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


def validate_comfy_components(paths: dict, *, model: str, needs_text: bool, needs_vae: bool) -> dict:
    """Header-only validation for Comfy-style single files + tokenizer dir."""
    dit = resolve_weight_file(paths["dit_path"], "dit_path")
    dit_headers, _ = tensor_header(dit)
    _assert_headers(dit_headers, transformer_shapes(), "dit_path")

    facts = {
        "model_format": "comfyui_files",
        "dit_path": str(dit),
        "transformer_tensors": len(dit_headers),
        "validation": "header-only; tensors not loaded",
        "model_variant": model,
    }

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
        _assert_headers(sft_headers, transformer_shapes(), "sft_dit_path")
        facts["sft_dit_path"] = str(sft)

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


def materialize_comfy_layout(paths: dict, *, model: str, staging_root: Path) -> Path:
    """Build ``staging_root/MOSS-Image-Base`` (+ optional SFT) and return parent model_dir."""
    staging_root = Path(staging_root)
    dit = resolve_weight_file(paths["dit_path"], "dit_path")
    text_encoder = resolve_weight_file(paths["text_encoder_path"], "text_encoder_path")
    vae = resolve_weight_file(paths["vae_path"], "vae_path")
    tokenizer = Path(paths["tokenizer_path"]).resolve()
    sft_dit = resolve_weight_file(paths["sft_dit_path"], "sft_dit_path") if model == "sft" else None
    if staging_root.exists():
        shutil.rmtree(staging_root)
    base = staging_root / "MOSS-Image-Base"
    methods = []
    methods += _stage_component(base, "transformer", dit)
    methods += _stage_component(base, "text_encoder", text_encoder)
    methods += _stage_component(base, "vae", vae)
    methods += _stage_component(base, "tokenizer", None, link_tokenizer=tokenizer)
    if model == "sft":
        sft = staging_root / "MOSS-Image-SFT"
        methods += _stage_component(sft, "transformer", sft_dit)
    # Smoke-check the staged native layout with the existing directory validators.
    component_headers(base / "transformer")
    component_headers(base / "text_encoder", text=True)
    component_headers(base / "vae")
    resolved = {
        "dit_path": str(dit), "text_encoder_path": str(text_encoder),
        "vae_path": str(vae), "tokenizer_path": str(tokenizer),
    }
    if sft_dit is not None:
        resolved["sft_dit_path"] = str(sft_dit)
    (staging_root / ".next-moss-comfy.json").write_text(
        json.dumps({"paths": resolved, "model": model, "link_methods": methods}, ensure_ascii=False, indent=2),
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
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16]
