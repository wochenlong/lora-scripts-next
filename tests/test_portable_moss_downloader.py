import json
import runpy
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "portable" / "download_moss_model.py"
BAT = ROOT / "scripts" / "portable" / "templates" / "Download-MOSS-Model.bat"


def _write_safetensors(path, tensors):
    offset = 0
    header = {"__metadata__": {"format": "pt"}}
    payload = bytearray()
    for key, data in tensors.items():
        header[key] = {"dtype": "U8", "shape": [len(data)], "data_offsets": [offset, offset + len(data)]}
        payload.extend(data)
        offset += len(data)
    raw = json.dumps(header, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 8)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + payload)


def test_streaming_merge_header_keeps_tensor_offsets_and_payloads(tmp_path):
    mod = runpy.run_path(str(SCRIPT))
    first = tmp_path / "first.safetensors"
    second = tmp_path / "second.safetensors"
    _write_safetensors(first, {"a": b"abc"})
    _write_safetensors(second, {"b": b"12345"})
    parts = []
    sources = []
    for path in (first, second):
        header, header_end = mod["read_safetensors_header"](path)
        parts.append((header, path.stat().st_size - header_end))
        sources.append((path, header_end))
    output_header, boundaries = mod["merged_header"](parts)
    output = tmp_path / "merged.safetensors"
    with output.open("wb") as handle:
        handle.write(output_header)
        for path, header_end in sources:
            mod["append_safetensors_payload"](path, handle, header_end)
    header, header_end = mod["read_safetensors_header"](output)
    assert boundaries == [0, 3, 8]
    assert header["a"]["data_offsets"] == [0, 3]
    assert header["b"]["data_offsets"] == [3, 8]
    assert output.read_bytes()[header_end:] == b"abc12345"


def test_downloader_uses_modelscope_bf16_training_layout():
    mod = runpy.run_path(str(SCRIPT))
    assert mod["DIT"].repo == "Comfy-Org/MOSS-Image"
    assert mod["DIT"].path.endswith("moss_image_base_bf16.safetensors")
    assert mod["VAE"].path.endswith("flux2-vae_small.safetensors")
    assert all(item.repo == "openmoss/MOSS-Image-Base" for item in mod["TEXT_SHARDS"])
    serialized = SCRIPT.read_text(encoding="utf-8")
    assert "base_int8" not in serialized
    assert "w4a8" not in serialized


def test_portable_builder_bundles_moss_downloader_under_tools():
    bat = BAT.read_text(encoding="utf-8")
    builder = (ROOT / "build-scripts" / "build_portable.ps1").read_text(encoding="utf-8")
    root_layout = (ROOT / "build-scripts" / "apply_portable_2026_root.ps1").read_text(encoding="utf-8")
    assert "download_moss_model.py" in bat
    assert "python_embeded" in bat
    assert "Download-MOSS-Model.bat" in builder
    assert '"Download-MOSS-Model.bat"' in root_layout
