"""Verify and apply the bundled MOSS batch and preview patch."""
import hashlib
import subprocess
from pathlib import Path

PATCH_FILE = Path(__file__).with_name("patches") / "batched_training.patch"
from .manifest import UPSTREAM

PATCHED_FILES = {'library/moss/batching.py': 'a4e3c250792ec1d82ad7954623601fcb794566ccd356befcc2633bdff554e1fa',
 'library/moss/lora.py': '95b5eb24dbf28ccc9a72012095e19160598e8a53b8d8bbe932b61d1cfb8a436b',
 'library/moss/preview.py': 'a920709bd15fc3d1582ebafcec2bd776301c4ae74b562925acebde28dc91f445',
 'library/moss/requests.py': '7cd805ff20cead8918c5a6c06defedb5bfe024eb5a912563d333ed036934b764',
 'library/moss/train.py': '79ec8c076c57a22b4a89e35fe5784bb17a645a70542131c96a507a777e68cf0e'}


def verify_source(runtime):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(runtime.source), *args], text=True).strip()
    if git('rev-parse', 'HEAD') != UPSTREAM['commit']:
        raise ValueError('MOSS upstream commit differs from the pinned source')
    changed = set(filter(None, git('diff', '--name-only', 'HEAD', '--').splitlines()))
    changed.update(filter(None, git('ls-files', '--others', '--exclude-standard').splitlines()))
    if changed != set(PATCHED_FILES):
        raise ValueError('MOSS source drift outside the bundled patch: ' + repr(sorted(changed)))
    for name, expected in PATCHED_FILES.items():
        path = runtime.source/name
        contents = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else b""
        if not path.is_file() or hashlib.sha256(contents).hexdigest() != expected:
            raise ValueError('MOSS bundled patch fingerprint mismatch: ' + name)
    return {'local_patch_files': sorted(changed), 'source_commit': UPSTREAM['commit']}


def apply_source_patch(source):
    from types import SimpleNamespace
    runtime = SimpleNamespace(source=Path(source))
    try:
        verify_source(runtime)
        return
    except ValueError:
        pass
    def git(*args):
        return subprocess.check_output(["git", "-C", str(runtime.source), *args], text=True).strip()
    if git("rev-parse", "HEAD") != UPSTREAM["commit"]:
        raise ValueError("MOSS source commit differs from the pinned source")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Refusing to patch modified MOSS source; repair the engine")
    patch = PATCH_FILE.read_text(encoding="utf-8").encode("utf-8")
    subprocess.run(["git", "-C", str(runtime.source), "apply", "--check", "-"], input=patch, check=True)
    subprocess.run(["git", "-C", str(runtime.source), "apply", "-"], input=patch, check=True)
    verify_source(runtime)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", required=True, metavar="SOURCE")
    apply_source_patch(parser.parse_args().apply)
