"""Download locked public inputs into a new rebuild root after Phase4 approval.

Never links/copies probe assets, resumes a failed root, or handles credentials.
The caller must first close the explicit blocked_gates in the audited manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def filename(value):
    if not isinstance(value, str) or Path(value).name != value or "/" in value or "\\" in value or value in {"", ".", ".."}:
        raise ValueError("input filename is invalid")
    return value


def download(opener, asset, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    count = 0
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "caption-isolated-rebuild"})
    with opener.open(request, timeout=60) as response, temporary.open("xb") as stream:
        while data := response.read(1024 * 1024):
            stream.write(data)
            digest.update(data)
            count += len(data)
        stream.flush()
        os.fsync(stream.fileno())
    if digest.hexdigest() != asset["sha256"] or (asset.get("size_bytes") is not None and count != asset["size_bytes"]):
        raise ValueError("download differs from the locked manifest")
    os.replace(temporary, target)
    return {"url": asset["url"], "filename": target.name, "sha256": digest.hexdigest(), "size_bytes": count,
            "downloaded_at": datetime.now(timezone.utc).isoformat(), "fresh_download": True}


def extract_runtime(archive, directory, expected):
    directory.mkdir()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("runtime archive contains a symbolic link")
            target = directory / entry.filename
            target.resolve().relative_to(directory.resolve())
        source.extractall(directory)
    candidates = list(directory.rglob("llama-server.exe"))
    if len(candidates) != 1 or hashlib.sha256(candidates[0].read_bytes()).hexdigest() != expected:
        raise ValueError("runtime executable differs from the locked manifest")
    return candidates[0].relative_to(directory).as_posix()


def validate_inputs(root):
    """Verify completed fresh downloads before another acceptance tool uses them."""
    root = Path(root).resolve()
    report = json.loads((root / "input-receipts.json").read_text(encoding="utf-8"))
    manifest_bytes = (root / "locked-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if not report.get("passed") or report["manifest_sha256"] != hashlib.sha256(manifest_bytes).hexdigest() or manifest.get("blocked_gates"):
        raise ValueError("fresh input receipts are not complete")
    for receipt in report["receipts"]:
        path = root / receipt["relative_path"]
        path.resolve().relative_to(root)
        if not receipt.get("fresh_download") or not path.is_file() or path.stat().st_size != receipt["size_bytes"]:
            raise ValueError("fresh input file is missing or changed")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != receipt["sha256"]:
            raise ValueError("fresh input digest differs")
    executable = root / report["runtime_executable"]
    executable.resolve().relative_to(root)
    if hashlib.sha256(executable.read_bytes()).hexdigest() != manifest["runtime"]["executable_sha256"]:
        raise ValueError("fresh runtime executable differs")
    return root, executable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--proxy", default="http://127.0.0.1:11809")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("blocked_gates"):
        parser.error("Phase4 gates remain open; no rebuild directory was created")
    root = args.root.resolve()
    if root.exists():
        parser.error("fresh rebuild input root must not exist; failed roots cannot be resumed")
    root.mkdir(parents=True)
    (root / "locked-manifest.json").write_bytes(args.manifest.read_bytes())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy}))
    report = {"schema_version": 1, "kind": "fresh-caption-rebuild-inputs", "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              "receipts": [], "passed": False}
    try:
        groups = [("samples", manifest["samples"]), ("vision", manifest["vision"]["files"]), ("tag-models/wd14/wd14-convnextv2-v2", manifest["onnx"]["files"])]
        for folder, assets in groups:
            for asset in assets:
                target = root / folder / filename(asset["filename"])
                receipt = download(opener, asset, target)
                receipt["relative_path"] = target.relative_to(root).as_posix()
                report["receipts"].append(receipt)
                print(json.dumps({"downloaded": asset["filename"], "sha256_verified": True}), flush=True)
        runtime = manifest["runtime"]
        archive_name = filename(runtime["url"].rsplit("/", 1)[-1])
        archive = root / "runtime-download" / archive_name
        receipt = download(opener, {"url": runtime["url"], "sha256": runtime["archive_sha256"], "size_bytes": runtime.get("size_bytes")}, archive)
        receipt["relative_path"] = archive.relative_to(root).as_posix()
        report["receipts"].append(receipt)
        report["runtime_executable"] = "runtime/" + extract_runtime(archive, root / "runtime", runtime["executable_sha256"])
        report["passed"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        print(json.dumps({"passed": False, "error_type": type(error).__name__, "new_root_required": True}), flush=True)
    finally:
        (root / "input-receipts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
