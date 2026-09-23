import json
import re
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MANIFEST_FILENAME = "mikazuki-dataset.json"
MIN_PAIRED_IMAGES = 3
REPEATS_DIR = re.compile(r"^\d+_")
VALID_TYPES = {"image", "image_edit"}


def _result(type_, confidence, targets=None, refs=None, reason=None):
    return {"type": type_, "confidence": confidence, "targets": targets, "refs": refs or [], "reason": reason}


def _manifest_override(dataset_dir: Path) -> dict | None:
    path = dataset_dir / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict) or data.get("type") not in VALID_TYPES:
        return None
    targets = data.get("targets")
    refs = data.get("refs")
    return _result(
        data["type"],
        "override",
        targets=targets if isinstance(targets, str) and targets else None,
        refs=[item for item in refs if isinstance(item, str)] if isinstance(refs, list) else [],
    )


def image_rel_paths(subtree: Path) -> frozenset:
    return frozenset(
        path.relative_to(subtree).as_posix()
        for path in subtree.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _has_caption(subtree: Path, image_set: frozenset) -> bool:
    return any((subtree / rel).with_suffix(".txt").is_file() for rel in image_set)


OVERLAP_RATIO = 0.8


def _paired(a: frozenset, b: frozenset) -> bool:
    shared = len(a & b)
    return shared >= MIN_PAIRED_IMAGES and shared >= OVERLAP_RATIO * min(len(a), len(b))


def detect_dataset_type(dataset_dir: Path) -> dict:
    override = _manifest_override(dataset_dir)
    if override:
        return override

    candidates: dict[str, frozenset] = {}
    for child in sorted(dataset_dir.iterdir()):
        if not child.is_dir() or child.is_symlink() or child.name.startswith(".") or REPEATS_DIR.match(child.name):
            continue
        image_set = image_rel_paths(child)
        if image_set:
            candidates[child.name] = image_set

    names = list(candidates)
    parent = {name: name for name in names}

    def find(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    any_overlap = False
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = candidates[a] & candidates[b]
            if shared:
                any_overlap = True
            if _paired(candidates[a], candidates[b]):
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(find(name), []).append(name)
    paired = sorted((members for members in groups.values() if len(members) >= 2), key=lambda members: (-len(members), members))
    if not paired:
        if any_overlap:
            return _result("image", "candidate", reason="subtrees share images but below pairing threshold")
        return _result("image", "detected")

    members = sorted(paired[0])
    captioned = [name for name in members if _has_caption(dataset_dir / name, candidates[name])]
    if len(captioned) != 1:
        return _result("image_edit", "ambiguous", reason="captioned subtree unclear" if not captioned else f"multiple captioned subtrees {captioned}")
    targets = captioned[0]
    refs = [name for name in members if name != targets]
    return _result("image_edit", "detected", targets=targets, refs=refs)
