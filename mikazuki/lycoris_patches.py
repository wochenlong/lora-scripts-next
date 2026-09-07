"""Runtime patches for the third-party ``lycoris`` package (issue #323).

``lycoris.kohya`` is a pip dependency (not vendored) and its upstream is
unmaintained, so bugs cannot be fixed at the source. The training subprocess
entry (``mikazuki/accelerate_launch.py``) applies these patches before the
trainer script imports lycoris.

Currently patched:

- ``LokrModule.bypass_forward_diff``: the bypass forward path feeds the raw
  fp32 LoKr parameters into ``F.linear``/``F.conv*`` against activations that
  may be bf16/fp16 (e.g. Anima sampling with bf16 autocast or native bf16
  weights), raising ``expected mat1 and mat2 to have the same dtype``. The
  non-bypass forward already aligns via ``.to(self.dtype)``; this patch makes
  the bypass path align the weights to the incoming activation dtype, which
  is a no-op when dtypes already match. Casts keep autograd connectivity, so
  fp32 master weights for optimizers like Automagic are untouched.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PATCH_MARK = "_mikazuki_dtype_aligned"


def _make_patched_bypass_forward_diff():
    import torch
    import torch.nn.functional as F

    def bypass_forward_diff(self, h, scale=1):
        # Body mirrors lycoris_lora 3.2.0.post2 lycoris/modules/lokr.py, with
        # every weight tensor aligned to the activation dtype before use.
        dtype = h.dtype
        is_conv = self.module_type.startswith("conv")
        if self.use_w2:
            ba = self.lokr_w2.to(dtype)
        else:
            a = self.lokr_w2_b.to(dtype)
            b = self.lokr_w2_a.to(dtype)

            if self.tucker:
                t = self.lokr_t2.to(dtype)
                a = a.view(*a.shape, *[1] * (len(t.shape) - 2))
                b = b.view(*b.shape, *[1] * (len(t.shape) - 2))
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
            # NOTE: upstream rebinds ``b`` here (``b, _, *rest = h.shape``),
            # shadowing the w2_a weight and making conv bypass crash; we use a
            # distinct name so the weight stays reachable below.
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

    bypass_forward_diff._mikazuki_dtype_aligned_src = "lycoris_lora-3.2.0.post2"  # type: ignore[attr-defined]
    return bypass_forward_diff


def apply_lycoris_patches() -> None:
    """Best-effort, defensive: never blocks training when lycoris is absent
    or its layout drifts from the known version."""
    try:
        from lycoris.modules import lokr as lycoris_lokr
    except ImportError:
        return
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
