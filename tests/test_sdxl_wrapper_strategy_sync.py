from pathlib import Path


def test_sdxl_wrapper_uses_sdxl_text_encoding_strategy():
    wrapper = Path("scripts/stable/sdxl_train_network.py").read_text(encoding="utf-8")
    assert "strategy_sdxl.SdxlTextEncodingStrategy()" in wrapper
    assert "strategy_sd.SdTextEncodingStrategy" not in wrapper


def test_sdxl_wrapper_uses_dual_tokenizer_strategy():
    wrapper = Path("scripts/stable/sdxl_train_network.py").read_text(encoding="utf-8")
    assert "strategy_sdxl.SdxlTokenizeStrategy" in wrapper
    assert "tokenizer1" in wrapper and "tokenizer2" in wrapper
