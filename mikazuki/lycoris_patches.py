"""Runtime patches for the third-party ``lycoris`` package (issue #323).

``lycoris.kohya`` is a pip dependency (not vendored) and its upstream is
unmaintained, so bugs cannot be fixed at the source. The training subprocess
applies these patches from ``vendor/sd-scripts/train_network.py`` right
before importing the network module.

Currently patched:

- ``LokrModule.bypass_forward_diff``: the bypass forward path feeds the raw
  fp32 LoKr parameters into ``F.linear``/``F.conv*`` against activations that
  may be bf16/fp16 (e.g. Anima sampling with bf16 autocast or native bf16
  weights), raising ``expected mat1 and mat2 to have the same dtype``. The
  non-bypass forward already aligns via ``.to(self.dtype)``; this patch makes
  the bypass path align the weights to the incoming activation dtype, which
  is a no-op when dtypes already match. Casts keep autograd connectivity, so
  fp32 master weights for optimizers like Automagic are untouched.

The patched body mirrors lycoris-lora **3.3.0** (verified byte-identical in
3.2.0.post2) with two additional upstream conv-bypass fixes: the batch-size
variable shadowing the ``b`` weight, and the Tucker closing 1x1 conv getting
``w2_a`` in its stored ``(dim, vp)`` orientation instead of the required
``(vp, dim)``. Application is gated on the verified versions because the
copied body is version-specific; unknown versions are skipped with a warning
(same policy as ``mikazuki/anima_backend/lycoris_patch.py``).
"""

from __future__ import annotations

import importlib.metadata
import logging

logger = logging.getLogger(__name__)

_PATCH_MARK = "_mikazuki_dtype_aligned"

# bypass_forward_diff bodies verified identical across these releases.
_SUPPORTED_LYCORIS_VERSIONS = {"3.3.0", "3.2.0.post2"}


def _lycoris_lora_version() -> str | None:
    try:
        return importlib.metadata.version("lycoris-lora")
    except importlib.metadata.PackageNotFoundError:
        return None


def _make_patched_bypass_forward_diff():
    import torch
    import torch.nn.functional as F

    def bypass_forward_diff(self, h, scale=1):
        # Body mirrors lycoris-lora 3.3.0 lycoris/modules/lokr.py, with every
        # weight tensor aligned to the activation dtype before use.
        dtype = h.dtype
        is_conv = self.module_type.startswith("conv")
        if self.use_w2:
            ba = self.lokr_w2.to(dtype)
        else:
            a = self.lokr_w2_b.to(dtype)
            b = self.lokr_w2_a.to(dtype)

            if self.tucker:
                t = self.lokr_t2.to(dtype)
                # Upstream bugs fixed here: ``b`` was later shadowed by the
                # batch size, and w2_a is stored (dim, vp) while the closing
                # 1x1 conv needs (vp, dim) - see rebuild_tucker's einsum.
                b = b.mT
                a = a.view(*a.shape, *[1] * (len(t.shape) - 2))
                b = b.reshape(*b.shape, *[1] * (len(t.shape) - 2))
            elif is_conv:
                a = a.view(*a.shape, *self.shape[2:])
                b = b.view(*b.shape, *[1] * (len(self.shape) - 2))

        if self.use_w1:
            c = self.lokr_w1.to(dtype)
        else:
            c = (self.lokr_w1_a @ self.lokr_w1_b).to(dtype)
        uq = c.size(1)

        if is_conv:
            # (b, uq), vq, ...
            bsz, _, *rest = h.shape
            h_in_group = h.reshape(bsz * uq, -1, *rest)
        else:
            # b, ..., uq, vq
            h_in_group = h.reshape(*h.shape[:-1], uq, -1)

        if self.use_w2:
            hb = self.op(h_in_group, ba, **self.kw_dict)
        else:
            if is_conv:
                if self.tucker:
                    ha = self.op(h_in_group, a)
                    ht = self.op(ha, t, **self.kw_dict)
                    hb = self.op(ht, b)
                else:
                    ha = self.op(h_in_group, a, **self.kw_dict)
                    hb = self.op(ha, b)
            else:
                ha = self.op(h_in_group, a, **self.kw_dict)
                hb = self.op(ha, b)

        if is_conv:
            # (b, uq), vp, ..., f
            # -> b, uq, vp, ..., f
            # -> b, f, vp, ..., uq
            hb = hb.view(bsz, -1, *hb.shape[1:])
            h_cross_group = hb.transpose(1, -1)
        else:
            # b, ..., uq, vq
            # -> b, ..., vq, uq
            h_cross_group = hb.transpose(-1, -2)

        hc = F.linear(h_cross_group, c)
        if is_conv:
            # b, f, vp, ..., up
            # -> b, up, vp, ... ,f
            # -> b, c, ..., f
            hc = hc.transpose(1, -1)
            h = hc.reshape(bsz, -1, *hc.shape[3:])
        else:
            # b, ..., vp, up
            # -> b, ..., up, vp
            # -> b, ..., c
            hc = hc.transpose(-1, -2)
            h = hc.reshape(*hc.shape[:-2], -1)

        return self.drop(h * scale * self.scalar)

    bypass_forward_diff._mikazuki_dtype_aligned_src = "lycoris-lora-3.3.0"  # type: ignore[attr-defined]
    return bypass_forward_diff


def apply_lycoris_patches() -> None:
    """Best-effort, defensive: never blocks training when lycoris is absent,
    its layout drifts from the known version, or the release is unverified."""
    version = _lycoris_lora_version()
    if version is None:
        return  # lycoris not installed; nothing to patch
    if version not in _SUPPORTED_LYCORIS_VERSIONS:
        logger.warning(
            "lycoris-lora %s is not a verified version for the LoKr bypass dtype "
            "patch (verified: %s); skipping. LoKr bypass_mode may crash on dtype "
            "mismatch (issue #323)",
            version,
            ", ".join(sorted(_SUPPORTED_LYCORIS_VERSIONS)),
        )
        return

    try:
        from lycoris.modules import lokr as lycoris_lokr
    except Exception:  # noqa: BLE001 - a broken lycoris install must not kill launch
        logger.warning("lycoris import failed unexpectedly; skipping lycoris patches", exc_info=True)
        return

    module_cls = getattr(lycoris_lokr, "LokrModule", None)
    original = getattr(module_cls, "bypass_forward_diff", None) if module_cls is not None else None
    if module_cls is None or original is None:
        logger.warning(
            "lycoris LokrModule layout not recognized (version drift?); "
            "skipping bypass dtype patch for issue #323"
        )
        return
    if getattr(original, _PATCH_MARK, False):
        return

    patched = _make_patched_bypass_forward_diff()
    setattr(patched, _PATCH_MARK, True)
    module_cls.bypass_forward_diff = patched
    logger.info("Applied lycoris LokrModule bypass dtype-alignment patch (issue #323)")
