"""Default model assets per train type (presence check + download).

Generic across training backends: each train type registers its required base
models with default local paths and optional HuggingFace / ModelScope sources.

Repo ids can be overridden per asset in config/model_assets.toml:

    [krea2-lora.dit]
    hf_repo = "..."
    hf_file = "..."
    ms_repo = "..."
    ms_file = "..."
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import os

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib


CONFIG_PATH = Path("config/model_assets.toml")


@dataclass(frozen=True)
class AssetDef:
    key: str
    label: str
    default_path: str  # relative to project root; a directory for kind="dir"
    optional: bool = False
    kind: str = "file"  # "file" | "dir" (directory of loose files, e.g. tokenizer)
    hf_repo: str = ""
    hf_file: str = ""
    ms_repo: str = ""
    ms_file: str = ""


KREA2_REPO = "Comfy-Org/Krea-2"
QWEN3_VL_REPO = "Qwen/Qwen3-VL-4B-Instruct"
TOKENIZER_FILES = ["tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt"]
TOKENIZER_REQUIRED = ("tokenizer.json", "tokenizer_config.json")

ASSET_REGISTRY: dict[str, tuple[AssetDef, ...]] = {
    "krea2-lora": (
        AssetDef("dit", "Krea 2 DiT（RAW 底模）", "sd-models/krea2/krea2.safetensors",
                 hf_repo=KREA2_REPO, hf_file="diffusion_models/krea2_raw_bf16.safetensors",
                 ms_repo=KREA2_REPO, ms_file="diffusion_models/krea2_raw_bf16.safetensors"),
        AssetDef("vae", "VAE（Qwen-Image）", "sd-models/krea2/qwen_image_vae.safetensors",
                 hf_repo=KREA2_REPO, hf_file="vae/qwen_image_vae.safetensors",
                 ms_repo=KREA2_REPO, ms_file="vae/qwen_image_vae.safetensors"),
        AssetDef("text_encoder", "文本编码器（Qwen3-VL-4B）", "sd-models/krea2/qwen3_vl_4b.safetensors",
                 hf_repo=KREA2_REPO, hf_file="text_encoders/qwen3vl_4b_bf16.safetensors",
                 ms_repo=KREA2_REPO, ms_file="text_encoders/qwen3vl_4b_bf16.safetensors"),
        AssetDef("turbo_dit", "Turbo 蒸馏 DiT（可选）", "sd-models/krea2/krea2-turbo.safetensors", optional=True,
                 hf_repo=KREA2_REPO, hf_file="diffusion_models/krea2_turbo_bf16.safetensors",
                 ms_repo=KREA2_REPO, ms_file="diffusion_models/krea2_turbo_bf16.safetensors"),
        AssetDef("tokenizer", "Qwen3-VL tokenizer（目录）", "sd-models/krea2/qwen3-vl-tokenizer", kind="dir",
                 hf_repo=QWEN3_VL_REPO, ms_repo=QWEN3_VL_REPO),
    ),
}


def _config() -> dict:
    path = CONFIG_PATH
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def manifest_for(train_type: str) -> list[AssetDef]:
    base = ASSET_REGISTRY.get(train_type)
    if not base:
        return []
    overrides = _config().get(train_type, {})
    resolved = []
    for asset in base:
        extra = overrides.get(asset.key, {}) if isinstance(overrides, dict) else {}
        resolved.append(AssetDef(
            key=asset.key,
            label=asset.label,
            default_path=str(extra.get("default_path") or asset.default_path),
            optional=bool(extra.get("optional", asset.optional)),
            kind=str(extra.get("kind") or asset.kind),
            hf_repo=str(extra.get("hf_repo") or asset.hf_repo),
            hf_file=str(extra.get("hf_file") or asset.hf_file),
            ms_repo=str(extra.get("ms_repo") or asset.ms_repo),
            ms_file=str(extra.get("ms_file") or asset.ms_file),
        ))
    return resolved


def resolve_train_type(payload_train_type: str, values: dict[str, Any]) -> str:
    """Prefer the config's model_train_type (e.g. lora-master → sd-lora/sdxl-lora)."""
    from_values = str(values.get("model_train_type") or "").strip()
    return from_values or payload_train_type.strip()


