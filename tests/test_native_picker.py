from __future__ import annotations

import asyncio
from unittest.mock import Mock

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


@pytest.mark.parametrize(
    ("picker_type", "title", "file_types"),
    [
        (
            "model-file",
            "Select file",
            [("checkpoints", "*.safetensors;*.ckpt;*.pt"), ("all files", "*.*")],
        ),
        (
            "image",
            "Select image",
            [("images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff"), ("all files", "*.*")],
        ),
    ],
)
def test_pick_file_uses_open_file_dialog_with_matching_filters(monkeypatch, picker_type, title, file_types):
    monkeypatch.setattr(api.path_browser_utils, "gui_picker_available", lambda: True)
    monkeypatch.setattr(tk_window, "_TKINTER_AVAILABLE", True)
    monkeypatch.setattr(tk_window, "tk_window", lambda: None)
    monkeypatch.setattr(tk_window, "last_dir", "")
    open_file = Mock(return_value="D:/images/preview.png")
    open_folder = Mock(side_effect=AssertionError("file selection must not open the folder dialog"))
    monkeypatch.setattr(tk_window, "askopenfilename", open_file)
    monkeypatch.setattr(tk_window, "askdirectory", open_folder)

    response = asyncio.run(api.pick_file(picker_type))

    assert response.status == "success"
    assert response.data == {"path": "D:/images/preview.png"}
    open_file.assert_called_once()
    assert open_file.call_args.kwargs["title"] == title
    assert open_file.call_args.kwargs["filetypes"] == file_types
    open_folder.assert_not_called()


def test_pick_file_folder_keeps_directory_dialog(monkeypatch):
    monkeypatch.setattr(api.path_browser_utils, "gui_picker_available", lambda: True)
    monkeypatch.setattr(tk_window, "_TKINTER_AVAILABLE", True)
    monkeypatch.setattr(tk_window, "tk_window", lambda: None)
    monkeypatch.setattr(tk_window, "last_dir", "")
    open_file = Mock(side_effect=AssertionError("folder selection must not open the file dialog"))
    open_folder = Mock(return_value="D:/images")
    monkeypatch.setattr(tk_window, "askopenfilename", open_file)
    monkeypatch.setattr(tk_window, "askdirectory", open_folder)

    response = asyncio.run(api.pick_file("folder"))

    assert response.status == "success"
    assert response.data == {"path": "D:/images"}
    open_folder.assert_called_once()
    open_file.assert_not_called()


def test_pick_file_image_cancellation_keeps_cancelled_response(monkeypatch):
    monkeypatch.setattr(api.path_browser_utils, "gui_picker_available", lambda: True)
    monkeypatch.setattr(api, "open_file_selector", Mock(return_value=""))

    response = asyncio.run(api.pick_file("image"))

    assert response.status == "fail"
    assert response.data == {"code": "CANCELLED", "web_picker": True}


def test_image_web_fallback_filter_lists_images_and_preserves_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(api.path_browser_utils, "gui_picker_available", lambda: False)
    (tmp_path / "nested").mkdir()
    image_names = {
        "preview" + ext
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
    } | {"preview-upper.PNG"}
    for name in image_names | {"model.safetensors", "caption.txt"}:
        (tmp_path / name).write_bytes(b"test")

    native_response = asyncio.run(api.pick_file("image"))
    assert native_response.data == {"code": "GUI_PICKER_UNAVAILABLE", "web_picker": True}
    web_response = asyncio.run(api.path_browser_list(
        str(tmp_path),
        mode="file",
        name_filter="*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff",
    ))

    assert web_response.status == "success"
    entries = {entry["name"]: entry["type"] for entry in web_response.data["entries"]}
    assert entries == {"nested": "dir", **dict.fromkeys(image_names, "file")}
