import sys
import types

import pytest

from mikazuki.app.train_submit import _detect_best_attn_mode
from mikazuki.portable_utils import train_env_overrides


def test_detect_best_attn_mode_prefers_flash_when_stack_usable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.app.train_submit.flash_attn_stack_usable", lambda: True)
    assert _detect_best_attn_mode() == "flash"


def test_detect_best_attn_mode_uses_xformers_without_flash(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.app.train_submit.flash_attn_stack_usable", lambda: False)
    monkeypatch.setitem(sys.modules, "xformers", types.ModuleType("xformers"))
    assert _detect_best_attn_mode() == "xformers"


def test_detect_best_attn_mode_uses_torch_without_flash_or_xformers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.app.train_submit.flash_attn_stack_usable", lambda: False)
    # sys.modules["xformers"] = None makes `import xformers` raise ImportError
    # even when xformers is installed in the environment.
    monkeypatch.setitem(sys.modules, "xformers", None)
    assert _detect_best_attn_mode() == "torch"


def test_train_env_overrides_skips_sdpa_when_flash_usable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.portable_utils.is_embedded_python", lambda executable=None: True)
    monkeypatch.setattr("mikazuki.portable_utils.flash_attn_stack_usable", lambda: True)
    assert train_env_overrides() == {"XFORMERS_FORCE_DISABLE_TRITON": "1"}


def test_train_env_overrides_sets_sdpa_when_flash_unusable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.portable_utils.is_embedded_python", lambda executable=None: True)
    monkeypatch.setattr("mikazuki.portable_utils.flash_attn_stack_usable", lambda: False)
    assert train_env_overrides() == {
        "XFORMERS_FORCE_DISABLE_TRITON": "1",
        "TRANSFORMERS_ATTN_IMPLEMENTATION": "sdpa",
    }


def test_train_env_overrides_empty_on_non_embedded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mikazuki.portable_utils.is_embedded_python", lambda executable=None: False)
    assert train_env_overrides() == {}
