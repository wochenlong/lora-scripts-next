from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "sd-scripts"))

from library.anima_utils import normalize_anima_checkpoint_key  # noqa: E402


class AnimaCheckpointKeyNormalizationTests(unittest.TestCase):
    def test_accepts_known_save_prefixes(self):
        expected = "x_embedder.proj.1.weight"

        self.assertEqual(normalize_anima_checkpoint_key(f"net.{expected}"), expected)
        self.assertEqual(normalize_anima_checkpoint_key(expected), expected)
        self.assertEqual(normalize_anima_checkpoint_key(f"model.diffusion_model.{expected}"), expected)
        self.assertEqual(normalize_anima_checkpoint_key(f"diffusion_model.{expected}"), expected)


if __name__ == "__main__":
    unittest.main()
