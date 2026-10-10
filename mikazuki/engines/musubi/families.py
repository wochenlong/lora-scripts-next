"""Model-family registry for the musubi-tuner engine pack.

A family pairs one upstream musubi-tuner architecture with its entry scripts,
LoRA network module and parameter constraints. The pack currently ships:

- ``krea2``     — Krea 2 LoRA (RAW/Turbo DiT, fp8 pair)
- ``ideogram4`` — Ideogram 4 LoRA (FP8-only base, Qwen3-VL-8B text encoder,
  asymmetric CFG for inference)

Everything family-specific lives here so adapter/launcher/preflight/run stay
generic. ``manifest.TRAIN_TYPES`` maps train type -> family name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FamilySpec:
    family: str
    train_type: str
    label: str
    network_module: str
    cache_latents_script: str
    cache_text_encoder_script: str
    train_script: str
    text_encoder_label: str = "Qwen3-VL 文本编码器路径"
    # Krea 2 only: optional Turbo DiT used for sampling; mutually exclusive with
    # blocks_to_swap.
    supports_turbo_dit: bool = False
    # Krea 2 only: fp8_base/fp8_scaled must be enabled together. Ideogram 4's
    # base is always FP8, so the flags must not leak into its TOML.
    supports_fp8_pair: bool = False
    # Upper bound for blocks_to_swap as documented upstream (0 = no limit).
    blocks_to_swap_max: int = 0
    # Krea 2 refuses to start without the local Qwen3-VL tokenizer directory
    # (its encoder is patched to it). Ideogram 4 falls back to the Hub id when
    # the directory is absent, so it only warns.
    require_local_tokenizer: bool = True
    vram_hint_mb: int = 12000
    vram_hint: str = "建议开启 fp8_base + blocks_to_swap"
    default_network_dim: int = 32
    default_network_alpha: int = 32
    # Config keys forwarded to the cache stages as CLI flags.
    cache_latents_args: tuple[str, ...] = ()
    cache_text_encoder_args: tuple[str, ...] = ()
    # Values appended to the train TOML as defaults when sampling is enabled.
    sampler_defaults: dict[str, Any] = field(default_factory=dict)
    # Defaults applied before prompt generation (UI-only sample keys).
    sample_defaults: dict[str, Any] = field(default_factory=dict)
    # Overrides applied on top of sample_defaults when a Turbo/aux DiT is set.
    turbo_sample_defaults: dict[str, Any] = field(default_factory=dict)


KREA2 = FamilySpec(
    family="krea2",
    train_type="krea2-lora",
    label="Krea 2",
    network_module="musubi_tuner.networks.lora_krea2",
    cache_latents_script="krea2_cache_latents.py",
    cache_text_encoder_script="krea2_cache_text_encoder_outputs.py",
    train_script="krea2_train_network.py",
    text_encoder_label="Qwen3-VL-4B 文本编码器路径",
    supports_turbo_dit=True,
    supports_fp8_pair=True,
    sample_defaults={"sample_cfg": 4.5, "sample_steps": 28},
    turbo_sample_defaults={"sample_cfg": 1, "sample_steps": 8},
)

IDEOGRAM4 = FamilySpec(
    family="ideogram4",
    train_type="ideogram4-lora",
    label="Ideogram 4",
    network_module="musubi_tuner.networks.lora_ideogram4",
    cache_latents_script="ideogram4_cache_latents.py",
    cache_text_encoder_script="ideogram4_cache_text_encoder_outputs.py",
    train_script="ideogram4_train_network.py",
    text_encoder_label="Qwen3-VL-8B 文本编码器路径（qwen3vl_8b_fp8_scaled）",
    blocks_to_swap_max=33,
    require_local_tokenizer=False,
    vram_hint_mb=16000,
    vram_hint="建议提高 blocks_to_swap（上限 33）并开启 gradient_checkpointing，必要时关闭训练中采样预览",
    cache_latents_args=("vae_dtype",),
    cache_text_encoder_args=("text_cache_dtype", "validate_caption_structure", "warn_on_caption_issues"),
    sampler_defaults={
        "sampler_preset": "V4_DEFAULT_20",
        "initial_sigma": 1.004,
    },
    sample_defaults={
        "sample_cfg": 7,
        "sample_steps": 20,
    },
)

FAMILIES: dict[str, FamilySpec] = {spec.family: spec for spec in (KREA2, IDEOGRAM4)}
DEFAULT_FAMILY = KREA2.family
TRAIN_TYPE_TO_FAMILY: dict[str, str] = {spec.train_type: spec.family for spec in FAMILIES.values()}


def family_for(family: str | None) -> FamilySpec:
    """Resolve a family name; unknown/empty values fall back to Krea 2."""
    return FAMILIES.get(str(family or "").strip(), KREA2)


def family_for_variant(variant: str | None) -> FamilySpec:
    """Resolve the registry variant (``manifest.TRAIN_TYPES`` value)."""
    return family_for(variant)


def family_for_train_type(train_type: str | None) -> FamilySpec:
    """Resolve a page-level train type (``model_train_type``) to its family."""
    return family_for(TRAIN_TYPE_TO_FAMILY.get(str(train_type or "").strip()))


def cache_extra_args(
    spec: FamilySpec,
    stage: str,
    values: dict[str, Any],
) -> list[str]:
    """CLI flags for a cache stage, taken from the adapted config values."""
    keys = spec.cache_latents_args if stage == "cache_latents" else spec.cache_text_encoder_args
    args: list[str] = []
    for key in keys:
        raw = values.get(key)
        if raw is None or raw is False:
            continue
        if raw is True:
            args.append(f"--{key}")
            continue
        text = str(raw).strip()
        if not text:
            continue
        args.extend((f"--{key}", text))
    return args
