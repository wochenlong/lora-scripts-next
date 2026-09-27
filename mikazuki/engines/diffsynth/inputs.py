"""Local assets and metadata contracts; no model downloads or torch imports."""
import csv
import hashlib
import json
import math

from .formats import conversion_plan
import re
import struct
from pathlib import Path

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
PROCESSOR_FILES = ('tokenizer.json', 'tokenizer_config.json', 'preprocessor_config.json', 'chat_template.jinja', 'video_preprocessor_config.json')


class InputError(ValueError):
    def __init__(self, field, message, path=None):
        self.field, self.path = field, str(path) if path else None
        super().__init__(f'{field}: {message}' + (f' ({path})' if path else ''))


def absolute(value, root):
    path = Path(str(value)).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def required_path(config, key, root):
    if not str(config.get(key, '')).strip():
        raise InputError(key, '请填写路径')
    path = absolute(config[key], root)
    if not path.exists():
        raise InputError(key, '路径不存在', path)
    return path


def read_index(path, field):
    try:
        mapping = json.loads(path.read_text(encoding='utf-8'))['weight_map']
        if not isinstance(mapping, dict) or not mapping or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
            raise ValueError('weight_map 必须是非空的张量名到分片文件名映射')
        return mapping
    except (ValueError, KeyError, TypeError) as exc:
        raise InputError(field, f'无效分片索引: {exc}', path) from exc


def weight_files(path, field):
    """One explicit file, one index, or one unambiguous unsharded checkpoint."""
    if path.is_dir():
        indices = sorted(path.glob('*.safetensors.index.json'))
        files = sorted(path.glob('*.safetensors'))
        candidates = indices or files
        if len(candidates) != 1:
            raise InputError(field, '目录缺少权重或存在多个候选；请选择一个文件或索引', path)
        path = candidates[0]
        if indices:
            resolved = weight_files(path, field)
            indexed = {p.name for p in resolved}
            if {p.name for p in files} - indexed:
                raise InputError(field, '目录含索引之外的权重，请明确选择一个文件或索引', path.parent)
            return resolved
    if path.name.endswith('.safetensors.index.json'):
        names = sorted(set(read_index(path, field).values()))
        files = [(path.parent / name).resolve() for name in names]
        for file in files:
            if not file.is_relative_to(path.parent.resolve()):
                raise InputError(field, '分片索引路径越界', file)
            if not file.is_file():
                raise InputError(field, '模型分片缺失', file)
        return files
    if path.suffix != '.safetensors' or not path.is_file():
        raise InputError(field, '请选择 safetensors 文件或索引', path)
    # Selecting one shard resolves the complete indexed checkpoint automatically.
    indices = []
    for index in path.parent.glob('*.safetensors.index.json'):
        if path.name in read_index(index, field).values():
            indices.append(index)
    if len(indices) > 1:
        raise InputError(field, '分片属于多个索引，请明确选择索引', path)
    if indices:
        return weight_files(indices[0], field)
    if re.search(r'-\d{5}-of-\d{5}', path.name):
        raise InputError(field, '分片权重需要对应的索引文件', path)
    return [path]


def tensor_headers(files, field):
    result, owners = {}, {}
    for path in files:
        try:
            with path.open('rb') as stream:
                size = struct.unpack('<Q', stream.read(8))[0]
                if size > 100_000_000 or size > path.stat().st_size - 8:
                    raise ValueError('invalid header length')
                headers = json.loads(stream.read(size))
            headers.pop('__metadata__', None)
            for key, info in headers.items():
                if key in result:
                    raise ValueError(f'duplicate tensor: {key}')
                if info['dtype'] != 'BF16':
                    raise ValueError(f'{key}: {info["dtype"]}，首版仅支持 BF16')
                start, end = info['data_offsets']
                if start < 0 or end - start != math.prod(info['shape']) * 2 or end + 8 + size > path.stat().st_size:
                    raise ValueError(f'truncated tensor: {key}')
                result[key] = info
                owners[key] = path.name
            offset = 0
            for start, end in sorted(info['data_offsets'] for info in headers.values()):
                if start != offset:
                    raise ValueError('张量数据区域不连续或重叠')
                offset = end
            if offset + 8 + size != path.stat().st_size:
                raise ValueError('权重文件长度与张量数据不一致')
        except (OSError, ValueError, KeyError, struct.error) as exc:
            raise InputError(field, f'权重校验失败: {exc}', path) from exc
    if not result:
        raise InputError(field, '权重不包含张量')
    # Index must describe exactly the selected shards, not merely existing filenames.
    for index in files[0].parent.glob('*.safetensors.index.json'):
        mapping = read_index(index, field)
        if set(mapping.values()) == {p.name for p in files} and mapping != owners:
            raise InputError(field, '索引张量与分片内容不一致', index)
    return result


