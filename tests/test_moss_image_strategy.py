import sys
from pathlib import Path

import torch


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "sd-scripts"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))


def test_moss_text_encoder_cache_uses_common_four_argument_contract(tmp_path):
    from library.strategy_moss_image import MossImageTextEncoderOutputsCachingStrategy

    class Info:
        def __init__(self, caption, name):
            self.caption = caption
            self.caption_dropout_rate = 0.0
            self.text_encoder_outputs_npz = str(tmp_path / f"{name}.npz")
            self.text_encoder_outputs = None

    class Tokenize:
        seen = None

        def tokenize(self, captions):
            self.seen = captions
            return captions

    class Encode:
        def encode_tokens(self, tokenize_strategy, models, tokens):
            del tokenize_strategy, models
            batch = len(tokens)
            return [
                torch.ones((batch, 2, 3), dtype=torch.bfloat16),
                torch.ones((batch, 2), dtype=torch.int32),
            ]

    infos = [Info("first caption", "first"), Info("second caption", "second")]
    tokenize = Tokenize()
    strategy = MossImageTextEncoderOutputsCachingStrategy(
        cache_to_disk=False,
        batch_size=2,
        skip_disk_cache_validity_check=False,
    )
    strategy.get_uncond_embeds = lambda *_: torch.ones((1, 3), dtype=torch.bfloat16)

    # train_util calls every TextEncoderOutputsCachingStrategy with these four
    # arguments; MOSS must derive captions from infos like the other strategies.
    strategy.cache_batch_outputs(tokenize, [object()], Encode(), infos)

    assert tokenize.seen == ["first caption", "second caption"]
    assert all(info.text_encoder_outputs is not None for info in infos)
