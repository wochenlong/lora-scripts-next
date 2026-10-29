"""离线从固定wheel归档和固定uv/Python生成GUI登记恢复可信文件索引。"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import shutil
import subprocess
import tarfile
import zipfile

RECIPE_SHA = "8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090"
def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
def path_ok(name):
    p = PurePosixPath(name)
    if not name or "\\" in name or p.is_absolute() or any(x in ("", ".", "..") for x in name.split("/")):
        raise ValueError(f"unsafe archive path: {name}")
    return p
def mapped(name, data):
    path_ok(name)
    if name.startswith(data + "/"):
        category, rest = name[len(data) + 1:].split("/", 1)
        if category in ("purelib", "platlib"):
            return "Lib/site-packages/" + rest
        if category == "scripts":
            return "Scripts/" + rest
        if category == "data":
            return rest
        raise ValueError(f"unsupported wheel data category {category}")
    return "Lib/site-packages/" + name

def generate(args):
    recipe_bytes = args.recipe.read_bytes()
    if hashlib.sha256(recipe_bytes).hexdigest() != RECIPE_SHA:
        raise ValueError("fixed recipe raw SHA mismatch")
    recipe = json.loads(recipe_bytes)
    manifest_bytes=args.python_manifest.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest()!='9172037fe65f76c9fe9373bf3240887889d480a569bfd785d6832e086ab96e06':
        raise ValueError('fixed Python original-file manifest identity differs')
    manifest = json.loads(manifest_bytes)
    expected = {x["path"]: x for x in manifest["files"] + manifest["uv_generated_files"]}
    if digest(args.uv) != recipe["tool_uv"]["exe_sha256"]:
        raise ValueError("fixed uv executable differs")
    # The old E-drive source may have runtime-generated extra bytecode. Never run
    # that installed tree or delete its files: independently copy only fixed
    # manifest members into a new closed trusted fixture and verify every copy.
    controlled_target = args.control_base / manifest["installation_directory"]
    if controlled_target.exists():
        raise ValueError("trusted control base path must be absent")
    archive = args.python_archive
    if archive.stat().st_size != recipe['python']['archive']['bytes'] or digest(archive) != recipe['python']['archive']['sha256']:
        raise ValueError("fixed original Python archive identity differs")
    source_expected = {x['path']: x for x in manifest['files']}
    seen = set()
    with tarfile.open(archive, 'r:gz') as source:
        for entry in source:
            path_ok(entry.name.rstrip('/'))
            if entry.isdir():
                continue
            if not entry.isfile() or not entry.name.startswith('python/'):
                raise ValueError('Python archive contains a special or foreign member')
            relative = entry.name[len('python/'):]
            if relative in seen or relative not in source_expected:
                raise ValueError('Python archive contains duplicate or unknown file')
            seen.add(relative)
            expected_entry = source_expected[relative]
            if entry.size != expected_entry['bytes']:
                raise ValueError('Python archive member length differs')
            destination = controlled_target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(entry) as input, destination.open('xb') as output:
                shutil.copyfileobj(input, output, 65536)
            if digest(destination) != expected_entry['sha256']:
                raise ValueError('Python archive member digest differs')
    if seen != set(source_expected):
        raise ValueError('Python archive closure incomplete')
    generated = {'BUILD': recipe['python']['build'].encode(), 'Lib/EXTERNALLY-MANAGED': b'[externally-managed]\nError=This Python installation is managed by uv and should not be modified.\n'}
    for relative, content in generated.items():
        expected_entry = expected[relative]
        if len(content) != expected_entry['bytes'] or hashlib.sha256(content).hexdigest() != expected_entry['sha256']:
            raise ValueError('fixed Python generated control identity differs')
        destination = controlled_target / relative
        with destination.open('xb') as output:
            output.write(content)
    target = controlled_target
    if args.control.exists():
        raise ValueError("control fixture path must be absent")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("UV_", "PIP_", "PYTHON"))}
    env.update(UV_OFFLINE="1", UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never", PYTHONDONTWRITEBYTECODE="1",
               UV_CACHE_DIR=str(args.output.parent / "control-cache"), HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9", NO_PROXY="")
    result = subprocess.run([str(args.uv), "--no-config", "--offline", "venv", "--python", str(target / "python.exe"), str(args.control)],
                            env=env, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)
    (args.output.parent / "control-uv.stdout.log").write_bytes(result.stdout)
    (args.output.parent / "control-uv.stderr.log").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("trusted control venv creation failed")
    controls = []
    for path in sorted(args.control.rglob("*")):
        if path.is_symlink():
            raise ValueError("control venv has a reparse file")
        if not path.is_file():
            continue
        relative = str(path.relative_to(args.control)).replace("\\", "/")
        raw = path.read_bytes()
        row = {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if relative == "pyvenv.cfg":
            row["kind"] = "pyvenv_config"
        elif relative.lower().endswith((".exe", ".dll", ".pth", ".py")) or relative in (".gitignore", "CACHEDIR.TAG"):
            row["kind"] = "fixed"
        else:
            text = raw.decode("utf-8")
            text = text.replace(str(args.control), "{{ENVIRONMENT}}")
            text = text.replace(str(args.control).replace("\\", "/"), "{{ENVIRONMENT_SLASH}}")
            text = text.replace(args.control.name, "{{ENVIRONMENT_NAME}}")
            row["kind"] = "template"
            row["template"] = text
        controls.append(row)
    packages = []
    all_paths = set()
    for asset in sorted(recipe["wheels"], key=lambda x: x["name"]):
        archive = args.wheelhouse / asset["filename"]
        if archive.stat().st_size != asset["bytes"] or digest(archive) != asset["sha256"]:
            raise ValueError(f"wheel archive identity differs: {asset['filename']}")
        parts = asset["filename"].split("-")
        dist, data = f"{parts[0]}-{parts[1]}.dist-info", f"{parts[0]}-{parts[1]}.data"
        rows, source_paths, record, entry_points = [], set(), None, None
        with zipfile.ZipFile(archive) as wheel:
            if len(wheel.infolist()) > 100000:
                raise ValueError("wheel entry bound")
            for entry in wheel.infolist():
                path_ok(entry.filename.rstrip("/"))
                mode = (entry.external_attr >> 16) & 0o170000
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("wheel special file")
                if entry.is_dir():
                    continue
                if entry.filename in source_paths:
                    raise ValueError("wheel source alias")
                source_paths.add(entry.filename)
                name = mapped(entry.filename, data)
                if name.lower() in all_paths:
                    raise ValueError(f"wheel installed alias: {name}")
                all_paths.add(name.lower())
                h, count = hashlib.sha256(), 0
                with wheel.open(entry) as file:
                    for chunk in iter(lambda: file.read(65536), b""):
                        count += len(chunk)
                        if count > 512 * 1024**2:
                            raise ValueError("wheel member bound")
                        h.update(chunk)
                if count != entry.file_size:
                    raise ValueError("wheel member length")
                if entry.filename == dist + "/RECORD":
                    record = wheel.read(entry).decode("utf-8")
                    continue
                if entry.filename == dist + "/entry_points.txt":
                    entry_points = wheel.read(entry).decode("utf-8")
                rows.append({"path": name, "bytes": count, "sha256": h.hexdigest()})
        if record is None or {x[0] for x in csv.reader(io.StringIO(record))} != source_paths:
            raise ValueError("wheel RECORD source set differs")
        packages.append({"name": asset["name"], "version": asset["version"], "archive_sha256": asset["sha256"],
                         "dist_info": dist, "originals": sorted(rows, key=lambda x: x["path"]), "entry_points": entry_points,
                         "license": asset["licenses"]})
    output = {"schema_version": 1, "recipe_id": recipe["id"], "recipe_sha256": RECIPE_SHA,
              "uv_exe_sha256": recipe["tool_uv"]["exe_sha256"], "python_archive_sha256": recipe["python"]["archive"]["sha256"],
              "source": "fixed-sha256-wheel-archives-and-isolated-fixed-uv-venv", "controls": controls, "packages": packages}
    raw = (json.dumps(output, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    with args.output.open("xb") as file:
        file.write(raw)
    print(json.dumps({"index": str(args.output), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                      "packages": len(packages), "original_files": sum(len(x["originals"]) for x in packages), "controls": len(controls)}, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("recipe", "python-manifest", "python-archive", "uv", "control-base", "control", "wheelhouse", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    generate(parser.parse_args())