def model_inputs(config, root):
    mode = config.get('model_input_mode', 'directory')
    if mode == 'directory':
        directory = required_path(config, 'diffsynth_model_dir', root)
        selected = [('dit_path', directory / 'transformer'), ('text_encoder_path', directory / 'text_encoder'), ('vae_path', directory / 'vae')]
    elif mode == 'components':
        selected = [(key, required_path(config, key, root)) for key in ('dit_path', 'text_encoder_path', 'vae_path')]
    else:
        raise InputError('model_input_mode', '未知模型输入模式')
    models = []
    for key, path in selected:
        files = weight_files(path, key)
        headers = tensor_headers(files, key)
        try:
            plan = conversion_plan(headers, key)
        except ValueError as exc:
            raise InputError(key, str(exc), path) from exc
        models.append({'component': key, 'files': [str(p) for p in files], 'conversion': plan})
    from .processor import processor_directory
    # Preparation runs in the queued training child, with progress in its log.
    # Legacy UI processor_path values no longer override the managed location.
    return models, processor_directory(root)


def dataset_inputs(config, root):
    mode = config.get('dataset_format', 'image_text')
    if mode == 'image_text':
        base = required_path(config, 'train_data_dir', root)
        rows = []
        for image in sorted(base.rglob('*')):
            if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            caption = image.with_suffix('.txt')
            if not caption.is_file():
                raise InputError('train_data_dir', '缺少图片标注', caption)
            relative = image.relative_to(base)
            match = re.match(r'^(\d+)_', relative.parts[0]) if len(relative.parts) > 1 else None
            repeat = int(match[1]) if match else 1
            if repeat < 1:
                raise InputError('train_data_dir', '子目录重复次数必须大于 0', image.parent)
            # Empty TXT is an explicit empty prompt, not a missing caption.
            rows.extend([{'image': relative.as_posix(), 'prompt': caption.read_text(encoding='utf-8-sig').strip()}] * repeat)
        metadata = None
    elif mode == 'metadata':
        base = required_path(config, 'dataset_base_path', root)
        metadata = required_path(config, 'dataset_metadata_path', root)
        with metadata.open(encoding='utf-8-sig', newline='') as stream:
            if metadata.suffix.lower() == '.json':
                rows = json.load(stream)
            elif metadata.suffix.lower() == '.jsonl':
                rows = [json.loads(line) for line in stream if line.strip()]
            elif metadata.suffix.lower() == '.csv':
                rows = list(csv.DictReader(stream))
            else:
                raise InputError('dataset_metadata_path', '仅支持 CSV / JSON / JSONL', metadata)
        # This is preflight only. Training uses upstream UnifiedDataset with the original file.
        if not isinstance(rows, list):
            raise InputError('dataset_metadata_path', '元数据必须是记录列表', metadata)
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get('image'), str) or not isinstance(row.get('prompt'), str):
                raise InputError('dataset_metadata_path', f'第 {i + 1} 条需要 image 和 prompt 字符串', metadata)
            image = absolute(row['image'], base)
            if not image.is_file():
                raise InputError('dataset_metadata_path', f'第 {i + 1} 条图片不存在', image)
    else:
        raise InputError('dataset_format', '未知数据集格式')
    if not rows:
        raise InputError('train_data_dir' if mode == 'image_text' else 'dataset_metadata_path', '数据集没有图片')
    return base, metadata, rows


def cache_key(files):
    return hashlib.sha256(json.dumps([(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in map(Path, files)]).encode()).hexdigest()[:24]