def _target_path(raw: str, project_root: Path) -> Path:
    path = Path(raw.strip() or ".")
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def dir_complete(path: Path) -> bool:
    return all((path / name).is_file() for name in TOKENIZER_REQUIRED)


def krea2_tokenizer_dir(project_root: Path) -> Path:
    for asset in manifest_for("krea2-lora"):
        if asset.key == "tokenizer":
            return _target_path(asset.default_path, project_root)
    return _target_path("sd-models/krea2/qwen3-vl-tokenizer", project_root)


KREA2_ENCODER_REL = Path("src/musubi_tuner/krea2/krea2_encoder.py")
_TOKENIZER_PATCH_MARK = "# mikazuki: patched tokenizer path"
_TOKENIZER_LOAD_LINE = "    tokenizer = AutoTokenizer.from_pretrained(tokenizer_repo, max_length=max_length)"


def patch_krea2_tokenizer_path(source_root: Path, tokenizer_dir: Path, log: Callable[[str], None] = print) -> bool:
    """Rewrite krea2_encoder.py so the Qwen3-VL tokenizer loads from the local
    tokenizer directory instead of hitting the Hub. Idempotent; no-op when the
    directory is incomplete. Refuses to write if the result would not compile."""
    encoder = Path(source_root) / KREA2_ENCODER_REL
    if not encoder.is_file():
        return False
    tokenizer_dir = Path(tokenizer_dir)
    if not dir_complete(tokenizer_dir):
        return False
    text = encoder.read_text(encoding="utf-8")
    if _TOKENIZER_PATCH_MARK in text:
        return True
    if _TOKENIZER_LOAD_LINE not in text:
        log(f"[patch] tokenizer load line not found in {encoder}; skipped")
        return False
    injection = f'    tokenizer_repo = r"{tokenizer_dir.as_posix()}"  {_TOKENIZER_PATCH_MARK}\n'
    patched = text.replace(_TOKENIZER_LOAD_LINE, injection + _TOKENIZER_LOAD_LINE, 1)
    try:
        compile(patched, str(encoder), "exec")
    except SyntaxError as exc:
        log(f"[patch] result would not compile ({exc}); {encoder} left unchanged")
        return False
    encoder.write_text(patched, encoding="utf-8")
    log(f"[patch] krea2 tokenizer_repo -> {tokenizer_dir}")
    return True


def patch_krea2_tokenizer_everywhere(project_root: Path, log: Callable[[str], None] = print) -> bool:
    """Patch every known musubi source root (installed extension, vendor, upstream cache)."""
    from mikazuki.musubi_backend.extension_state import default_layout as musubi_default_layout

    tokenizer_dir = krea2_tokenizer_dir(project_root)
    patched = False
    for root in (
        musubi_default_layout(project_root).source,
        Path(project_root) / "vendor" / "musubi-tuner",
        Path(project_root) / ".cache" / "musubi" / "upstream",
    ):
        patched = patch_krea2_tokenizer_path(root, tokenizer_dir, log) or patched
    return patched


def check_assets(train_type: str, values: dict[str, Any], project_root: Path) -> list[dict]:
    items = []
    for asset in manifest_for(train_type):
        target = _target_path(str(values.get(asset.key) or asset.default_path), project_root)
        exists = dir_complete(target) if asset.kind == "dir" else target.is_file()
        items.append({
            "key": asset.key,
            "label": asset.label,
            "path": str(target),
            "exists": exists,
            "optional": asset.optional,
            "sources": {
                "huggingface": bool(asset.hf_repo and (asset.hf_file or asset.kind == "dir")),
                "modelscope": bool(asset.ms_repo and (asset.ms_file or asset.kind == "dir")),
            },
        })
    return items


