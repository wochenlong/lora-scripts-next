"""Tests for mikazuki.lycoris_patches (issue #323).

Covers:
- defensive application (missing lycoris / unknown layout / idempotency)
- the patched LokrModule.bypass_forward_diff aligning fp32 weights to bf16
  activations, staying a no-op when dtypes already match, and keeping
  autograd connectivity to the fp32 master weights
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

import torch
import torch.nn.functional as F

from mikazuki import lycoris_patches


def _install_fake_lycoris(*, with_lokr_module: bool = True) -> types.ModuleType:
    lycoris_pkg = types.ModuleType("lycoris")
    lycoris_pkg.__path__ = []
    modules_pkg = types.ModuleType("lycoris.modules")
    modules_pkg.__path__ = []
    lokr_mod = types.ModuleType("lycoris.modules.lokr")

    if with_lokr_module:

        class LokrModule:
            def bypass_forward_diff(self, h, scale=1):
                raise RuntimeError(
                    "expected mat1 and mat2 to have the same dtype, but got: c10::BFloat16 != float"
                )

        lokr_mod.LokrModule = LokrModule

    modules_pkg.lokr = lokr_mod
    lycoris_pkg.modules = modules_pkg
    fake = {
        "lycoris": lycoris_pkg,
        "lycoris.modules": modules_pkg,
        "lycoris.modules.lokr": lokr_mod,
    }
    return mock.patch.dict(sys.modules, fake), lokr_mod


class ApplyPatchesDefensivenessTests(unittest.TestCase):
    def test_noop_when_lycoris_not_installed(self):
        with mock.patch.dict(sys.modules, {"lycoris": None, "lycoris.modules": None, "lycoris.modules.lokr": None}):
            lycoris_patches.apply_lycoris_patches()  # must not raise

    def test_patches_lokr_module_and_is_idempotent(self):
        patcher, lokr_mod = _install_fake_lycoris()
        with patcher:
            cls = lokr_mod.LokrModule
            original = cls.bypass_forward_diff

            lycoris_patches.apply_lycoris_patches()
            self.assertIsNot(cls.bypass_forward_diff, original)
            self.assertTrue(getattr(cls.bypass_forward_diff, lycoris_patches._PATCH_MARK, False))

            patched_once = cls.bypass_forward_diff
            lycoris_patches.apply_lycoris_patches()
            self.assertIs(cls.bypass_forward_diff, patched_once)

    def test_skips_with_warning_on_unrecognized_layout(self):
        patcher, lokr_mod = _install_fake_lycoris(with_lokr_module=False)
        with patcher:
            with self.assertLogs(lycoris_patches.logger, level="WARNING"):
                lycoris_patches.apply_lycoris_patches()
            self.assertFalse(hasattr(lokr_mod, "LokrModule"))

    def test_never_raises_on_broken_lycoris(self):
        broken = types.ModuleType("lycoris.modules")

        def _boom(name):
            raise RuntimeError("corrupt install")

        broken.__getattr__ = _boom
        fake = {
            "lycoris": types.ModuleType("lycoris"),
            "lycoris.modules": broken,
        }
        with mock.patch.dict(sys.modules, fake):
            lycoris_patches.apply_lycoris_patches()  # must not raise


class _FakeLokrModule:
    """Minimal mimic of lycoris LokrModule (linear, decomposed w1/w2)."""

    def __init__(self, dtype=torch.float32):
        # in_dim = in_m * in_n = 2 * 3 = 6, out_dim = out_l * out_k = 2 * 5 = 10
        self.module_type = "linear"
        self.use_w1 = False
        self.use_w2 = False
        self.tucker = False
        self.kw_dict = {}
        self.scalar = 1.0
        self.drop = lambda x: x
        self.op = F.linear
        self.lokr_w1_a = torch.nn.Parameter(torch.randn(2, 4, dtype=dtype) * 0.02)
        self.lokr_w1_b = torch.nn.Parameter(torch.randn(4, 2, dtype=dtype) * 0.02)
        self.lokr_w2_a = torch.nn.Parameter(torch.randn(5, 4, dtype=dtype) * 0.02)
        self.lokr_w2_b = torch.nn.Parameter(torch.randn(4, 3, dtype=dtype) * 0.02)


class PatchedBypassForwardDiffTests(unittest.TestCase):
    patched = staticmethod(lycoris_patches._make_patched_bypass_forward_diff())

    def test_bf16_activation_against_fp32_weights_no_longer_crashes(self):
        module = _FakeLokrModule()
        h = torch.randn(2, 6, dtype=torch.bfloat16)

        with self.assertRaises(RuntimeError):
            # unpatched behavior: raw fp32 weights vs bf16 activation
            a = module.lokr_w2_b
            F.linear(h.reshape(2, 2, 3), a)

        out = self.patched(module, h)
        self.assertEqual(out.dtype, torch.bfloat16)
        self.assertEqual(out.shape, (2, 10))
        self.assertTrue(torch.isfinite(out).all())

    def test_fp32_activation_matches_unpatched_reference(self):
        module = _FakeLokrModule()
        h = torch.randn(2, 6, dtype=torch.float32)

        out = self.patched(module, h)

        c = module.lokr_w1_a @ module.lokr_w1_b
        h_in_group = h.reshape(2, 2, 3)
        ha = F.linear(h_in_group, module.lokr_w2_b)
        hb = F.linear(ha, module.lokr_w2_a)
        h_cross_group = hb.transpose(-1, -2)
        hc = F.linear(h_cross_group, c)
        ref = hc.transpose(-1, -2).reshape(2, -1)

        self.assertTrue(torch.allclose(out, ref, atol=1e-6))

    def test_gradients_flow_to_fp32_master_weights(self):
        module = _FakeLokrModule()
        h = torch.randn(2, 6, dtype=torch.bfloat16)

        out = self.patched(module, h)
        out.float().sum().backward()

        for p in (module.lokr_w1_a, module.lokr_w1_b, module.lokr_w2_a, module.lokr_w2_b):
            self.assertIsNotNone(p.grad)
            self.assertEqual(p.dtype, torch.float32)


if __name__ == "__main__":
    unittest.main()
