"""Qwen 2.1 BF16 Comfy-Org -> pinned DiffSynth layouts and native Comfy LoRA.

Only tensor names, the fused MLP row split and singleton VAE time axis change.
No model implementation is copied from either trainer.
"""
import hashlib
import re
import math

MODEL_HASHES = {
    'dit_path': '4c9f4f5bdeb5c737742ad8e4080221d1',
    'text_encoder_path': '2d11bf14bba8b4e87477c8199a895403',
    'vae_path': '959403bfea52f7c5a3ccf82274f7e9ef',
}


def layout_hash(headers):
    keys = [item for key, info in headers.items() for item in (key, key + ':' + '_'.join(map(str, info['shape'])))]
    return hashlib.md5(','.join(sorted(keys)).encode()).hexdigest()


def vae_key(key):
    if key.startswith('conv1.'):
        return key.replace('conv1.', 'quant_conv.', 1)
    if key.startswith('conv2.'):
        return key.replace('conv2.', 'post_quant_conv.', 1)
    key = re.sub(r'^(encoder|decoder)\.conv1\.', r'\1.conv_in.', key)
    key = key.replace('.head.0.', '.norm_out.').replace('.head.2.', '.conv_out.')
    for source, target in (('0', 'resnets.0'), ('1', 'attentions.0'), ('2', 'resnets.1')):
        key = key.replace(f'.middle.{source}.', f'.mid_block.{target}.')
    for direction, count in (('down', 2), ('up', 3)):
        key = re.sub(rf'\.{direction}samples\.(\d+)\.{direction}samples\.(\d+)\.',
                     lambda m: f'.{direction}_blocks.{m[1]}.' + (f'{direction}sampler.' if int(m[2]) == count else f'resnets.{m[2]}.'), key)
    for source, target in (('0', 'norm1'), ('2', 'conv1'), ('3', 'norm2'), ('6', 'conv2')):
        key = key.replace(f'.residual.{source}.', f'.{target}.')
    return key.replace('.shortcut.', '.conv_shortcut.')


def conversion_plan(headers, component):
    """Return target -> (source, operation), plus normalized header shapes."""
    native = layout_hash(headers) == MODEL_HASHES[component]
    plan, normalized = {}, {}
    for key, info in headers.items():
        shape = list(info['shape'])
        targets = [(key, 'identity', shape)]
        if not native:
            if component == 'dit_path' and key.endswith('.img_mlp.gate_up.weight'):
                if shape[0] % 2:
                    raise ValueError('gate_up 权重行数必须为偶数')
                targets = [(key.replace('.gate_up.', f'.{name}.'), operation, [shape[0] // 2, *shape[1:]]) for name, operation in [('gate_layer', 'first_half'), ('proj', 'second_half')]]
            elif component == 'text_encoder_path' and key.startswith(('model.layers.', 'model.embed_tokens.', 'model.norm.')):
                targets = [('model.language_model.' + key[len('model.'):], 'identity', shape)]
            elif component == 'vae_path':
                squeeze = len(shape) == 5 and shape[2] == 1
                targets = [(vae_key(key), 'squeeze_time' if squeeze else 'identity', shape[:2] + shape[3:] if squeeze else shape)]
        for target, operation, result_shape in targets:
            if target in plan:
                raise ValueError(f'转换后权重名称重复: {target}')
            plan[target] = [key, operation]
            normalized[target] = {'shape': result_shape}
    if layout_hash(normalized) != MODEL_HASHES[component]:
        raise ValueError('权重结构不是受支持的 Qwen-Image-2.1 / Qwen3-VL-8B 模型（键名或尺寸不匹配）')
    return plan


def export_comfy_lora(state_dict, alpha=None):
    """PEFT default adapter -> Comfy's native lora_A/B and optional alpha tensors.

    Keep gate_layer/proj separate: Comfy's QwenImage mapping applies each LoRA
    to the corresponding half of its fused gate_up weight.
    """
    result = {}
    for key, tensor in state_dict.items():
        key = key.removeprefix('pipe.dit.').replace('.lora_A.default.', '.lora_A.').replace('.lora_B.default.', '.lora_B.')
        if not key.endswith(('.lora_A.weight', '.lora_B.weight')):
            raise ValueError(f'非 LoRA 权重不能导出: {key}')
        result[key] = tensor.detach().cpu().contiguous()
    if not result:
        raise ValueError('没有可保存的 LoRA 权重，请检查目标层')
    for key, down in list(result.items()):
        if key.endswith('.lora_A.weight'):
            base = key.removesuffix('.lora_A.weight')
            up = result[base + '.lora_B.weight']
            if down.ndim != 2 or up.ndim != 2 or up.shape[1] != down.shape[0]:
                raise ValueError(f'LoRA 矩阵尺寸不匹配: {base}')
    if sum(k.endswith('.lora_A.weight') for k in result) * 2 != len(result):
        raise ValueError('LoRA A/B 权重不成对')
    if alpha is not None:
        import torch
        for key in list(result):
            if key.endswith('.lora_A.weight'):
                result[key.removesuffix('.lora_A.weight') + '.alpha'] = torch.tensor(float(alpha))
    return result


def prepare_lora_checkpoint(weights, rank, alpha):
    """Keep the effective LoRA delta when resuming with a different alpha."""
    weights = {k.replace('.lora_A.default.', '.lora_A.').replace('.lora_B.default.', '.lora_B.'): v
               for k, v in weights.items()}
    for key in list(weights):
        if key.endswith('.lora_B.weight'):
            base = key.removesuffix('.lora_B.weight')
            source_rank = weights[base + '.lora_A.weight'].shape[0]
            if source_rank != rank:
                raise ValueError('继续训练的 LoRA Rank 与当前配置不一致')
            source_alpha = float(weights.get(base + '.alpha', source_rank))
            if not math.isfinite(source_alpha) or source_alpha <= 0:
                raise ValueError('LoRA 文件中的 Alpha 必须为有限正数')
            weights[key] = weights[key] * (source_alpha / alpha)
    return {k: v for k, v in weights.items() if not k.endswith('.alpha')}
