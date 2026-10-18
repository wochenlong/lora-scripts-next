"""Local, header-only MOSS asset and dataset checks. Never load/download weights."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TE_SUFFIX = ".moss_te.safetensors"
LATENT_RE = re.compile(r"^(?P<stem>.+)_(?P<w>\d+)x(?P<h>\d+)\.moss_latent\.safetensors$")
FLOAT_DTYPES = {"BF16": 2, "F16": 2, "F32": 4}


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid/missing JSON / JSON 缺失或无效: {path}: {exc}") from exc


def tensor_header(path):
    """Read JSON and byte-range metadata only, including sparse test fixtures."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            size = struct.unpack("<Q", stream.read(8))[0]
            if size < 2 or size > min(16_000_000, path.stat().st_size - 8):
                raise ValueError("invalid header length")
            headers = json.loads(stream.read(size))
        if not isinstance(headers, dict):
            raise ValueError("expected a tensor-header object")
        metadata = headers.pop("__metadata__", {})
        if not headers or not isinstance(metadata, dict):
            raise ValueError("no tensors or invalid metadata")
        for key, info in headers.items():
            dtype, shape = info["dtype"], info["shape"]
            # The sole allowed integer buffer is BatchNorm's counter.
            width = FLOAT_DTYPES.get(dtype, 8 if dtype == "I64" and key.endswith("num_batches_tracked") else 0)
            if not width:
                raise ValueError(f"{key}: unsupported/quantized dtype {dtype}; use BF16/FP16/FP32")
            if not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
                raise ValueError(f"{key}: invalid tensor shape")
            start, end = info["data_offsets"]
            if type(start) is not int or type(end) is not int or start < 0 or end - start != math.prod(shape) * width or end + 8 + size > path.stat().st_size:
                raise ValueError(f"{key}: truncated/invalid tensor bytes")
        return headers, metadata
    except (OSError, ValueError, TypeError, KeyError, struct.error) as exc:
        raise ValueError(f"Invalid safetensors / 权重头无效: {path}: {exc}") from exc


def component_headers(directory, *, text=False):
    """Use the exact standard names from from_pretrained; reject loose Comfy files."""
    directory = Path(directory)
    stem = "model" if text else "diffusion_pytorch_model"
    index = directory / f"{stem}.safetensors.index.json"
    if index.is_file():
        mapping = read_json(index).get("weight_map")
        if not isinstance(mapping, dict) or not mapping or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
            raise ValueError(f"Invalid weight_map / 分片索引无效: {index}")
        files = []
        for name in sorted(set(mapping.values())):
            path = directory / name
            if path.resolve().parent != directory.resolve() or not path.is_file():
                raise ValueError(f"Missing/unsafe model shard / 模型分片缺失或路径越界: {path}")
            files.append(path)
    else:
        mapping = None
        files = [directory / f"{stem}.safetensors"]
        if not files[0].is_file():
            raise ValueError(f"Native Diffusers component required / 需要原生组件目录: {directory} ({stem}.safetensors or index.json)")
    result = {}
    for file in files:
        headers, _ = tensor_header(file)
        if set(result) & set(headers):
            raise ValueError(f"Duplicate tensor keys / 重复权重键名: {file}")
        if mapping is not None and any(mapping.get(key) != file.name for key in headers):
            raise ValueError(f"Shard index/key mismatch / 分片索引与键名不匹配: {file}")
        result.update(headers)
    if mapping is not None and set(result) != set(mapping):
        raise ValueError(f"Missing indexed tensors / 分片缺少索引中的权重: {index}")
    return result