def _download_dir_asset(asset: AssetDef, source: str, target_dir: Path, log: Callable[[str], None]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    if source == "huggingface":
        log(f"[download] huggingface {asset.hf_repo} (tokenizer files) -> {target_dir}")
        from huggingface_hub import hf_hub_download

        for name in TOKENIZER_FILES:
            hf_hub_download(repo_id=asset.hf_repo, filename=name, local_dir=str(target_dir))
    else:
        log(f"[download] modelscope {asset.ms_repo} (tokenizer files) -> {target_dir}")
        try:
            from modelscope import snapshot_download
        except ImportError as exc:
            raise RuntimeError("ModelScope 下载需要 modelscope 依赖，请先安装 requirements.txt") from exc

        snapshot_download(asset.ms_repo, allow_patterns=TOKENIZER_FILES, local_dir=str(target_dir))
    if not dir_complete(target_dir):
        raise FileNotFoundError(f"下载完成但目录缺少 tokenizer 文件: {target_dir}")


def download_assets(
    train_type: str,
    items: list[dict],
    source: str,
    project_root: Path,
    log: Callable[[str], None],
) -> None:
    """Download selected asset keys to their target paths. Runs inside a task thread."""
    assets = {asset.key: asset for asset in manifest_for(train_type)}
    for item in items:
        asset = assets.get(str(item.get("key")))
        if asset is None:
            raise ValueError(f"未知资产: {item.get('key')}")
        if asset.kind == "dir":
            _download_dir_asset(asset, source, _target_path(str(item.get("path") or asset.default_path), project_root), log)
            log(f"[done] {asset.label}")
            if train_type == "krea2-lora" and asset.key == "tokenizer":
                patch_krea2_tokenizer_everywhere(project_root, log)
            continue
        target = _target_path(str(item.get("path") or asset.default_path), project_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source == "huggingface":
            if not (asset.hf_repo and asset.hf_file):
                raise ValueError(f"{asset.label} 未配置 HuggingFace 下载源")
            log(f"[download] huggingface {asset.hf_repo}/{asset.hf_file} -> {target}")
            from huggingface_hub import hf_hub_download

            downloaded = Path(hf_hub_download(repo_id=asset.hf_repo, filename=asset.hf_file, local_dir=str(target.parent)))
        elif source == "modelscope":
            if not (asset.ms_repo and asset.ms_file):
                raise ValueError(f"{asset.label} 未配置 ModelScope 下载源")
            log(f"[download] modelscope {asset.ms_repo}/{asset.ms_file} -> {target}")
            try:
                from modelscope import snapshot_download
            except ImportError as exc:
                raise RuntimeError("ModelScope 下载需要 modelscope 依赖，请先安装 requirements.txt") from exc

            snapshot_download(asset.ms_repo, allow_patterns=[asset.ms_file], local_dir=str(target.parent))
            downloaded = target.parent / asset.ms_file
        else:
            raise ValueError(f"未知下载源: {source}")
        if downloaded.resolve() != target:
            if not downloaded.is_file():
                raise FileNotFoundError(f"下载完成但未找到文件: {downloaded}")
            downloaded.replace(target)
        log(f"[done] {asset.label} -> {target}")


def start_download_task(train_type: str, items: list[dict], source: str, project_root: Path) -> tuple[str, dict]:
    import threading
    import uuid

    from mikazuki.tasks import Task, tm
    from mikazuki.train_log_hub import hub as train_log_hub

    task_id = f"assets-download-{uuid.uuid4()}"
    task = Task(
        task_id=task_id,
        command=["assets-download"],
        environ=os.environ.copy(),
        metadata={"kind": "assets_download", "train_type": train_type, "source": source, "items": items},
        cwd=str(project_root),
    )
    tm.add_task(task_id, task)
    task.start_log_only()

    def runner() -> None:
        def log(line: str) -> None:
            train_log_hub.append_line(task_id, line)

        try:
            log(f"[start] asset download via {source} ({train_type})")
            download_assets(train_type, items, source, project_root, log)
            task.finish_log_only(0, None)
        except (Exception, KeyboardInterrupt) as exc:
            log(f"[error] {exc}")
            task.finish_log_only(1, exc)

    threading.Thread(target=runner, daemon=True).start()
    return task_id, {
        "task_id": task_id,
        "log_stream": f"/api/train/log/stream/{task_id}",
    }
