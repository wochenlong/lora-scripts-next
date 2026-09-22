"""Structural validator for kohya-format dataset config TOML files.

Catches the classic "starts training then dies instantly on voluptuous
schema error" failure (e.g. feeding an anima-fast dataset TOML with
``validation_split_num``/``recursive``/``cache_dir`` to the kohya engine)
at submit time instead of runtime.

Key whitelists are a static snapshot of vendor/sd-scripts/library/config_util.py
(BlueprintGenerator schemas); re-sync when vendored sd-scripts is refreshed.
Only structure and key names are checked, not value semantics.
"""

from __future__ import annotations

from pathlib import Path

_SUBSET_ASCENDABLE = {
    "color_aug", "face_crop_aug_range", "flip_aug", "num_repeats", "random_crop",
    "shuffle_caption", "keep_tokens", "keep_tokens_separator", "secondary_separator",
    "caption_separator", "enable_wildcard", "token_warmup_min", "token_warmup_step",
    "caption_prefix", "caption_suffix", "custom_attributes", "resize_interpolation",
}
_DO_SUBSET_ASCENDABLE = {
    "caption_dropout_every_n_epochs", "caption_dropout_rate", "caption_tag_dropout_rate",
}
_DB_SUBSET_ASCENDABLE = {"caption_extension", "class_tokens", "cache_info"}
_CN_SUBSET_ASCENDABLE = {"caption_extension", "cache_info"}
_SUBSET_DISTINCT = {
    "image_dir", "metadata_file", "is_reg", "alpha_mask", "conditioning_data_dir",
}

GENERAL_KEYS = (
    _SUBSET_ASCENDABLE | _DO_SUBSET_ASCENDABLE | _DB_SUBSET_ASCENDABLE | _CN_SUBSET_ASCENDABLE
)

DATASET_KEYS = {
    "batch_size", "bucket_no_upscale", "bucket_reso_steps", "enable_bucket",
    "max_bucket_reso", "min_bucket_reso", "validation_seed", "validation_split",
    "resolution", "network_multiplier", "resize_interpolation", "skip_image_resolution",
    "subsets",
}

SUBSET_KEYS = GENERAL_KEYS | _SUBSET_DISTINCT

_TOP_LEVEL_KEYS = {"general", "datasets"}


def _unknown_keys(mapping: dict, allowed: set, where: str) -> list[str]:
    return [
        f"{where}: 未知字段 {key!r} —— kohya 数据集格式不支持它"
        "（若该字段来自 anima-fast 等其他引擎的配置，请切换引擎或移除）"
        for key in mapping
        if key not in allowed
    ]


def validate_dataset_toml(path: str) -> dict:
    """Validate a dataset config TOML. Returns {ok, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    file_path = Path(str(path).strip()) if str(path).strip() else None
    if file_path is None or not file_path.is_file():
        return {"ok": False, "errors": [f"数据集配置文件不存在: {path}"], "warnings": warnings}

    try:
        import toml

        config = toml.load(file_path)
    except Exception as exc:
        return {"ok": False, "errors": [f"TOML 解析失败: {exc}"], "warnings": warnings}

    errors.extend(_unknown_keys(config, _TOP_LEVEL_KEYS, "顶层"))

    general = config.get("general") or {}
    if not isinstance(general, dict):
        errors.append("[general] 必须是表")
        general = {}
    errors.extend(_unknown_keys(general, GENERAL_KEYS, "[general]"))

    datasets = config.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        errors.append("缺少 [[datasets]] 或内容为空")
        datasets = []

    for idx, dataset in enumerate(datasets):
        where = f"[[datasets]] 第 {idx + 1} 项"
        if not isinstance(dataset, dict):
            errors.append(f"{where}: 必须是表")
            continue
        errors.extend(_unknown_keys(dataset, DATASET_KEYS, where))

        resolution = dataset.get("resolution")
        if resolution is None:
            errors.append(f"{where}: 缺少 resolution")
        elif isinstance(resolution, list):
            if len(resolution) != 2 or not all(isinstance(v, int) for v in resolution):
                errors.append(f"{where}: resolution 列表必须是 [宽, 高] 两个整数")
        elif not isinstance(resolution, int):
            errors.append(f"{where}: resolution 必须是整数或 [宽, 高]")

        subsets = dataset.get("subsets")
        if not isinstance(subsets, list) or not subsets:
            errors.append(f"{where}: 缺少 subsets 或内容为空")
            continue

        for sidx, subset in enumerate(subsets):
            sw = f"{where} 第 {sidx + 1} 个 subset"
            if not isinstance(subset, dict):
                errors.append(f"{sw}: 必须是表")
                continue
            errors.extend(_unknown_keys(subset, SUBSET_KEYS, sw))

            image_dir = subset.get("image_dir")
            metadata_file = subset.get("metadata_file")
            if not image_dir and not metadata_file:
                errors.append(f"{sw}: 缺少 image_dir（或 fine-tuning 模式的 metadata_file）")
            elif image_dir:
                dir_path = Path(str(image_dir))
                if not dir_path.is_absolute():
                    dir_path = file_path.parent / dir_path
                if not dir_path.is_dir():
                    errors.append(f"{sw}: image_dir 不存在: {image_dir}")

            if subset.get("is_reg") and not subset.get("class_tokens"):
                warnings.append(f"{sw}: is_reg=true 但未设 class_tokens，正则化效果可能不符合预期")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
