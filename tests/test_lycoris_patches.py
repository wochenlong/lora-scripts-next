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
        # test venv has no lycoris-lora dist metadata -> version None -> skip
        lycoris_patches.apply_lycoris_patches()  # must not raise

    def test_patches_lokr_module_and_is_idempotent(self):
        patcher, lokr_mod = _install_fake_lycoris()
        with patcher:
            cls = lokr_mod.LokrModule
            original = cls.bypass_forward_diff

            with mock.patch.object(lycoris_patches, "_lycoris_lora_version", return_value="3.3.0"):
                lycoris_patches.apply_lycoris_patches()
                self.assertIsNot(cls.bypass_forward_diff, original)
                self.assertTrue(getattr(cls.bypass_forward_diff, lycoris_patches._PATCH_MARK, False))

                patched_once = cls.bypass_forward_diff
                lycoris_patches.apply_lycoris_patches()
                self.assertIs(cls.bypass_forward_diff, patched_once)

    def test_skips_with_warning_on_unverified_version(self):
        patcher, lokr_mod = _install_fake_lycoris()
        with patcher:
            cls = lokr_mod.LokrModule
            original = cls.bypass_forward_diff

            with mock.patch.object(lycoris_patches, "_lycoris_lora_version", return_value="9.9.9"):
                with self.assertLogs(lycoris_patches.logger, level="WARNING") as cm:
                    lycoris_patches.apply_lycoris_patches()

            self.assertIs(cls.bypass_forward_diff, original)
            self.assertIn("9.9.9", "\n".join(cm.output))

    def test_skips_with_warning_on_unrecognized_layout(self):
        patcher, lokr_mod = _install_fake_lycoris(with_lokr_module=False)
        with patcher:
            with mock.patch.object(lycoris_patches, "_lycoris_lora_version", return_value="3.3.0"):
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
            with mock.patch.object(lycoris_patches, "_lycoris_lora_version", return_value="3.3.0"):
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


class _FakeTuckerConvLokrModule:
    """Minimal mimic of lycoris LokrModule, conv + tucker branch.

    3.3.0 shapes: w2_b (dim, vq), t2 (dim, dim, *k), w2_a (dim, vp);
    in_ch = uq * vq, out_ch = out_l * vp.
    """

    def __init__(self, dtype=torch.float32):
        self.module_type = "conv2d"
        self.use_w1 = False
        self.use_w2 = False
        self.tucker = True
        self.kw_dict = {}
        self.scalar = 1.0
        self.drop = lambda x: x
        self.op = F.conv2d
        self.shape = ((2, 5), (2, 3), 1, 1)  # ((out_l, vp), (uq, vq), k1, k2)
        uq, vq, dim, vp, out_l, r = 2, 3, 4, 5, 2, 3
        self.lokr_w2_b = torch.nn.Parameter(torch.randn(dim, vq, dtype=dtype) * 0.02)
        self.lokr_t2 = torch.nn.Parameter(torch.randn(dim, dim, 1, 1, dtype=dtype) * 0.02)
        self.lokr_w2_a = torch.nn.Parameter(torch.randn(dim, vp, dtype=dtype) * 0.02)
        self.lokr_w1_a = torch.nn.Parameter(torch.randn(out_l, r, dtype=dtype) * 0.02)
        self.lokr_w1_b = torch.nn.Parameter(torch.randn(r, uq, dtype=dtype) * 0.02)


class PatchedTuckerConvTests(unittest.TestCase):
    """Regression for the two stacked upstream conv-bypass bugs: the `b`
    shadowing and the (dim, vp) vs (vp, dim) orientation of w2_a."""

    patched = staticmethod(lycoris_patches._make_patched_bypass_forward_diff())

    def test_tucker_conv_runs_and_matches_reference(self):
        module = _FakeTuckerConvLokrModule()
        h = torch.randn(2, 6, 3, 3)  # (batch, uq*vq, H, W)

        out = self.patched(module, h)
        self.assertEqual(out.shape, (2, 10, 3, 3))  # out_l * vp channels

        # reference: same contraction with explicitly correct orientation
        a = module.lokr_w2_b.view(4, 3, 1, 1)
        b = module.lokr_w2_a.mT.reshape(5, 4, 1, 1)
        c = module.lokr_w1_a @ module.lokr_w1_b
        h_in_group = h.reshape(2 * 2, 3, 3, 3)
        ha = F.conv2d(h_in_group, a)
        ht = F.conv2d(ha, module.lokr_t2)
        hb = F.conv2d(ht, b)
        hb = hb.view(2, -1, *hb.shape[1:])
        h_cross_group = hb.transpose(1, -1)
        hc = F.linear(h_cross_group, c)
        ref = hc.transpose(1, -1).reshape(2, -1, 3, 3)

        self.assertTrue(torch.allclose(out, ref, atol=1e-5))

    def test_tucker_conv_bf16_activation_fp32_weights(self):
        module = _FakeTuckerConvLokrModule()
        h = torch.randn(2, 6, 3, 3, dtype=torch.bfloat16)

        out = self.patched(module, h)

        self.assertEqual(out.dtype, torch.bfloat16)
        self.assertTrue(torch.isfinite(out.float()).all())


if __name__ == "__main__":
    unittest.main()
