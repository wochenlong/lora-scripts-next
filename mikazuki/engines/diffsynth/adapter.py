"""UI configuration -> official Qwen-Image-2.1 arguments and dataset metadata."""
from dataclasses import dataclass
from pathlib import Path
import json
import math
from .inputs import absolute, model_inputs, dataset_inputs
from .samples import sample_config

@dataclass
class AdaptedConfig:
    arguments: dict
    dataset: list
    output_path: Path
    engine: dict
    metadata_path: Path | None


def positive_int(config, key, default):
    value = config.get(key, default)
    number = int(value)
    if number < 1 or float(value) != number:
        raise ValueError(f"{key} 必须为正整数")
    return number


def adapt_config(config, runtime):
    for field in ("output_dir", "output_name"):
        if not str(config.get(field, "")).strip():
            raise ValueError(f"缺少必填参数: {field}")
    models, processor = model_inputs(config, runtime.project_root)
    dataset_dir, metadata, rows = dataset_inputs(config, runtime.project_root)
    name = str(config["output_name"])
    if name in {".", ".."} or any(c in name for c in '/\\:'):
        raise ValueError("输出名称应为文件夹名称，不能包含路径分隔符")
    output = absolute(config["output_dir"], runtime.project_root) / name
    lr = float(config.get("learning_rate", 1e-4))
    if not math.isfinite(lr) or lr <= 0:
        raise ValueError("学习率必须为正数")
    rank = positive_int(config, 'lora_rank', 32)
    alpha = float(config['lora_alpha']) if config.get('lora_alpha') not in (None, '') else float(rank)
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError('LoRA Alpha 必须是有限正数')
    optimizer = config.get('optimizer_type', 'AdamW')
    optimizers = {'AdamW': 'torch.optim.AdamW', 'AdamW8bit': 'bitsandbytes.optim.AdamW8bit'}
    if optimizer not in optimizers:
        raise ValueError('不支持的优化器，请选择 AdamW 或 AdamW8bit')
    from .buckets import bucket_settings, dataset_buckets
    buckets = bucket_settings(config)
    batch_size = positive_int(config, 'train_batch_size', 1)
    arguments = {
        "dataset_base_path": str(dataset_dir),
        "data_file_keys": "image",
        "dataset_repeat": positive_int(config, "dataset_repeat", 1) if config.get("dataset_format", "image_text") == "image_text" else 1,
        # The upstream collate lambda is not spawn-picklable on Windows.
        "dataset_num_workers": 0,
        "model_paths": json.dumps([model["files"] for model in models], ensure_ascii=False),
        "processor_path": str(processor),
        "max_pixels": buckets['max_pixels'],
        "learning_rate": lr,
        "num_epochs": positive_int(config, "num_epochs", 5),
        "gradient_accumulation_steps": positive_int(config, "gradient_accumulation_steps", 1),
        "output_path": str(output),
        "remove_prefix_in_ckpt": "pipe.dit.",
        "lora_base_model": "dit",
        # Empty selects upstream auto-detection, not the parser's legacy q,k,v default.
        "lora_target_modules": str(config.get("lora_target_modules", "")),
        "lora_rank": rank,
        "customized_optimizer": optimizers[optimizer],
        "enable_tensorboard_log": True,
        "enable_csv_log": True,
        "find_unused_parameters": True,
    }
    for key, default in (("use_gradient_checkpointing", True), ("use_gradient_checkpointing_offload", False), ("initialize_model_on_cpu", True), ("enable_model_cpu_offload", False)):
        arguments[key] = bool(config.get(key, default))
    if config.get("save_steps"):
        arguments["save_steps"] = positive_int(config, "save_steps", 100)
    if config.get("lora_checkpoint"):
        checkpoint = absolute(config["lora_checkpoint"], runtime.project_root)
        if not checkpoint.is_file():
            raise ValueError(f"LoRA 权重不存在: {checkpoint}")
        arguments["lora_checkpoint"] = str(checkpoint)
    if config.get("diffsynth_quantization", "none") != "none":
        raise ValueError("首版仅支持 BF16 模型，不支持量化训练")
    samples = sample_config(config)
    cache_embeddings = bool(config.get('cache_embeddings', False))
    if batch_size > 1 and not cache_embeddings:
        raise ValueError('真实 batch size 大于 1 时请开启预编码缓存，以便对 latent 和文本特征按桶组批')
    sizes, batches_per_epoch, bucket_summary = dataset_buckets(rows, dataset_dir, buckets, arguments['dataset_repeat'], batch_size)
    from .lr_schedule import schedule_config
    total_steps = math.ceil(batches_per_epoch / arguments['gradient_accumulation_steps']) * arguments['num_epochs']
    schedule = schedule_config(config, total_steps)
    if samples["enabled"] and arguments["enable_model_cpu_offload"] and not cache_embeddings:
        raise ValueError("模型 CPU 卸载与训练预览同时使用时，请开启预编码缓存；否则请关闭预览或关闭模型 CPU 卸载。")
    engine = {"models": models, "cache_dir": str(runtime.root / "cache" / "models"), "samples": samples, "output_name": name,
              "cache_embeddings": cache_embeddings, "lora_alpha": alpha, "lr_schedule": schedule,
              "bucket_settings": buckets, "bucket_sizes": sizes, "bucket_summary": bucket_summary,
              "train_batch_size": batch_size, "batches_per_epoch": batches_per_epoch}
    return AdaptedConfig(arguments, rows, output, engine, metadata)


def dump_config(adapted, autosave_dir, run_id):
    directory = Path(autosave_dir)
    directory.mkdir(parents=True, exist_ok=True)
    metadata = adapted.metadata_path
    if metadata is None:
        metadata = directory / f"{run_id}-dataset.json"
        metadata.write_text(json.dumps(adapted.dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    adapted.arguments["dataset_metadata_path"] = str(metadata.resolve())
    config_path = directory / f"{run_id}-arguments.json"
    config_path.write_text(json.dumps({"arguments": adapted.arguments, **adapted.engine}, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path
