from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import torch

SD_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "sd-scripts"
if str(SD_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SD_SCRIPTS_ROOT))

from library.optimizers.automagic import Automagic


def _train_a_few_steps(optimizer: Automagic, param: torch.nn.Parameter, steps: int = 3) -> None:
    for _ in range(steps):
        param.grad = torch.randn_like(param)
        optimizer.step()


class AutomagicResumeTest(unittest.TestCase):
    def _roundtrip(self, device: str) -> tuple[Automagic, torch.nn.Parameter]:
        torch.manual_seed(0)
        param = torch.nn.Parameter(torch.randn(8, 8, device=device))
        optimizer = Automagic([param], lr=1e-6)
        _train_a_few_steps(optimizer, param)
        saved = optimizer.state_dict()
        saved_mask = optimizer.state[param]["lr_mask"].dequantize()

        with tempfile.TemporaryDirectory() as tmp:
            blob = Path(tmp) / "optimizer.bin"
            torch.save(saved, blob)
            loaded = torch.load(blob, map_location="cpu", weights_only=False)

        new_param = torch.nn.Parameter(param.detach().clone())
        new_optimizer = Automagic([new_param], lr=1e-6)
        new_optimizer.load_state_dict(loaded)

        restored_mask = new_optimizer.state[new_param]["lr_mask"].dequantize()
        self.assertTrue(
            torch.allclose(restored_mask.cpu(), saved_mask.cpu()),
            "lr_mask values must survive a save/load roundtrip",
        )
        return new_optimizer, new_param

    def test_resume_roundtrip_cpu(self):
        optimizer, param = self._roundtrip("cpu")
        _train_a_few_steps(optimizer, param, steps=1)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required for device-mismatch regression")
    def test_resume_after_cpu_map_location_load(self):
        optimizer, param = self._roundtrip("cuda")
        mask = optimizer.state[param]["lr_mask"]
        self.assertEqual(
            mask.quantized.device,
            param.device,
            "accelerate loads optimizer state with map_location='cpu'; "
            "restored lr_mask must be moved back to the param device",
        )
        _train_a_few_steps(optimizer, param, steps=1)

    def test_resume_with_unstepped_params_keeps_alignment(self):
        torch.manual_seed(0)
        params = [
            torch.nn.Parameter(torch.randn(4, 8)),
            torch.nn.Parameter(torch.randn(6, 6)),  # never receives a gradient
            torch.nn.Parameter(torch.randn(8, 4)),
        ]
        optimizer = Automagic(params, lr=1e-6)
        for _ in range(3):
            params[0].grad = torch.randn_like(params[0])
            params[2].grad = torch.randn_like(params[2])
            optimizer.step()
        self.assertNotIn(params[1], optimizer.state)
        saved = optimizer.state_dict()
        saved_masks = [optimizer.state[params[i]]["lr_mask"].dequantize() for i in (0, 2)]

        new_params = [torch.nn.Parameter(p.detach().clone()) for p in params]
        new_optimizer = Automagic(new_params, lr=1e-6)
        new_optimizer.load_state_dict(saved)

        for i, j in ((0, 0), (2, 1)):
            restored = new_optimizer.state[new_params[i]]["lr_mask"].dequantize()
            self.assertTrue(
                torch.allclose(restored, saved_masks[j]),
                f"param {i} must restore its own lr_mask even when an earlier param has no state",
            )


if __name__ == "__main__":
    unittest.main()
