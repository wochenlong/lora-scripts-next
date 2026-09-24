import os
import sys
from mikazuki.log import log

try:
    import tkinter
    from tkinter.filedialog import askdirectory, askopenfilename
    _TKINTER_AVAILABLE = True
except ImportError:
    tkinter = None
    askdirectory = None
    askopenfilename = None
    _TKINTER_AVAILABLE = False


def _warn_tkinter_missing_once() -> None:
    if _TKINTER_AVAILABLE:
        return
    if getattr(_warn_tkinter_missing_once, "_logged", False):
        return
    _warn_tkinter_missing_once._logged = True  # type: ignore[attr-defined]
    exe = sys.executable.replace("\\", "/").lower()
    if "python_embeded" in exe or "python_embedded" in exe:
        log.warning(
            "tkinter not found in portable Python; folder/file picker will not work. "
            "Type paths manually, or rebuild the portable package with tkinter bundled "
            "(see build-scripts/build_portable.ps1)."
        )
    else:
        log.warning(
            "tkinter not found, file selector will not work. "
            "Install tkinter for your Python (e.g. python3-tk on Linux)."
        )

last_dir = ""


class NativePickerError(RuntimeError):
    """Raised when tkinter cannot create or operate a native picker."""


def tk_window():
    window = tkinter.Tk()
    window.wm_attributes('-topmost', 1)
    window.withdraw()


def tkinter_available() -> bool:
    return _TKINTER_AVAILABLE


def open_file_selector(
        initialdir="",
        title="Select a file",
        filetypes="*") -> str:
    _warn_tkinter_missing_once()
    if not _TKINTER_AVAILABLE:
        return ""
    global last_dir
    if last_dir != "":
        initialdir = last_dir
    elif initialdir == "":
        initialdir = os.getcwd()
    try:
        tk_window()
        filename = askopenfilename(
            initialdir=initialdir, title=title,
            filetypes=filetypes
        )
        last_dir = os.path.dirname(filename)
        return filename
    except Exception as exc:
        log.exception("Native file picker failed")
        raise NativePickerError(str(exc)) from exc


def open_directory_selector(initialdir) -> str:
    _warn_tkinter_missing_once()
    if not _TKINTER_AVAILABLE:
        return ""
    global last_dir
    if last_dir != "":
        initialdir = last_dir
    elif initialdir == "":
        initialdir = os.getcwd()
    try:
        tk_window()
        directory = askdirectory(
            initialdir=initialdir
        )
        last_dir = directory
        return directory
    except Exception as exc:
        log.exception("Native directory picker failed")
        raise NativePickerError(str(exc)) from exc
