"""Read-only validation of local model assets; never download or rewrite weights."""
import json
import math
from pathlib import Path
import struct

# Safetensors Dtype bit widths, including packed low-precision formats.
DTYPE_BITS = {
    'BOOL': 8, 'U8': 8, 'I8': 8, 'F8_E5M2': 8, 'F8_E4M3': 8, 'F8_E4M3FN': 8, 'F8_E8M0': 8,
    'F8_E4M3FNUZ': 8, 'F8_E5M2FNUZ': 8, 'F4': 4, 'F6_E2M3': 6, 'F6_E3M2': 6,
    'I16': 16, 'U16': 16, 'F16': 16, 'BF16': 16, 'I32': 32, 'U32': 32, 'F32': 32,
    'C64': 64, 'F64': 64, 'I64': 64, 'U64': 64,
}


def safetensors_header(path: Path) -> dict:
    # Opening a FIFO or device before this check can block an API request.
    if not path.is_file():
        raise ValueError(f"模型权重必须是普通文件: {path}")
    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError(f"模型文件不是有效的 safetensors: {path}")
        size = struct.unpack("<Q", prefix)[0]
        if not 2 <= size <= min(100_000_000, path.stat().st_size - 8):
            raise ValueError(f"模型文件头损坏: {path}")
        header = json.loads(stream.read(size))
    if not isinstance(header, dict):
        raise ValueError(f"模型文件头格式错误: {path}")
    tensors = {key: value for key, value in header.items() if key != "__metadata__"}
    if not tensors:
        raise ValueError(f"模型文件没有权重: {path}")
    payload_size = path.stat().st_size - 8 - size
    spans = []
    for value in tensors.values():
        offsets = value.get("data_offsets", []) if isinstance(value, dict) else []
        if not isinstance(offsets, list) or len(offsets) != 2 or any(type(offset) is not int for offset in offsets) or not 0 <= offsets[0] <= offsets[1] <= payload_size:
            raise ValueError(f"模型权重数据不完整: {path}")
        dtype, shape = value.get('dtype'), value.get('shape')
        if not isinstance(dtype, str) or dtype not in DTYPE_BITS or not isinstance(shape, list) or any(type(dim) is not int or dim < 0 for dim in shape):
            raise ValueError(f"模型权重 dtype 或 shape 无效: {path}")
        bits = math.prod(shape) * DTYPE_BITS[dtype]
        if bits % 8 or bits // 8 != offsets[1] - offsets[0]:
            raise ValueError(f"模型权重形状与数据长度不符: {path}")
        spans.append(tuple(offsets))
    end = 0
    for start, stop in sorted(spans):
        if start != end:
            raise ValueError(f"模型权重数据有重叠或空洞: {path}")
        end = stop
    if end != payload_size:
        raise ValueError(f"模型权重数据长度不符: {path}")
    return tensors


def local_weights(directory: Path) -> list[Path]:
    """Check indexed shards without allowing an index to escape its component."""
    directory = directory.resolve()
    files = set(directory.glob("*.safetensors"))
    indexed_tensors = []
    for index in directory.glob("*.safetensors.index.json"):
        data = json.loads(index.read_text(encoding="utf-8"))
        mapping = data.get("weight_map") if isinstance(data, dict) else None
        if not isinstance(mapping, dict) or not mapping or any(not isinstance(name, str) for name in mapping.values()):
            raise ValueError(f"模型分片索引为空: {index}")
        for tensor, name in mapping.items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError(f"模型分片路径越界: {index}: {name}")
            if not path.is_file():
                raise ValueError(f"模型缺少分片: {path}")
            files.add(path)
            indexed_tensors.append((tensor, path))
    if not files:
        raise ValueError(f"模型目录缺少 *.safetensors 权重: {directory}")
    headers = {path: safetensors_header(path) for path in files}
    for tensor, path in indexed_tensors:
        if tensor not in headers[path]:
            raise ValueError(f"模型分片缺少索引中的权重 {tensor}: {path}")
    return sorted(files)
