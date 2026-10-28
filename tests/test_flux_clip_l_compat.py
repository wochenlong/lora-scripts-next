import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"))

from library.flux_utils import _align_clip_l_state_dict_keys


class _FakeClip:
    def __init__(self, keys):
        self.keys = keys

    def state_dict(self):
        return {key: None for key in self.keys}


def test_clip_l_strips_prefix_for_transformers_with_bare_keys():
    weight = object()
    state_dict = {"text_model.encoder.layers.0.self_attn.k_proj.weight": weight}

    aligned = _align_clip_l_state_dict_keys(_FakeClip(["encoder.layers.0.self_attn.k_proj.weight"]), state_dict)

    assert aligned == {"encoder.layers.0.self_attn.k_proj.weight": weight}


def test_clip_l_keeps_prefix_for_transformers_with_prefixed_keys():
    weight = object()
    state_dict = {"text_model.encoder.layers.0.self_attn.k_proj.weight": weight}

    aligned = _align_clip_l_state_dict_keys(
        _FakeClip(["text_model.encoder.layers.0.self_attn.k_proj.weight"]), state_dict
    )

    assert aligned is state_dict
