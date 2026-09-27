"""Structured sample settings shared by preflight and the training callback."""
import json
import math

DEFAULT_SAMPLE = {'prompt': '', 'width': 1024, 'height': 1024, 'seed': 42, 'guidance_scale': 4, 'sample_steps': 20}


def sample_config(config):
    enabled = bool(config.get('sample_enabled', False))
    if not enabled:
        return {'enabled': False, 'every_steps': 100, 'samples': []}
    def positive_interval(value, name):
        try:
            if isinstance(value, bool) or int(value) != float(value) or int(value) < 1:
                raise ValueError()
            return int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f'{name} 必须为正整数') from exc
    raw_epochs = config.get('sample_every_n_epochs')
    every_epochs = None if raw_epochs is None or str(raw_epochs).strip() == '' else positive_interval(raw_epochs, 'sample_every_n_epochs')
    # An overridden step interval must not prevent epoch-based previews.
    interval = 100 if every_epochs is not None else positive_interval(config.get('sample_every_n_steps', 100), 'sample_every_n_steps')
    samples = config.get('preview_samples', [json.dumps(DEFAULT_SAMPLE)])
    if not samples:
        raise ValueError('至少需要一个预览样例')
    result = []
    for i, value in enumerate(samples):
        sample = json.loads(value)
        if not isinstance(sample, dict) or set(sample) - (set(DEFAULT_SAMPLE) | {'controlImages'}):
            raise ValueError(f'预览样例 {i + 1} 包含不支持的参数')
        if sample.pop('controlImages', []) != []:
            raise ValueError(f'预览样例 {i + 1}: 文生图不支持参考图，controlImages 必须为空数组')
        sample = {**DEFAULT_SAMPLE, **sample}
        if not isinstance(sample['prompt'], str):
            raise ValueError(f'预览样例 {i + 1} 的 prompt 必须是字符串')
        for key in ('width', 'height', 'seed', 'sample_steps'):
            number = sample[key]
            minimum = 0 if key == 'seed' else 1
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or int(number) != number or number < minimum:
                raise ValueError(f'预览样例 {i + 1}: {key} 必须是 >= {minimum} 的整数')
            sample[key] = int(number)
        if sample['width'] % 32 or sample['height'] % 32:
            raise ValueError('预览宽高必须是 32 的倍数')
        cfg = float(sample['guidance_scale'])
        if not math.isfinite(cfg) or cfg < 1:
            raise ValueError('预览 guidance_scale 必须 >= 1')
        sample['guidance_scale'] = cfg
        result.append(sample)
    return {'enabled': True, 'every_steps': interval, 'every_epochs': every_epochs, 'samples': result}
