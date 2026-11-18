from __future__ import annotations

from pathlib import Path
import sys
import unittest

import torch
from torch import nn


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"
sys.path.insert(0, str(VENDOR_ROOT))

from library.anima_models import Block, FinalLayer  # noqa: E402


class _Passthrough(nn.Module):
    def forward(self, x, *_args, **_kwargs):
        return x.to(torch.get_autocast_dtype(x.device.type))


@unittest.skipUnless(torch.cuda.is_available(), "CUDA is required for bf16 autocast")
class AnimaDoraBf16DtypeTests(unittest.TestCase):
    def test_final_layer_runs_modulation_in_fp32_and_returns_bf16(self):
        layer = FinalLayer(8, 1, 1, 8).cuda().eval()
        x = torch.randn(1, 1, 1, 1, 8, device="cuda", dtype=torch.bfloat16)
        embedding = torch.randn(1, 1, 8, device="cuda", dtype=torch.bfloat16)
        modulation_dtypes = []
        hook = layer.adaln_modulation[1].register_forward_hook(
            lambda _module, _inputs, output: modulation_dtypes.append(output.dtype)
        )

        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = layer(x, embedding, use_fp32=False)
        hook.remove()

        self.assertEqual(modulation_dtypes, [torch.float32])
        self.assertEqual(output.dtype, torch.bfloat16)

    def test_block_runs_modulation_in_fp32_and_keeps_bf16_residual(self):
        block = Block(8, 8, 1).cuda().eval()
        block.self_attn = _Passthrough()
        block.cross_attn = _Passthrough()
        block.mlp = _Passthrough()
        x = torch.randn(1, 1, 1, 1, 8, device="cuda", dtype=torch.bfloat16)
        embedding = torch.randn(1, 1, 8, device="cuda", dtype=torch.bfloat16)
        context = torch.randn(1, 1, 8, device="cuda", dtype=torch.bfloat16)
        modulation_dtypes = []
        hooks = [
            modulation[1].register_forward_hook(
                lambda _module, _inputs, output: modulation_dtypes.append(output.dtype)
            )
            for modulation in (
                block.adaln_modulation_self_attn,
                block.adaln_modulation_cross_attn,
                block.adaln_modulation_mlp,
            )
        ]

        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = block._forward(x, embedding, context, None, use_fp32=False)
        for hook in hooks:
            hook.remove()

        self.assertEqual(modulation_dtypes, [torch.float32] * 3)
        self.assertEqual(output.dtype, torch.bfloat16)


if __name__ == "__main__":
    unittest.main()
