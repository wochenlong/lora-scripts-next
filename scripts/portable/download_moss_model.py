"""Download a training-compatible MOSS-Image Comfy layout from ModelScope."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


MODELSCOPE = "https://www.modelscope.cn/models"
CHUNK_SIZE = 16 * 1024 * 1024
USER_AGENT = "Next-Trainer-MOSS-Downloader/1.0"


@dataclass(frozen=True)
class RemoteFile:
    repo: str
    path: str
    size: int
    sha256: str

    @property
    def url(self) -> str:
        encoded = "/".join(urllib.parse.quote(part) for part in self.path.split("/"))
        return f"{MODELSCOPE}/{self.repo}/resolve/master/{encoded}"


DIT = RemoteFile(
    "Comfy-Org/MOSS-Image",
    "diffusion_models/moss_image_base_bf16.safetensors",
    10164655808,
    "cacd158728a1fb9e57c408a922b54752ec71fceb566b3821269927964e62b41f",
)
VAE = RemoteFile(
    "Comfy-Org/MOSS-Image",
    "vae/flux2-vae_small.safetensors",
    249521340,
    "d8d52ba036475f5fb07c8b435e176d3d97ebfa82f0d1a1c317f9cc1e25bd013b",
)
TEXT_SHARDS = (
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "text_encoder/model-00001-of-00004.safetensors",
        4973910744,
        "abfaa3d3a8612508c85ee8f6da9c734b862f10298b903765c4ad384177c32b0b",
    ),
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "text_encoder/model-00002-of-00004.safetensors",
        4988364288,
        "9112637fa6bf4d07bafd6ae268852b18d3d0c1242f4ee901c5579006e5bd4894",
    ),
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "text_encoder/model-00003-of-00004.safetensors",
        4954202112,
        "956f1ef51d0cfe610b0d22987c0b7821c36e3ce228abceccef523518bcf079dc",
    ),
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "text_encoder/model-00004-of-00004.safetensors",
        1869001848,
        "9e21d20e8adde88c3e0b65d4a0d251f143d98ee9d52db36b4348361091e4e208",
    ),
)
TOKENIZER_FILES = (
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "tokenizer/chat_template.jinja",
        7756,
        "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715",
    ),
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "tokenizer/tokenizer.json",
        19989325,
        "06b9509352d2af50381ab2247e083b80d32d5c0aba91c272ca9ff729b6a0e523",
    ),
    RemoteFile(
        "openmoss/MOSS-Image-Base",
        "tokenizer/tokenizer_config.json",
        1123,
        "bee8eba30f0eb4af73c0fe2cd06d0f89b657d7819941c438157ec42f7c80ea87",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_download(path: Path, spec: RemoteFile) -> bool:
    return path.is_file() and path.stat().st_size == spec.size and _sha256(path) == spec.sha256


def download(spec: RemoteFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _valid_download(destination, spec):
        print(f"[skip] {destination.name}")
        return
    if destination.exists():
        destination.unlink()
    partial = destination.with_name(destination.name + ".part")
    for attempt in range(1, 4):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > spec.size:
            partial.unlink()
            offset = 0
        request = urllib.request.Request(spec.url, headers={"User-Agent": USER_AGENT})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            mode = "ab" if offset else "wb"
            print(f"[download] {spec.path} ({offset / 1_000_000_000:.2f}/{spec.size / 1_000_000_000:.2f} GB)")
            with urllib.request.urlopen(request, timeout=60) as response, partial.open(mode) as output:
                if offset and response.status != 206:
                    output.close()
                    partial.unlink(missing_ok=True)
                    raise OSError("server did not honor the resume range")
                while chunk := response.read(CHUNK_SIZE):
                    output.write(chunk)
            if _valid_download(partial, spec):
                os.replace(partial, destination)
                return
            raise OSError("download size or SHA-256 mismatch")
        except (OSError, urllib.error.URLError) as exc:
            if attempt == 3:
                raise RuntimeError(f"download failed after {attempt} attempts: {spec.path}: {exc}") from exc
            print(f"[retry {attempt}/3] {exc}")
            time.sleep(attempt * 2)


def read_safetensors_header(path: Path) -> tuple[dict, int]:
    with path.open("rb") as handle:
        raw_size = handle.read(8)
        if len(raw_size) != 8:
            raise ValueError(f"invalid safetensors header: {path}")
        header_size = struct.unpack("<Q", raw_size)[0]
        header = json.loads(handle.read(header_size))
    return header, 8 + header_size


def fetch_safetensors_header(spec: RemoteFile) -> tuple[dict, int]:
    def ranged(start: int, end: int) -> bytes:
        request = urllib.request.Request(
            spec.url,
            headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 206:
                raise OSError(f"server did not honor header range for {spec.path}")
            return response.read()

    header_size = struct.unpack("<Q", ranged(0, 7))[0]
    header = json.loads(ranged(8, 7 + header_size))
    return header, 8 + header_size


def merged_header(parts: list[tuple[dict, int]]) -> tuple[bytes, list[int]]:
    merged: dict = {"__metadata__": {"format": "pt"}}
    boundaries = [0]
    offset = 0
    for header, payload_size in parts:
        for key, value in header.items():
            if key == "__metadata__":
                continue
            if key in merged:
                raise ValueError(f"duplicate tensor across text-encoder shards: {key}")
            item = dict(value)
            start, end = item["data_offsets"]
            item["data_offsets"] = [start + offset, end + offset]
            merged[key] = item
        offset += payload_size
        boundaries.append(offset)
    raw = json.dumps(merged, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    raw += b" " * (-len(raw) % 8)
    return struct.pack("<Q", len(raw)) + raw, boundaries


def append_safetensors_payload(source: Path, destination, header_end: int) -> None:
    with source.open("rb") as handle:
        handle.seek(header_end)
        while chunk := handle.read(CHUNK_SIZE):
            destination.write(chunk)


def merge_text_encoder(destination: Path, work_dir: Path) -> None:
    if destination.is_file():
        header, _ = read_safetensors_header(destination)
        embed = header.get("language_model.embed_tokens.weight", {})
        if embed.get("shape") == [248320, 4096]:
            print(f"[skip] {destination.name}")
            return
        destination.unlink()

    remote_parts = []
    header_ends = []
    for spec in TEXT_SHARDS:
        header, header_end = fetch_safetensors_header(spec)
        remote_parts.append((header, spec.size - header_end))
        header_ends.append(header_end)
    output_header, boundaries = merged_header(remote_parts)
    partial = destination.with_name(destination.name + ".part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    if not partial.exists() or partial.stat().st_size < len(output_header):
        partial.write_bytes(output_header)
    else:
        with partial.open("rb") as handle:
            if handle.read(len(output_header)) != output_header:
                partial.write_bytes(output_header)

    payload_written = partial.stat().st_size - len(output_header)
    completed = max((value for value in boundaries if value <= payload_written), default=0)
    if payload_written != completed:
        with partial.open("r+b") as handle:
            handle.truncate(len(output_header) + completed)

    work_dir.mkdir(parents=True, exist_ok=True)
    for index, (spec, header_end) in enumerate(zip(TEXT_SHARDS, header_ends)):
        if boundaries[index + 1] <= completed:
            continue
        shard = work_dir / Path(spec.path).name
        download(spec, shard)
        print(f"[merge] {shard.name}")
        with partial.open("ab") as output:
            append_safetensors_payload(shard, output, header_end)
        shard.unlink()
        completed = boundaries[index + 1]

    expected_size = len(output_header) + boundaries[-1]
    if partial.stat().st_size != expected_size:
        raise RuntimeError("merged text encoder has an unexpected size")
    header, _ = read_safetensors_header(partial)
    embed = header.get("language_model.embed_tokens.weight", {})
    if embed.get("shape") != [248320, 4096]:
        raise RuntimeError("merged text encoder is not the training-compatible Qwen3.5 layout")
    os.replace(partial, destination)


def validate_layout(model_dir: Path) -> None:
    checks = (
        ("dit.safetensors", "layers.0.proj.qkv.weight", [9216, 3072]),
        ("text_encoder.safetensors", "language_model.embed_tokens.weight", [248320, 4096]),
        ("vae.safetensors", "decoder.conv_in.weight", [384, 32, 3, 3]),
    )
    for filename, key, shape in checks:
        header, _ = read_safetensors_header(model_dir / filename)
        if header.get(key, {}).get("shape") != shape:
            raise RuntimeError(f"{filename}: incompatible MOSS training layout ({key})")
    for filename in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja"):
        if not (model_dir / "tokenizer" / filename).is_file():
            raise RuntimeError(f"tokenizer file missing: {filename}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    if not (project_root / "gui.py").is_file():
        raise RuntimeError(f"Next Trainer project root not found: {project_root}")
    model_dir = project_root / "sd-models" / "moss-image"
    model_dir.mkdir(parents=True, exist_ok=True)
    missing_bytes = sum(
        spec.size
        for spec, path in (
            (DIT, model_dir / "dit.safetensors"),
            (VAE, model_dir / "vae.safetensors"),
            *((spec, model_dir / "tokenizer" / Path(spec.path).name) for spec in TOKENIZER_FILES),
        )
        if not path.exists()
    )
    if not (model_dir / "text_encoder.safetensors").exists():
        missing_bytes += sum(spec.size for spec in TEXT_SHARDS)
    free = shutil.disk_usage(model_dir).free
    if free < missing_bytes + 6_000_000_000:
        raise RuntimeError(
            f"not enough free disk space: need about {(missing_bytes + 6_000_000_000) / 1e9:.1f} GB, "
            f"available {free / 1e9:.1f} GB"
        )

    print("MOSS-Image Base BF16 downloader (ModelScope CN)")
    print(f"Destination: {model_dir}")
    download(DIT, model_dir / "dit.safetensors")
    download(VAE, model_dir / "vae.safetensors")
    for spec in TOKENIZER_FILES:
        download(spec, model_dir / "tokenizer" / Path(spec.path).name)
    merge_text_encoder(model_dir / "text_encoder.safetensors", model_dir / ".download")
    validate_layout(model_dir)
    shutil.rmtree(model_dir / ".download", ignore_errors=True)
    manifest = {
        "format": "next-trainer-moss-comfy-v1",
        "source": "ModelScope",
        "variant": "base",
        "precision": "bf16",
        "files": {
            "dit.safetensors": DIT.sha256,
            "vae.safetensors": VAE.sha256,
            "text_encoder.safetensors": [item.sha256 for item in TEXT_SHARDS],
            "tokenizer": {Path(item.path).name: item.sha256 for item in TOKENIZER_FILES},
        },
    }
    (model_dir / "download-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Done. Select 'ComfyUI files' in KohakuMossTrainer; default paths are ready.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled. Run this downloader again to resume.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
