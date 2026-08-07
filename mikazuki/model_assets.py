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
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 runtime
    import toml as tomllib


CONFIG_PATH = Path("config/model_assets.toml")


@dataclass(frozen=True)
class AssetDef:
    key: str
    label: str
    default_path: str  # relative to project root; unused for kind="hf_cache"
    optional: bool = False
    kind: str = "file"  # "file" | "hf_cache" (tokenizer files living in the HF hub cache)
    hf_repo: str = ""
    hf_file: str = ""
    ms_repo: str = ""
    ms_file: str = ""


KREA2_REPO = "Comfy-Org/Krea-2"
QWEN3_VL_REPO = "Qwen/Qwen3-VL-4B-Instruct"
HF_CACHE_PATTERNS = ["tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "special_tokens_map.json", "added_tokens.json"]
HF_CACHE_REQUIRED = ("tokenizer.json", "tokenizer_config.json")

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
        AssetDef("tokenizer", "Qwen3-VL tokenizer（HF 缓存）", "", kind="hf_cache",
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


def _hf_cache_repo_dir(repo: str) -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE

    return Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))


_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{5,64}$")


def _hf_cache_complete(repo: str) -> bool:
    """Mirror huggingface_hub.try_to_load_from_cache: refs/main must resolve to a
    commit-hash-shaped snapshot dir containing the required files. Files sitting in
    a non-hex snapshot (e.g. snapshots/main) are invisible to transformers too."""
    repo_dir = _hf_cache_repo_dir(repo)
    snapshots: list[Path] = []
    ref = repo_dir / "refs" / "main"
    if ref.is_file():
        revision = ref.read_text(encoding="utf-8").strip()
        if _COMMIT_HASH_RE.match(revision):
            snapshots.append(repo_dir / "snapshots" / revision)
    else:
        parent = repo_dir / "snapshots"
        if parent.is_dir():
            snapshots.extend(p for p in parent.iterdir() if p.is_dir() and _COMMIT_HASH_RE.match(p.name))
    return any(
        all((snapshot / name).is_file() for name in HF_CACHE_REQUIRED)
        for snapshot in snapshots
    )


def check_assets(train_type: str, values: dict[str, Any], project_root: Path) -> list[dict]:
    items = []
    for asset in manifest_for(train_type):
        if asset.kind == "hf_cache":
            target = _hf_cache_repo_dir(asset.hf_repo or asset.ms_repo)
            exists = _hf_cache_complete(asset.hf_repo or asset.ms_repo)
        else:
            target = _target_path(str(values.get(asset.key) or asset.default_path), project_root)
            exists = target.is_file()
        items.append({
            "key": asset.key,
            "label": asset.label,
            "path": str(target),
            "exists": exists,
            "optional": asset.optional,
            "sources": {
                "huggingface": bool(asset.hf_repo and (asset.hf_file or asset.kind == "hf_cache")),
                "modelscope": bool(asset.ms_repo and (asset.ms_file or asset.kind == "hf_cache")),
            },
        })
    return items


def _materialize_hf_cache(repo: str, source_dir: Path, log: Callable[[str], None]) -> None:
    """Lay ModelScope-downloaded files into the HF hub cache layout so
    transformers' from_pretrained(repo_id) hits the cache without network.
    The snapshot dir must look like a commit hash: huggingface_hub's
    try_to_load_from_cache rejects non-hex revisions (e.g. "main")."""
    import hashlib
    import shutil

    pseudo_commit = hashlib.sha1(f"modelscope:{repo}".encode("utf-8")).hexdigest()
    repo_dir = _hf_cache_repo_dir(repo)
    snapshot = repo_dir / "snapshots" / pseudo_commit
    snapshot.mkdir(parents=True, exist_ok=True)
    refs = repo_dir / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(pseudo_commit, encoding="utf-8")
    for path in source_dir.rglob("*"):
        if path.is_file():
            shutil.copy2(path, snapshot / path.name)
    log(f"[cache] materialized {repo} into {repo_dir}")


def _download_hf_cache_asset(asset: AssetDef, source: str, log: Callable[[str], None]) -> None:
    if source == "huggingface":
        log(f"[download] huggingface {asset.hf_repo} (cache files) -> HF hub cache")
        from huggingface_hub import snapshot_download

        snapshot_download(asset.hf_repo, allow_patterns=HF_CACHE_PATTERNS)
    else:
        log(f"[download] modelscope {asset.ms_repo} (cache files) -> HF hub cache")
        import tempfile

        try:
            from modelscope import snapshot_download as ms_snapshot_download
        except ImportError as exc:
            raise RuntimeError("ModelScope 下载需要 modelscope 依赖，请先安装 requirements.txt") from exc

        with tempfile.TemporaryDirectory() as td:
            ms_snapshot_download(asset.ms_repo, allow_patterns=HF_CACHE_PATTERNS, local_dir=td)
            _materialize_hf_cache(asset.ms_repo, Path(td), log)
    if not _hf_cache_complete(asset.hf_repo or asset.ms_repo):
        raise FileNotFoundError(f"下载完成但 HF 缓存缺少 tokenizer 文件: {asset.hf_repo or asset.ms_repo}")


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
        if asset.kind == "hf_cache":
            _download_hf_cache_asset(asset, source, log)
            log(f"[done] {asset.label}")
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
