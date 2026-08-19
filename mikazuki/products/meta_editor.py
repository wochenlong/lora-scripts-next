"""Safetensors metadata viewer/editor.

Only the header ``__metadata__`` section is rewritten; tensor bytes are
copied through untouched. The original file is backed up to ``<name>.bak``
(once) before the first edit. Non-safetensors files are rejected.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict

from mikazuki.utils.train_utils import read_safetensors_metadata


class MetadataEditError(ValueError):
    pass


def read_metadata(path: str) -> Dict[str, str]:
    header = read_safetensors_metadata(path) or {}
    meta = header.get("__metadata__", {}) if isinstance(header, dict) else {}
    return dict(meta)


def _coerce_metadata(metadata: dict) -> Dict[str, str]:
    """safetensors metadata is str->str; coerce scalars, JSON-encode the rest."""
    clean: Dict[str, str] = {}
    for key, value in (metadata or {}).items():
        key = str(key).strip()
        if not key:
            continue
        if isinstance(value, str):
            clean[key] = value
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[key] = "" if value is None else str(value)
        else:
            clean[key] = json.dumps(value, ensure_ascii=False)
    return clean


def write_metadata(path: str, metadata: dict) -> dict:
    p = Path(path)
    if p.suffix.lower() != ".safetensors":
        raise MetadataEditError("只有 .safetensors 文件支持编辑 metadata")
    if not p.is_file():
        raise MetadataEditError(f"文件不存在: {path}")

    header = read_safetensors_metadata(str(p))
    if header is None:
        raise MetadataEditError(f"无法读取文件头: {path}")
    old_len = None
    with open(p, "rb") as f:
        old_len = int.from_bytes(f.read(8), "little")

    new_header = {k: v for k, v in header.items() if k != "__metadata__"}
    clean = _coerce_metadata(metadata)
    if clean:
        new_header["__metadata__"] = clean
    payload = json.dumps(new_header, ensure_ascii=False).encode("utf-8")

    backup = p.with_name(p.name + ".bak")
    if not backup.exists():
        shutil.copy2(p, backup)

    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "wb") as out:
        out.write(len(payload).to_bytes(8, "little"))
        out.write(payload)
        with open(p, "rb") as src:
            src.seek(8 + old_len)
            shutil.copyfileobj(src, out)
    os.replace(tmp, p)
    return {"backup": str(backup), "keys": len(clean)}
