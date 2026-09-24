from __future__ import annotations

import asyncio

import pytest

from mikazuki.app import api
from mikazuki.utils import tk_window
from mikazuki.utils.tk_window import NativePickerError


def test_directory_selector_distinguishes_runtime_error_from_cancel(monkeypatch):
    monkeypatch.setattr(tk_window, "_TKINTER_AVAILABLE", True)
    monkeypatch.setattr(
        tk_window,
        "tk_window",
        lambda: (_ for _ in ()).throw(RuntimeError("display unavailable")),
    )

    with pytest.raises(NativePickerError, match="display unavailable"):
        tk_window.open_directory_selector("")


def test_pick_file_reports_native_runtime_error_for_web_fallback(monkeypatch):
    monkeypatch.setattr(api.path_browser_utils, "gui_picker_available", lambda: True)
    monkeypatch.setattr(
        api,
        "open_directory_selector",
        lambda _initial: (_ for _ in ()).throw(NativePickerError("display unavailable")),
    )

    response = asyncio.run(api.pick_file("folder"))

    assert response.status == "fail"
    assert response.data == {
        "code": "NATIVE_PICKER_ERROR",
        "web_picker": True,
    }