def transformer_shapes():
    """Exact 463-key native DiT layout from pinned library/moss/model.py."""
    shapes = {}
    def linear(name, out_dim, in_dim, bias=True):
        shapes[name + ".weight"] = [out_dim, in_dim]
        if bias:
            shapes[name + ".bias"] = [out_dim]
    linear("video_embedder", 3072, 128)
    linear("text_embedder.proj", 3072, 4096)
    linear("time_embedding.0", 3072, 256)
    linear("time_embedding.2", 3072, 3072)
    linear("shared_block_modulation", 18432, 3072)
    linear("final_linear_video", 128, 3072, False)
    linear("video_head_modulation", 6144, 3072)
    shapes["final_norm_video.weight"] = [3072]
    shapes["rope.bands"] = [16]
    for prefix in [f"layers.{i}" for i in range(42)] + [f"text_embedder.blocks.{i}" for i in range(2)]:
        for name in ("norm1", "norm2"):
            shapes[f"{prefix}.{name}.weight"] = [3072]
        for name in ("q_norm", "k_norm"):
            shapes[f"{prefix}.{name}.weight"] = [128]
        if prefix.startswith("layers."):
            for name in ("q", "k", "v", "o"):
                linear(f"{prefix}.proj.{name}", 3072, 3072, False)
            linear(f"{prefix}.proj.ffn_up_gate", 16384, 3072, False)
            linear(f"{prefix}.proj.ffn_down", 3072, 8192, False)
        else:
            linear(f"{prefix}.qkv", 9216, 3072)
            linear(f"{prefix}.proj", 3072, 3072)
            linear(f"{prefix}.ffn_gate", 8192, 3072)
            linear(f"{prefix}.ffn_up", 8192, 3072)
            linear(f"{prefix}.ffn_down", 3072, 8192)
    return shapes


def _config(directory):
    config = read_json(directory / "config.json")
    if config.get("quantization_config") or config.get("_pre_quantization_dtype"):
        raise ValueError(f"Quantized weights unsupported / 不支持量化权重: {directory}")
    return config


def text_encoder_keys():
    """Native language_model keys in the official Qwen3.5-9B index.

    Base metadata ref 5f40f07a304541840b6019d2d34d30f966756787. The unused
    vision tower is intentionally not interpreted or remapped here.
    """
    keys = {"language_model.embed_tokens.weight", "language_model.norm.weight"}
    for i in range(32):
        prefix = f"language_model.layers.{i}."
        names = ["input_layernorm.weight", "post_attention_layernorm.weight",
                 "mlp.down_proj.weight", "mlp.gate_proj.weight", "mlp.up_proj.weight"]
        if i % 4 == 3:
            names += [f"self_attn.{name}.weight" for name in ("k_norm", "k_proj", "o_proj", "q_norm", "q_proj", "v_proj")]
        else:
            names += ["linear_attn.A_log", "linear_attn.dt_bias"]
            names += [f"linear_attn.{name}.weight" for name in ("conv1d", "in_proj_a", "in_proj_b", "in_proj_qkv", "in_proj_z", "norm", "out_proj")]
        keys.update(prefix + name for name in names)
    return keys



def vae_sentinel_shapes():
    """Critical native FLUX.2 VAE stages, inferred from pinned Diffusers/config.

    This is a structural preflight, not a full tensor-value or loader audit.
    BatchNorm is affine=False; running stats contain packed 32*2*2 channels.
    """
    shapes = {"bn.running_mean": [128], "bn.running_var": [128]}
    stages = {
        "encoder.conv_in": [128, 3, 3, 3], "encoder.conv_out": [64, 512, 3, 3],
        "decoder.conv_in": [384, 32, 3, 3], "decoder.conv_out": [3, 96, 3, 3],
        "quant_conv": [64, 64, 1, 1], "post_quant_conv": [32, 32, 1, 1],
        "encoder.mid_block.attentions.0.to_q": [512, 512],
        "decoder.mid_block.attentions.0.to_q": [384, 384],
    }
    for i, channels in enumerate((128, 256, 512, 512)):
        stages[f"encoder.down_blocks.{i}.resnets.1.conv2"] = [channels, channels, 3, 3]
    for i, channels in enumerate((384, 384, 192, 96)):
        stages[f"decoder.up_blocks.{i}.resnets.2.conv2"] = [channels, channels, 3, 3]
    for name, shape in stages.items():
        shapes[name + ".weight"] = shape
        shapes[name + ".bias"] = [shape[0]]
    return shapes


