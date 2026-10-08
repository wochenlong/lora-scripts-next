"""Preserve Toolkit identities and legacy Klein paths through the shared importer."""
from pathlib import Path
import json
from .capabilities import MODELS, TRAIN_TYPES, family, schema_name
from .model_inputs import absolute

UI_FIELDS = set('''model_train_type model_input_mode model_path model_config_dir model_variant
dit_path text_encoder_path vae_path train_data_dir training_task control_data_dirs caption_extension
caption_dropout_rate shuffle_caption cache_latents_to_disk resolution dataset_repeats max_train_steps
output_name output_dir logging_dir quantize quantize_te qtype low_vram layer_offloading optimizer_type
train_batch_size gradient_accumulation_steps gradient_checkpointing learning_rate lr_scheduler
mixed_precision max_grad_norm seed use_ema ema_decay network_dim network_alpha save_precision
save_every_n_steps save_last_n_steps trigger_word enable_preview sample_at_first sample_every_n_steps
preview_samples negative_prompts gpu_ids'''.split())
LEGACY_FIELDS = set('''dit text_encoder pretrained_model_name_or_path positive_prompts sample_width
sample_height sample_seed sample_cfg sample_steps prompt_file sample_prompts ui_custom_params'''.split())


def validate_import(page, source):
    schemas = {schema_name(variant) for variant in MODELS}
    train_type = source.get('model_train_type')
    if train_type is not None and not isinstance(train_type, str):
        return {'result': 'reject', 'errors': ['model_train_type 必须是字符串']}
    if page not in schemas and page not in TRAIN_TYPES and train_type not in TRAIN_TYPES:
        return None
    if train_type not in TRAIN_TYPES:
        return {'result': 'reject', 'errors': ['请选择明确的 AI Toolkit model_train_type；不能自动把其他引擎参数转换为 Toolkit 配置']}
    variant = TRAIN_TYPES[train_type]
    target = schema_name(variant)
    if page not in {target, train_type}:
        return {'result': 'redirect', 'target_path': f'/training?model={family(variant)}&engine=ai-toolkit&target=lora',
                'target_train_type': train_type, 'config': dict(source), 'message': '此配置属于 AI Toolkit，请切换到对应模型与引擎'}
    config = dict(source)
    notices = []
    if 'enable_preview' not in config:
        config['enable_preview'] = bool(config.get('preview_samples') or config.get('positive_prompts') or config.get('prompt_file') or config.get('sample_prompts'))
    if config.get('ui_custom_params'):
        return {'result': 'reject', 'errors': ['请先将 ui_custom_params 展开为明确字段；不会静默忽略自定义训练参数']}
    for key in ('max_train_epochs', 'save_every_n_epochs', 'sample_every_n_epochs'):
        if config.get(key):
            return {'result': 'reject', 'errors': [f'AI Toolkit 不支持 {key}，请明确使用 steps 参数']}
    if not config.get('model_input_mode'):
        raw = config.get('dit') or config.get('pretrained_model_name_or_path')
        try:
            path = absolute(raw, Path.cwd())
        except ValueError as exc:
            return {'result': 'reject', 'errors': [str(exc)]}
        if not path.exists():
            return {'result': 'reject', 'errors': ['旧模型路径无法判断格式；请明确 model_input_mode 和本地路径，不会自动转换或下载']}
        directory = path.is_dir()
        config['model_input_mode'] = 'model_directory' if directory else 'single_file'
        config['model_path' if directory else 'dit_path'] = raw
        if config.get('text_encoder'):
            config['text_encoder_path'] = config['text_encoder']
        if variant.startswith('klein-') and not config.get('vae_path'):
            config['vae_path'] = str((path if directory else path.parent) / 'ae.safetensors')
        notices.append('已保留旧 Klein 本地路径并识别输入模式，请核对 VAE 路径')
    if config['model_input_mode'] not in MODELS[variant]['modes']:
        return {'result': 'reject', 'errors': [f"{MODELS[variant]['label']} 不支持 {config['model_input_mode']} 输入模式"]}
    if not config.get('preview_samples') and config.get('positive_prompts'):
        config['preview_samples'] = [json.dumps({'prompt': prompt.strip(),
            'width': config.get('sample_width', 1024), 'height': config.get('sample_height', 1024),
            'seed': config.get('sample_seed', 42), 'guidance_scale': config.get('sample_cfg', 4),
            'sample_steps': config.get('sample_steps', 20), 'controlImages': []}, ensure_ascii=False)
            for prompt in str(config['positive_prompts']).splitlines() if prompt.strip()]
    if config.get('prompt_file') or config.get('sample_prompts'):
        return {'result': 'reject', 'errors': ['旧配置使用外部 Prompt 文件；请先把文件内样例导入 preview_samples，以免丢失逐样例参数']}
    if config.get('control_data_dirs') and not config.get('training_task'):
        config['training_task'] = 'image-edit'
    unsupported = set(config) - UI_FIELDS - LEGACY_FIELDS
    if variant == 'sdxl':
        unsupported.update(key for key in ('quantize', 'quantize_te', 'qtype', 'low_vram', 'layer_offloading') if config.get(key))
    if variant != 'sdxl' and config.get('negative_prompts'):
        unsupported.add('negative_prompts')
    if not MODELS[variant].get('editing') and (config.get('control_data_dirs') or config.get('training_task') == 'image-edit'):
        return {'result': 'reject', 'errors': [f"{MODELS[variant]['label']} 首版只支持文生图"]}
    if unsupported:
        notices.append('当前表单不支持以下字段，提交时不会保留：' + ', '.join(sorted(unsupported)))
    return {'result': 'ok', 'config': config, 'notice': '；'.join(notices), 'forced_train_type': train_type}
