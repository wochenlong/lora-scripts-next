"""Keep runtime maintenance out of an active kogine run, including after a UI restart."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mikazuki.engines.kohaku_moss.extension_state import check_runtime
from mikazuki.engines.kohaku_moss.resource import environment_lock
from mikazuki.engines.kohaku_moss.settings import Runtime


def main():
    runtime = Runtime(Path(sys.argv[1]).resolve())
    with environment_lock(runtime.root):
        check_runtime(runtime)
        sys.path.insert(0, str(runtime.source / "src"))  # Editable .pth paths may predate a portable move.
        from kohakuengine.cli import main as kogine
        kogine(sys.argv[2:])


if __name__ == "__main__":
    main()