def validate_models(adapted):
    mode = getattr(adapted, "model_input_mode", "native_directory") or "native_directory"
    if mode == "comfyui_files":
        from .comfy import materialize_comfy_layout, validate_comfy_components

        paths = getattr(adapted, "comfy_paths", None) or {}
        if not paths:
            raise ValueError("comfy_paths: missing Comfy component paths / 缺少 Comfy 组件路径")
        # Staging always materializes the full Base tree so upstream from_pretrained works.
        facts = validate_comfy_components(
            paths, model=adapted.train["model"], needs_text=True, needs_vae=True,
        )
        resolved = {key: facts[key] for key in ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path")}
        if "sft_dit_path" in facts:
            resolved["sft_dit_path"] = facts["sft_dit_path"]
        staging = materialize_comfy_layout(resolved, model=adapted.train["model"], staging_root=Path(adapted.train["model_dir"]))
        facts["model_dir"] = str(staging)
        if facts.get("dit_layout") == "fused_qkv":
            facts["staging"] = "remap fused qkv → q/k/v into native Diffusers layout"
        else:
            facts["staging"] = "hardlink/symlink/copy into native Diffusers layout"
        return facts

    model_dir = Path(adapted.train["model_dir"])
    if not model_dir.is_dir():
        raise ValueError(f"model_dir: native MOSS parent directory required / 请选择原生 MOSS 目录: {model_dir}")
    base = model_dir / "MOSS-Image-Base"
    variant = model_dir / ("MOSS-Image-SFT" if adapted.train["model"] == "sft" else "MOSS-Image-Base")
    transformer = variant / "transformer"
    config = _config(transformer)
    expected_config = {"dim": 3072, "ffn_dim": 8192, "num_heads": 24, "num_layers": 42, "text_dim": 4096, "freq_dim": 256, "latent_channels": 128}
    if config.get("_class_name") != "MOSSImageTransformer" or any(config.get(k) != v for k, v in expected_config.items()):
        raise ValueError(f"transformer: expected native 42-block MOSS-Image 5B config / 需要原生 MOSS 配置: {transformer}")
    headers = component_headers(transformer)
    shapes = transformer_shapes()
    if set(headers) != set(shapes) or any(headers[k]["shape"] != shape for k, shape in shapes.items() if k in headers):
        raise ValueError("transformer: MOSS tensor names/shapes mismatch / MOSS 权重键名或尺寸不匹配，拒绝静默初始化")
    needs_text = adapted.run_preprocess or adapted.train["caption_dropout"] > 0
    if needs_text:
        te_dir = base / "text_encoder"
        te_config = _config(te_dir)
        text_config = te_config.get("text_config", {})
        architectures = te_config.get("architectures")
        if not isinstance(text_config, dict) or not isinstance(architectures, list) or te_config.get("model_type") != "qwen3_5" or "Qwen3_5Model" not in architectures or text_config.get("hidden_size") != 4096 or text_config.get("num_hidden_layers") != 32:
            raise ValueError("text_encoder: use native Qwen3_5Model with language_model prefix / 需要原生 Qwen3.5 完整目录，不能使用去掉前缀的纯文本模型")
        te = component_headers(te_dir, text=True)
        if te.get("language_model.embed_tokens.weight", {}).get("shape") != [248320, 4096] or not text_encoder_keys().issubset(te):
            raise ValueError("text_encoder: missing native language_model.* weights / 缺少原生 language_model.* 权重，拒绝静默初始化")
        tokenizer = base / "tokenizer"
        for filename in ("tokenizer.json", "tokenizer_config.json"):
            read_json(tokenizer / filename)
        token_config = read_json(tokenizer / "tokenizer_config.json")
        if not token_config.get("chat_template") and not (tokenizer / "chat_template.jinja").is_file():
            raise ValueError("tokenizer: MOSS chat template is missing / 缺少 MOSS 对话模板")
    if adapted.run_preprocess:
        vae_dir = base / "vae"
        vae_config = _config(vae_dir)
        vae_expected = {"_class_name": "AutoencoderKLFlux2", "latent_channels": 32, "patch_size": [2, 2],
                        "in_channels": 3, "out_channels": 3, "layers_per_block": 2,
                        "block_out_channels": [128, 256, 512, 512], "decoder_block_out_channels": [96, 192, 384, 384],
                        "use_quant_conv": True, "use_post_quant_conv": True, "mid_block_add_attention": True}
        if any(vae_config.get(key) != value for key, value in vae_expected.items()):
            raise ValueError("vae: expected native FLUX.2 VAE / 需要原生 FLUX.2 VAE")
        vae = component_headers(vae_dir)
        if any(vae.get(key, {}).get("shape") != shape for key, shape in vae_sentinel_shapes().items()):
            raise ValueError("vae: missing/wrong FLUX.2 encoder/decoder/BatchNorm shapes / FLUX.2 VAE 关键权重缺失或尺寸不匹配")
    return {"model_variant": adapted.train["model"], "model_dir": str(model_dir), "model_format": "native-diffusers", "transformer_tensors": len(headers), "validation": "header-only; tensors not loaded"}


def cache_identity(adapted):
    """Upstream cache freshness omits model identity and VAE dtype; bind both."""
    mode = getattr(adapted, "model_input_mode", "native_directory") or "native_directory"
    comfy_paths = getattr(adapted, "comfy_paths", None) or {}
    if mode == "comfyui_files" and comfy_paths:
        assets = []
        for key in ("dit_path", "text_encoder_path", "vae_path", "tokenizer_path", "sft_dit_path"):
            raw = comfy_paths.get(key)
            if not raw:
                continue
            path = Path(raw)
            if path.is_file():
                stat = path.stat()
                assets.append([key, str(path.resolve()), stat.st_size, stat.st_mtime_ns])
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        stat = child.stat()
                        assets.append([key, str(child.resolve()), stat.st_size, stat.st_mtime_ns])
        return {
            "version": 1, "model_format": "comfyui_files", "model_dir": adapted.train["model_dir"],
            "assets": assets, "src": adapted.cache.get("src", ""),
            **{key: adapted.cache[key] for key in ("resolution", "vae_dtype", "max_text_tokens")},
        }
    base = Path(adapted.train["model_dir"]) / "MOSS-Image-Base"
    assets = []
    for component in ("text_encoder", "tokenizer", "vae"):
        for path in sorted((base / component).glob("*")):
            if path.is_file():
                stat = path.stat()
                assets.append([str(path), stat.st_size, stat.st_mtime_ns])
    return {
        "version": 1, "model_dir": adapted.train["model_dir"], "assets": assets,
        "src": adapted.cache.get("src", ""),
        **{key: adapted.cache[key] for key in ("resolution", "vae_dtype", "max_text_tokens")},
    }


def write_cache_identity(adapted):
    path = Path(adapted.train["cache"]) / ".next-moss-cache.json"
    path.write_text(json.dumps(cache_identity(adapted), ensure_ascii=False, indent=2), encoding="utf-8")


def source_pairs(src):
    from PIL import Image
    src = Path(src)
    if not src.is_dir():
        raise ValueError(f"src: dataset directory does not exist / 数据集目录不存在: {src}")
    images = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    if not images:
        raise ValueError(f"src: no supported images / 没有 PNG/JPEG/WebP 图像: {src}")
    counts = {}
    for image in images:
        counts[image.stem] = counts.get(image.stem, 0) + 1
    pairs = {}
    for image in images:
        caption = image.with_suffix(".txt")
        if not caption.is_file():
            raise ValueError(f"src: missing .txt caption / 缺少标注: {caption}")
        text = caption.read_text(encoding="utf-8").strip()
        try:
            with Image.open(image) as opened:
                if min(opened.size) < 16:
                    raise ValueError("image dimensions must be at least 16 pixels")
                opened.verify()
        except (OSError, ValueError) as exc:
            raise ValueError(f"src: invalid image / 图像无效: {image}: {exc}") from exc
        stem = image.stem if counts[image.stem] == 1 else "__".join((*image.relative_to(src).parent.parts, image.stem))
        if stem == "_empty":
            raise ValueError("src: _empty is reserved for caption dropout / _empty 是空提示缓存保留名称，请重命名")
        if stem in pairs:
            raise ValueError(f"src: colliding cache stem / 缓存名称冲突: {stem}; rename the images")
        pairs[stem] = (image, hashlib.sha256(text.encode()).hexdigest())
    return pairs


def validate_cache(adapted, *, completed=False):
    """Check actual tensor shapes and orphan samples, never just file counts."""
    cache = Path(adapted.train["cache"])
    if adapted.run_preprocess and adapted.cache.get("save_crops"):
        src = Path(adapted.cache["src"]).resolve()
        if cache.resolve() == src or src in cache.resolve().parents:
            raise ValueError("cache_dir: save_crops requires a cache outside src / 保存裁剪图时缓存目录不能位于数据集内")
    pairs = source_pairs(adapted.cache["src"]) if adapted.cache.get("src") else None
    if not cache.exists() and adapted.run_preprocess and not completed:
        return {"dataset_pairs": len(pairs or {}), "cache_pairs": 0}
    if not cache.is_dir():
        raise ValueError(f"cache_dir: directory missing / 缓存目录不存在: {cache}")
    identity_file = cache / ".next-moss-cache.json"
    identity = read_json(identity_file) if identity_file.is_file() else None
    current_identity = cache_identity(adapted)
    if adapted.run_preprocess and any(cache.glob("*.safetensors")):
        if identity != current_identity and not adapted.cache["overwrite"]:
            raise ValueError("cache_dir: cache provenance/settings changed or unknown; use a fresh directory or overwrite_cache / 缓存来源或参数已变更，请换目录或启用重建缓存")
    elif identity is not None:
        # Cache-only mode intentionally omits src/cache settings from the UI,
        # but must still bind a known cache to the same frozen model assets.
        if any(identity.get(key) != current_identity[key] for key in ("model_dir", "assets")):
            raise ValueError("cache_dir: cached model identity changed / 缓存的模型来源已变更，请重新预处理")
    empty = cache / f"_empty{TE_SUFFIX}"
    if adapted.train["caption_dropout"] > 0 and empty.exists():
        if identity is None or any(identity.get(key) != current_identity[key] for key in ("model_dir", "assets")) or adapted.cache["overwrite"]:
            raise ValueError("cache_dir: empty-prompt provenance is unknown/changed; use a fresh directory / 空提示缓存来源无效，请换新目录")
        empty_headers, _ = tensor_header(empty)
        shape = empty_headers.get("embeds", {}).get("shape", [])
        if len(shape) != 2 or shape[1] != 4096 or not 1 <= shape[0] <= 4096:
            raise ValueError("cache_dir: invalid empty-prompt embedding / 空提示缓存尺寸错误")
    latents = {}
    for path in cache.glob("*.moss_latent.safetensors"):
        match = LATENT_RE.match(path.name)
        if not match:
            raise ValueError(f"cache_dir: invalid latent name / 缓存文件名无效: {path.name}")
        stem = match["stem"]
        if pairs is not None and stem not in pairs:
            raise ValueError(f"cache_dir: orphan sample {stem}; choose a fresh cache / 缓存包含已移除的样本，请换新缓存目录")
        if stem in latents:
            raise ValueError(f"cache_dir: multiple resolutions for {stem}; choose a fresh cache / 同一样本存在多份缓存")
        latents[stem] = (path, int(match["w"]), int(match["h"]))
    require_ready = completed or not adapted.run_preprocess
    if not require_ready:
        return {"dataset_pairs": len(pairs or {}), "cache_pairs": len(latents)}
    if not latents:
        raise ValueError("cache_dir: no MOSS cached samples / 没有 MOSS 缓存样本")
    if pairs is not None and set(latents) != set(pairs):
        raise ValueError("cache_dir: source/cache sample mismatch / 数据集与缓存样本不一致")
    for stem, (path, width, height) in latents.items():
        latent, _ = tensor_header(path)
        text, metadata = tensor_header(cache / f"{stem}{TE_SUFFIX}")
        if width % 16 or height % 16 or latent.get("latent", {}).get("shape") != [128, height // 16, width // 16]:
            raise ValueError(f"cache_dir: invalid packed latent shape / latent 尺寸错误: {path}")
        shape = text.get("embeds", {}).get("shape", [])
        if len(shape) != 2 or shape[1] != 4096 or not 1 <= shape[0] <= 4096:
            raise ValueError(f"cache_dir: invalid text embedding shape / 文本缓存尺寸错误: {stem}")
        if pairs is not None:
            image, caption_hash = pairs[stem]
            if metadata.get("caption_sha256") != caption_hash or metadata.get("max_text_tokens") != str(adapted.cache["max_text_tokens"]) or path.stat().st_mtime < image.stat().st_mtime:
                raise ValueError(f"cache_dir: stale source/caption cache / 缓存过期: {stem}")
    return {"dataset_pairs": len(pairs or {}), "cache_pairs": len(latents)}


def check_output(output):
    """Reserve the complete native output namespace, including periodic saves."""
    output = Path(output)
    pattern = re.compile(rf"^{re.escape(output.stem)}(?:\.safetensors|\.json|_e\d+\.safetensors)$", re.IGNORECASE)
    preview_dir = output.parent / (output.stem + "_samples")
    if preview_dir.exists() and any(preview_dir.iterdir()):
        raise ValueError(f"preview output exists; choose a new name: {preview_dir}")
    if output.parent.is_dir():
        for path in output.parent.iterdir():
            if pattern.fullmatch(path.name):
                raise ValueError(f"output exists; choose a new name / 输出文件已存在，请换名称: {path}")
