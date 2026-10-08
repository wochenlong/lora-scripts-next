"""Explicit local model modes. No path-to-Hub guessing and no implicit copies."""
from pathlib import Path, PureWindowsPath
import json

from .capabilities import MODELS, family
from mikazuki.model_asset_validation import local_weights, safetensors_header


def absolute(value, root: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("模型路径不能为空")
    if PureWindowsPath(text).drive and not Path(text).is_absolute():
        raise ValueError(f"Windows 路径不在当前服务端，请选择服务端路径: {text}")
    path = Path(text.replace("\\", "/")).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def model_inputs(source, root, variant):
    spec = MODELS[variant]
    kind = family(variant)
    mode = source.get("model_input_mode")
    legacy = not mode
    raw = source.get("model_path") or source.get("dit_path") or source.get("dit") or source.get("pretrained_model_name_or_path")
    if not mode:
        path = absolute(raw, root)
        if path.is_dir():
            mode = "model_directory"
        elif path.is_file():
            mode = "single_file"
        else:
            raise ValueError("旧配置的模型路径无法识别；请选择模型输入模式并填写本地路径，不会自动下载或转换")
    if mode not in spec["modes"]:
        raise ValueError(f"{spec['label']} 不支持模型输入模式 {mode}；支持: {', '.join(spec['modes'])}")
    # Only the selected mode participates in the launch. Other fields stay in drafts.
    key = "model_path" if mode == "model_directory" else "dit_path"
    path = absolute(source.get(key) or (raw if legacy else None), root)
    if not (path.is_dir() if mode == "model_directory" else path.is_file()):
        raise ValueError(f"{key} 路径不存在或类型错误: {path}（必须是服务端本地路径）")
    model = {"arch": spec["arch"], "name_or_path": str(path), "model_kwargs": {"use_comfy_weights": False}}
    assets = {"mode": mode, "family": kind, "source": str(path), "variant": variant}
    te = ""
    if kind in {"klein", "krea2"}:
        selected = source.get("model_variant", spec["variants"][0])
        if selected not in spec["variants"]:
            raise ValueError(f"{variant} 不支持 model_variant={selected}")
        if path.is_dir():
            filename = spec["dit_filename"]
            if kind == "klein" and selected == "distilled":
                filename = filename.replace("-base-", "-")
            path = path / filename
            if not path.is_file():
                raise ValueError(f"DiT 文件不存在: {path}")
        model["name_or_path"] = str(path)
        te = str(absolute(source.get("text_encoder_path") or source.get("text_encoder"), root))
        vae_raw = source.get("vae_path") or (path.parent / "ae.safetensors" if kind == "klein" else None)
        vae = str(absolute(vae_raw, root))
        assets.update(dit=str(path), text_encoder=te, vae=vae, model_variant=selected)
        if kind == "klein":
            model["vae_path"] = vae
            model["model_kwargs"]["match_target_res"] = False
        else:
            model["model_kwargs"].update(text_encoder_path=te, vae_path=vae)
    elif mode == "single_file":  # SDXL checkpoint plus local Diffusers configs/tokenizers
        extras = str(absolute(source.get("model_config_dir"), root))
        model["extras_name_or_path"] = extras
        model["model_kwargs"]["next_trainer_sdxl_config"] = extras
        assets["config_dir"] = extras
    elif mode == "comfyui_files":  # Qwen 2.1 native component loaders
        extras = str(absolute(source.get("model_config_dir"), root))
        components = {"transformer": str(path), "text_encoder": str(absolute(source.get("text_encoder_path"), root)),
                      "vae": str(absolute(source.get("vae_path"), root))}
        model["extras_name_or_path"] = extras
        model["model_kwargs"]["next_trainer_components"] = components
        assets.update(config_dir=extras, components=components)
    return model, te, assets


def _config(path):
    if not path.is_file():
        raise ValueError(f"模型目录缺少配置: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"模型配置格式错误: {path}")
    return value


def validate_assets(assets):
    spec = MODELS[assets["variant"]]
    kind = assets["family"]
    if kind in {"klein", "krea2"}:
        safetensors_header(Path(assets["dit"]))
        te = Path(assets["text_encoder"])
        cfg = _config(te / "config.json")
        _config(te / "tokenizer_config.json")
        _config(te / "tokenizer.json")
        local_weights(te)
        if kind == "klein":
            expected = spec["te_hidden_size"]
            if cfg.get("hidden_size") != expected:
                raise ValueError(f"文本编码器与变体不匹配: {te}，要求 hidden_size={expected}")
            safetensors_header(Path(assets["vae"]))
        else:
            vae = Path(assets["vae"])
            if (vae / "vae").is_dir():
                vae = vae / "vae"
            _config(vae / "config.json")
            local_weights(vae)
        return
    base = Path(assets.get("config_dir") or assets["source"])
    _config(base / "model_index.json")
    for component in spec["components"]:
        _config(base / component / "config.json")
        if assets["mode"] == "model_directory":
            local_weights(base / component)
    for folder in spec["tokenizers"]:
        directory = base / folder
        _config(directory / "tokenizer_config.json")
        if not (directory / "tokenizer.json").is_file() and not (directory / "vocab.json").is_file() and not (directory / "spiece.model").is_file():
            raise ValueError(f"模型目录缺少 tokenizer 词表: {directory}")
    if assets["mode"] == "single_file":
        safetensors_header(Path(assets["source"]))
    for path in assets.get("components", {}).values():
        safetensors_header(Path(path))
