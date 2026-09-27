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


def is_edit(config):
    task = config.get('training_task', 'text-to-image')
    if task not in ('text-to-image', 'image-edit'):
        raise InputError('training_task', '请选择 text-to-image 或 image-edit')
    return task == 'image-edit'


def reference_size(width, height, max_pixels):
    """Pinned ImageCropAndResize geometry (no fixed width/height in training args).

    Keep this lightweight for GUI preflight; parity is tested against upstream.
    """
    if width * height > max_pixels:
        scale = (width * height / max_pixels) ** 0.5
        height, width = int(height / scale), int(width / scale)
    return width // 32 * 32, height // 32 * 32


def reference_paths(value, base, field, checked=None, *, max_pixels=None, target_size=None):
    # CSV can hold a JSON array; JSON/JSONL also accept a single path.
    if isinstance(value, str):
        value = json.loads(value) if value.lstrip().startswith('[') else [value]
    if not isinstance(value, list) or not value or any(not isinstance(p, str) or not p.strip() for p in value):
        raise InputError(field, '至少需要一张参考图；填写路径或非空路径数组')
    paths = []
    from PIL import Image
    for item in value:
        path = absolute(item, base)
        if checked is not None and path in checked:
            width, height = checked[path]
        else:
            if not path.is_file():
                raise InputError(field, '参考图不存在', path)
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    image.verify()
            except (OSError, ValueError) as exc:
                raise InputError(field, '无法读取参考图', path) from exc
            if checked is not None:
                checked[path] = (width, height)
        resized = (width, height)
        if max_pixels is not None:
            resized = reference_size(width, height, max_pixels)
            if min(resized) == 0:
                raise InputError(field, f'参考图原始尺寸 {width}×{height}，按最大像素面积 '
                                 f'{max_pixels} 等比缩小并向下对齐到 32 像素后为 '
                                 f'{resized[0]}×{resized[1]}；处理后每边须至少为 32 像素，'
                                 '请调整参考图尺寸或比例', path)
        if target_size is not None:
            # Match the pinned Edit embedder before its minimum-area correction.
            # A reference reused by different target buckets must be checked again.
            ratio = resized[0] / resized[1]
            edit_width = math.sqrt(target_size[0] * target_size[1] * ratio)
            edit_size = (round(edit_width / 32) * 32, round(edit_width / ratio / 32) * 32)
            if min(edit_size) == 0:
                raise InputError(field, f'参考图原始尺寸 {width}×{height}，加载后为 '
                                 f'{resized[0]}×{resized[1]}，按目标尺寸 '
                                 f'{target_size[0]}×{target_size[1]} 再次缩放后为 '
                                 f'{edit_size[0]}×{edit_size[1]}；请增大目标尺寸或调整参考图比例', path)
        paths.append(str(path))
    return paths


def dataset_inputs(config, root):
    editing = is_edit(config)
    if editing:
        # The UI uses output/input terminology for Edit mode while the
        # backend keeps the original dataset contract for compatibility.
        if config.get("output_data_dir") and not config.get("train_data_dir"):
            config = {**config, "train_data_dir": config["output_data_dir"]}
        if config.get("input_data_dirs") is not None and config.get("control_data_dirs") is None:
            config = {**config, "control_data_dirs": config["input_data_dirs"]}
    checked = {}
    max_pixels = None
    if editing:
        from .buckets import bucket_settings, select_bucket
        settings = bucket_settings(config)
        max_pixels = settings['max_pixels']
        if max_pixels <= 0:
            raise InputError('max_pixels', '最大像素面积必须大于 0')
        from mikazuki.log import log
        log.info('Edit 数据预检：正在配对并检查参考图。')
    mode = config.get('dataset_format', 'image_text')
    if mode == 'image_text':
        base = required_path(config, 'train_data_dir', root)
        if not base.is_dir():
            raise InputError('train_data_dir', '请选择图片目录', base)
        controls = []
        if editing:
            raw = config.get('control_data_dirs')
            if not isinstance(raw, list) or not raw or any(not isinstance(p, str) or not p.strip() for p in raw):
                raise InputError('control_data_dirs', 'Edit 需要至少一个参考图目录')
            controls = [absolute(p, root) for p in raw]
            for directory in controls:
                if not directory.is_dir() or directory == base or directory.is_relative_to(base) or base.is_relative_to(directory):
                    raise InputError('control_data_dirs', '参考图目录必须存在，且与目标图目录互不包含', directory)
        reference_index = {}
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
            row = {'image': relative.as_posix(), 'prompt': caption.read_text(encoding='utf-8-sig').strip()}
            if editing:
                references = []
                for directory in controls:
                    parent = directory / relative.parent
                    if parent not in reference_index:
                        by_stem = {}
                        for candidate in parent.glob('*'):
                            if candidate.suffix.lower() in IMAGE_EXTENSIONS and candidate.is_file():
                                by_stem.setdefault(candidate.stem, []).append(candidate)
                        reference_index[parent] = by_stem
                    matches = reference_index[parent].get(image.stem, [])
                    if len(matches) != 1:
                        raise InputError('control_data_dirs', f'参考图须按相对目录及同名文件配对，找到 {len(matches)} 个候选', directory / relative)
                    references.append(str(matches[0]))
                row['edit_image'] = references
            rows.extend([row] * repeat)
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
    if editing:
        from PIL import Image
        target_sizes = {}
        for i, row in enumerate(rows):
            target = absolute(row['image'], base)
            if target not in target_sizes:
                with Image.open(target) as image:
                    target_sizes[target] = select_bucket(*image.size, settings)[0]
            row['edit_image'] = reference_paths(row.get('edit_image'), base, f'edit_image 第 {i + 1} 条', checked,
                                                max_pixels=max_pixels, target_size=target_sizes[target])
        # Normalize single paths / CSV arrays to the same upstream JSON contract.
        # Never overwrite the user's metadata.
        metadata = None
        log.info(f'Edit 数据预检完成：{len(rows)} 条样本（含目录重复），{len(checked)} 张独立参考图。')
    return base, metadata, rows


def cache_key(files):
    return hashlib.sha256(json.dumps([(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in map(Path, files)]).encode()).hexdigest()[:24]
