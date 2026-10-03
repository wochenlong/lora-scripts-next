"""Workbench fields -> pinned AI Toolkit configuration, with explicit semantics."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import math
import re

import yaml
from .capabilities import MODELS as VARIANTS, family
from .model_inputs import absolute, model_inputs
from .settings import RuntimeConfig

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.avif'}
OPTIMIZER_MAP = {'adamw': 'adamw', 'adamw8bit': 'adamw8bit', 'adamw_torch': 'adamw', 'adafactor': 'adafactor'}
SAVE_DTYPE_MAP = {'bf16': 'bf16', 'fp16': 'float16', 'float': 'float32', 'float32': 'float32', 'float16': 'float16'}


@dataclass
class AdaptedConfig:
    config: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    te_path: str = ''
    dataset_manifests: dict[str, dict] = field(default_factory=dict)


class AdapterError(ValueError):
    pass


def number(source, key, default, minimum=0, maximum=None, integer=False):
    value = source.get(key, default)
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise AdapterError(f'{key} 必须是有效数值') from None
    if isinstance(value, bool) or not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum) or (integer and result != int(result)):
        raise AdapterError(f'{key} 超出范围或不是有效{"整数" if integer else "数值"}')
    return int(result) if integer else result


def boolean(source, key, default=False):
    value = source.get(key, default)
    if value in (True, 'true', 'True', 1, '1'):
        return True
    if value in (False, 'false', 'False', 0, '0'):
        return False
    raise AdapterError(f'{key} 必须为布尔值')


def choice(source, key, choices, default):
    value = source.get(key, default)
    if value not in choices:
        raise AdapterError(f'{key} 不支持 {value!r}，可选: {", ".join(choices)}')
    return value


def _resolution(value):
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split('[x,]', str('1024' if value is None else value).replace(' ', ''))
    if not parts:
        raise AdapterError('resolution 至少需要一个分辨率')
    result = [number({'resolution': p}, 'resolution', 1024, 64, 4096, True) for p in parts]
    if any(p % 64 for p in result):
        raise AdapterError('resolution 必须为 64 的倍数')
    # Preserve the historical width,height contract; native array is explicit.
    return sorted(set(result)) if isinstance(value, list) else [max(result)]


def _datasets(source, runtime, spec, run_id):
    base = absolute(source.get('train_data_dir'), runtime.lora_next_root)
    if not base.is_dir():
        raise AdapterError(f'训练数据集路径不存在: {base}')
    controls = source.get('control_data_dirs') or []
    if isinstance(controls, str):
        controls = [p.strip() for p in controls.splitlines() if p.strip()]
    if not isinstance(controls, list) or any(not isinstance(p, str) or not p.strip() for p in controls):
        raise AdapterError('control_data_dirs 必须是非空目录数组')
    task = choice(source, 'training_task', ['text-to-image', 'image-edit'], 'image-edit' if controls else 'text-to-image')
    editing = task == 'image-edit'
    if editing and not spec.get('editing'):
        raise AdapterError(f'{spec["label"]} 首版不支持图像编辑')
    if editing and not 1 <= len(controls) <= 5:
        raise AdapterError('图像编辑需要 1–5 个 control_data_dirs 参考图目录')
    if not editing and controls:
        raise AdapterError('文生图不能提交 control_data_dirs；请切换图像编辑')
    controls = [absolute(p, runtime.lora_next_root) for p in controls]
    for directory in controls:
        if not directory.is_dir() or directory.is_relative_to(base) or base.is_relative_to(directory):
            raise AdapterError(f'参考图目录必须存在且与目标图目录互不包含: {directory}')
    common = {
        'caption_ext': str(source.get('caption_extension') or '.txt').lstrip('.'),
        'caption_dropout_rate': number(source, 'caption_dropout_rate', 0, 0, 1),
        'shuffle_tokens': boolean(source, 'shuffle_caption'),
        'cache_latents_to_disk': boolean(source, 'cache_latents_to_disk', True),
        'resolution': _resolution(source.get('resolution')),
    }
    if not common['caption_ext'] or '/' in common['caption_ext'] or '\\' in common['caption_ext']:
        raise AdapterError('caption_extension 不能为空或包含路径分隔符')
    repeats = number(source, 'dataset_repeats', 1, 1, integer=True)
    groups = {}
    for image in sorted(base.rglob('*')):
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTS:
            continue
        if not image.resolve().is_relative_to(base):
            raise AdapterError(f'数据集图片路径越界: {image}')
        relative = image.relative_to(base)
        if any(part.startswith('.') for part in relative.parts):
            continue
        for directory in controls:
            candidates = [p for p in (directory / relative.parent).glob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stem == image.stem]
            if len(candidates) != 1:
                raise AdapterError(f'参考图须按相对目录及同名文件配对: {directory / relative}，找到 {len(candidates)} 个候选')
            if not candidates[0].resolve().is_relative_to(directory):
                raise AdapterError(f'参考图路径越界: {candidates[0]}')
        groups.setdefault(image.parent, []).append(image)
    if not groups:
        raise AdapterError(f'数据集目录没有图片: {base}')
    entries = []
    manifests = {}
    for index, (directory, images) in enumerate(groups.items()):
        relative = directory.relative_to(base)
        repeat = repeats
        for part in relative.parts:
            match = re.match(r'^(\d+)_', part)
            if match:
                repeat *= int(match[1])
        if repeat < 1:
            raise AdapterError('数据集重复次数必须为正整数')
        entry = {**common, 'folder_path': str(directory), 'num_repeats': repeat}
        # Native caption JSON restricts each entry to its own images, retaining
        # nested repeat semantics without copying or moving user data.
        manifest = str(runtime.cache_dir / 'datasets' / f'{run_id}-{index}.json')
        entry['dataset_path'] = manifest
        manifests[manifest] = {}
        for image in images:
            caption = image.with_suffix('.' + common['caption_ext'])
            if not caption.resolve().is_relative_to(base):
                raise AdapterError(f'数据集标注路径越界: {caption}')
            manifests[manifest][str(image)] = {'caption': caption.read_text(encoding='utf-8-sig').strip() if caption.is_file() else ''}
        if controls:
            entry['control_path'] = [str(d / relative) for d in controls]
        entries.append(entry)
    return entries, task, manifests


def _samples(source, runtime, editing, multiple=16):
    if source.get('prompt_file') or source.get('sample_prompts'):
        raise AdapterError('请先将外部 Prompt 文件转换为 preview_samples，避免丢失逐样例参数')
    raw = source.get('preview_samples')
    if raw is not None:
        if not isinstance(raw, list):
            raise AdapterError('preview_samples 必须是样例数组')
        samples = []
        for value in raw:
            try:
                item = json.loads(value) if isinstance(value, str) else value
            except (ValueError, TypeError):
                raise AdapterError('预览样例 JSON 无效') from None
            if not isinstance(item, dict) or not isinstance(item.get('prompt'), str) or not item['prompt'].strip():
                raise AdapterError('预览样例必须填写 prompt')
            sample = {'prompt': item['prompt']}
            for key, default, minimum, integer in [('width', 1024, 64, True), ('height', 1024, 64, True), ('seed', 42, 0, True), ('guidance_scale', 4, 0, False), ('sample_steps', 20, 1, True)]:
                sample[key] = number(item, key, default, minimum, integer=integer)
            if sample['width'] % multiple or sample['height'] % multiple:
                raise AdapterError(f'预览图宽高必须为 {multiple} 的倍数')
            refs = item.get('controlImages', [])
            if not isinstance(refs, list) or len(refs) > 3:
                raise AdapterError('上游预览最多支持 3 张参考图')
            if refs and not editing:
                raise AdapterError('文生图预览不能携带参考图')
            if editing and not refs:
                raise AdapterError('图像编辑预览需要参考图')
            for i, value in enumerate(refs, 1):
                path = absolute(value, runtime.lora_next_root)
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                    raise AdapterError(f'预览参考图不存在或格式错误: {path}')
                sample[f'ctrl_img_{i}'] = str(path)
            samples.append(sample)
        if not samples:
            raise AdapterError('启用预览至少需要一个样例')
        return samples
    prompts = str(source.get('positive_prompts') or '').strip().splitlines()
    prompts = [p.strip() for p in prompts if p.strip()]
    if not prompts:
        raise AdapterError('启用预览必须填写提示词或 preview_samples')
    samples = [{'prompt': p, 'width': source.get('sample_width', 1024), 'height': source.get('sample_height', 1024),
                'seed': source.get('sample_seed', source.get('seed', 42)), 'guidance_scale': source.get('sample_cfg', 4),
                'sample_steps': source.get('sample_steps', 20)} for p in prompts]
    return _samples({**source, 'preview_samples': samples}, runtime, editing, multiple)


def adapt_config(source: dict, runtime: RuntimeConfig, run_id: str, variant: str) -> AdaptedConfig:
    if variant not in VARIANTS:
        raise AdapterError(f'未知 AI Toolkit 变体: {variant}')
    spec = VARIANTS[variant]
    warnings = []
    try:
        model, te, assets = model_inputs(source, runtime.lora_next_root, variant)
        datasets, task, manifests = _datasets(source, runtime, spec, run_id)
    except (ValueError, OSError) as exc:
        raise AdapterError(str(exc)) from exc
    if not source.get('max_train_steps'):
        raise AdapterError('AI Toolkit 只支持按步数 max_train_steps 训练，不支持 epoch')
    steps = number(source, 'max_train_steps', 0, 1, integer=True)
    for key in ('max_train_epochs', 'save_every_n_epochs', 'sample_every_n_epochs'):
        if source.get(key):
            raise AdapterError(f'AI Toolkit 不支持 {key}，请使用 steps 参数')
    name = str(source.get('output_name') or run_id).strip()
    if not name or name in {'.', '..'} or any(c in name for c in '/\\:') or any(ord(c) < 32 for c in name):
        raise AdapterError('output_name 不能为空或包含路径分隔符、控制字符')
    def path(key, default):
        return str(absolute(source.get(key) or default, runtime.lora_next_root))
    quantize = boolean(source, 'quantize', spec.get('quantization', True))
    quantize_te = boolean(source, 'quantize_te', quantize)
    if spec.get('quantization') is False and (quantize or quantize_te):
        raise AdapterError('SDXL 首版不支持量化')
    qtype = choice(source, 'qtype', ['qfloat8', 'qint8', 'qint4'], 'qfloat8')
    model.update(quantize=quantize, quantize_te=quantize_te, qtype=qtype, qtype_te=qtype,
                 low_vram=boolean(source, 'low_vram'), layer_offloading=boolean(source, 'layer_offloading'))
    optimizer = str(source.get('optimizer_type') or 'AdamW8bit').lower()
    if optimizer not in OPTIMIZER_MAP:
        raise AdapterError(f'不支持 optimizer_type={optimizer}')
    train = {
        'steps': steps, 'batch_size': number(source, 'train_batch_size', 1, 1, integer=True),
        'gradient_accumulation_steps': number(source, 'gradient_accumulation_steps', 1, 1, integer=True),
        'gradient_checkpointing': boolean(source, 'gradient_checkpointing', True),
        'noise_scheduler': spec.get('scheduler', 'flowmatch'), 'timestep_type': 'weighted',
        'optimizer': OPTIMIZER_MAP[optimizer], 'lr': number(source, 'learning_rate', 1e-4, 1e-12),
        'lr_scheduler': choice(source, 'lr_scheduler', ['constant', 'linear', 'cosine'], 'constant'),
        'dtype': choice(source, 'mixed_precision', ['bf16', 'fp16', 'float32'], 'bf16'),
        'max_grad_norm': number(source, 'max_grad_norm', 1, .001),
        'seed': number(source, 'seed', 42, 0, 2**32 - 1, integer=True),
        'train_unet': True, 'train_text_encoder': False,
    }
    if train['lr_scheduler'] == 'linear':
        train['lr_scheduler_params'] = {'start_factor': 1.0, 'end_factor': 0.0}
    if boolean(source, 'use_ema'):
        train['ema_config'] = {'use_ema': True, 'ema_decay': number(source, 'ema_decay', .99, 0, 1)}
    rank = number(source, 'network_dim', 16, 1, integer=True)
    save = {'dtype': SAVE_DTYPE_MAP[choice(source, 'save_precision', list(SAVE_DTYPE_MAP), 'bf16')],
            'save_every': number(source, 'save_every_n_steps', 250, 1, integer=True),
            'max_step_saves_to_keep': number(source, 'save_last_n_steps', 4, 1, integer=True), 'push_to_hub': False}
    process = {'type': 'sd_trainer', 'training_folder': path('output_dir', runtime.output_dir),
               'device': 'cuda:0', 'log_dir': path('logging_dir', runtime.logging_dir),
               'logging': {'log_every': max(1, min(100, steps // 100))},
               'network': {'type': 'lora', 'linear': rank, 'linear_alpha': number(source, 'network_alpha', rank, .001)},
               'save': save, 'datasets': datasets, 'train': train, 'model': model}
    if source.get('trigger_word'):
        process['trigger_word'] = str(source['trigger_word']).strip()
    preview = boolean(source, 'enable_preview', bool(source.get('preview_samples') or source.get('sample_prompts') or source.get('positive_prompts')))
    train['disable_sampling'] = not preview
    train['skip_first_sample'] = not boolean(source, 'sample_at_first')
    if preview:
        samples = _samples(source, runtime, task == 'image-edit', spec.get('sample_multiple', 16))
        process['sample'] = {
            'sampler': 'ddpm' if family(variant) == 'sdxl' else 'flowmatch',
            'sample_every': number(source, 'sample_every_n_steps', 250, 1, integer=True),
            'samples': samples, 'prompts': [s['prompt'] for s in samples],
            'width': number(source, 'sample_width', 1024, 64, integer=True),
            'height': number(source, 'sample_height', 1024, 64, integer=True),
            'seed': number(source, 'sample_seed', train['seed'], 0, integer=True), 'walk_seed': False,
            'guidance_scale': number(source, 'sample_cfg', 4, 0),
            'sample_steps': number(source, 'sample_steps', 20, 1, integer=True), 'neg': str(source.get('negative_prompts') or ''),
        }
    known = {'model_train_type', 'model_input_mode', 'model_path', 'model_config_dir', 'model_variant',
             'dit_path', 'text_encoder_path', 'vae_path', 'dit', 'text_encoder', 'pretrained_model_name_or_path',
             'train_data_dir', 'training_task', 'control_data_dirs', 'caption_extension', 'caption_dropout_rate',
             'shuffle_caption', 'cache_latents_to_disk', 'resolution', 'dataset_repeats', 'max_train_steps',
             'output_name', 'output_dir', 'logging_dir', 'quantize', 'quantize_te', 'qtype', 'low_vram', 'layer_offloading',
             'optimizer_type', 'train_batch_size', 'gradient_accumulation_steps', 'gradient_checkpointing', 'learning_rate',
             'lr_scheduler', 'mixed_precision', 'max_grad_norm', 'seed', 'use_ema', 'ema_decay', 'network_dim', 'network_alpha',
             'save_precision', 'save_every_n_steps', 'save_last_n_steps', 'trigger_word', 'enable_preview', 'sample_at_first',
             'sample_every_n_steps', 'preview_samples', 'sample_prompts', 'prompt_file', 'positive_prompts', 'negative_prompts',
             'sample_width', 'sample_height', 'sample_seed', 'sample_cfg', 'sample_steps', 'gpu_ids'}
    for key in source:
        if key not in known:
            warnings.append(f'AI Toolkit 未支持此字段，未传给上游: {key}')
    return AdaptedConfig({'job': 'extension', 'config': {'name': name, 'process': [process]},
                          'meta': {'name': name, 'version': '1.0', 'next_trainer': {'assets': assets, 'training_task': task}}}, warnings, te, manifests)


def dump_yaml(config):
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)


def write_job(adapted, yaml_path):
    for filename, items in adapted.dataset_manifests.items():
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Upstream reads manifests with the Windows locale encoding.
        path.write_text(json.dumps(items, ensure_ascii=True, indent=2), encoding='utf-8')
    Path(yaml_path).parent.mkdir(parents=True, exist_ok=True)
    Path(yaml_path).write_text(dump_yaml(adapted.config), encoding='utf-8')
