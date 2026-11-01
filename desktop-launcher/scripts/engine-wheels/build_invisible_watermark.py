#!/usr/bin/env python3
"""从固定官方源码正常构建只使用 headless OpenCV 的发行方 wheel。

只修改 setup.py 中版本和依赖声明；不安装训练环境，不修改安装后元数据。
"""
from __future__ import annotations

import argparse
import base64
import csv
import difflib
import email
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def item(data: bytes) -> dict:
    return {"bytes": len(data), "sha256": digest(data)}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def extract_source(archive: bytes, manifest: dict, destination: Path) -> dict[str, bytes]:
    files = {}
    expected_root = manifest["source"]["root"]
    expanded_bytes = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        for member in source.getmembers():
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and ".." not in name.parts and "\\" not in member.name,
                    f"源归档路径不安全: {member.name}")
            require(name.parts and name.parts[0] == expected_root, "源归档根目录不一致")
            require(member.isdir() or member.isfile(), f"不接受链接或特殊归档条目: {member.name}")
            if member.isdir():
                continue
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            require(relative not in files, f"源归档重复路径: {relative}")
            expanded_bytes += member.size
            require(expanded_bytes <= 20_000_000, "源归档超出小包展开上限")
            data = source.extractfile(member).read()
            require(len(data) == member.size, "源归档内容大小不一致")
            write_new(destination.joinpath(*name.parts[1:]), data)
            files[relative] = data
    return files


def inspect_wheel(wheel: Path, original: dict[str, bytes], manifest: dict) -> dict:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "wheel包含重复路径")
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_name))
        require(metadata["Name"] == manifest["name"], "wheel包名不一致")
        require(metadata["Version"] == manifest["local_version"], "wheel必须使用明确本地版本")
        dependencies = metadata.get_all("Requires-Dist", [])
        compact = [value.replace(" ", "") for value in dependencies]
        require(manifest["dependency_change"]["new"] in compact, "headless依赖未进入构建产物")
        require(not any(value.startswith("opencv-python>=") for value in compact), "wheel仍要求冲突GUI版")
        unchanged = {}
        for relative, raw in original.items():
            if relative.startswith("imwatermark/"):
                require(relative in names, f"wheel缺少上游包文件: {relative}")
                require(archive.read(relative) == raw, f"运行代码或模型数据发生变化: {relative}")
                unchanged[relative] = item(raw)
        require(unchanged, "未检查到运行源码")
        license_name = next(name for name in names if name.endswith("/LICENSE"))
        require(archive.read(license_name) == original["LICENSE"], "wheel未保留上游原LICENSE")
        record_name = next(name for name in names if name.endswith(".dist-info/RECORD"))
        records = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
        require({row[0] for row in records} == set(names), "wheel RECORD未覆盖全部文件")
        for name, recorded_hash, recorded_size in records:
            if name == record_name:
                require(recorded_hash == recorded_size == "", "RECORD自身必须无摘要")
                continue
            raw = archive.read(name)
            wanted = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode("ascii")
            require(recorded_hash == wanted and int(recorded_size) == len(raw), f"wheel RECORD摘要不符: {name}")
        return {"name": metadata["Name"], "version": metadata["Version"], "requires_dist": dependencies,
                "metadata": item(archive.read(metadata_name)), "license": item(archive.read(license_name)),
                "unchanged_upstream_package_files": unchanged,
                "all_runtime_source_and_bundled_data_byte_identical": True,
                "normal_build_generated_record_validated": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="全新构建目录，必须不存在")
    parser.add_argument("--uv", type=Path, required=True, help="既有uv可执行文件")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="构建解释器，不安装运行依赖")
    parser.add_argument("--source-archive", type=Path, help="可复用已下载的固定原归档，仍核大小和SHA")
    parser.add_argument("--proxy", help="仅构建子进程与固定下载使用的HTTP/HTTPS代理")
    parser.add_argument("--cache-dir", type=Path, help="可选uv构建缓存；默认在独占work-dir中")
    parser.add_argument("--output-dir", type=Path, help="可选复制到正式wheel目录；同名不允许不同字节")
    args = parser.parse_args()
    manifest_path = HERE / "invisible-watermark-source.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    require(args.uv.is_file() and args.python.is_file(), "构建工具/解释器不存在")
    work = args.work_dir.resolve()
    require(not work.exists(), "构建目录必须全新，不覆盖既有证据")
    work.mkdir(parents=True)
    archive_path = work / manifest["source"]["filename"]
    if args.source_archive:
        raw = args.source_archive.read_bytes()
    else:
        proxy = {"http": args.proxy, "https": args.proxy} if args.proxy else {}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy))
        request = urllib.request.Request(manifest["source"]["url"], headers={"User-Agent": "NextTrainer-WheelPublisher"})
        with opener.open(request, timeout=60) as response:
            raw = response.read(manifest["source"]["bytes"] + 1)
    require(item(raw) == {"bytes": manifest["source"]["bytes"], "sha256": manifest["source"]["sha256"]}, "官方源归档大小或SHA不匹配")
    write_new(archive_path, raw)
    source_dir = work / "source"
    original = extract_source(raw, manifest, source_dir)
    require(digest(original["setup.py"]) == manifest["source"]["setup_sha256"], "上游setup.py不符")
    require(digest(original["LICENSE"]) == manifest["source"]["license_sha256"], "上游LICENSE不符")
    old_text = original["setup.py"].decode("utf-8")
    replacements = [(f"version='{manifest['upstream_version']}'", f"version='{manifest['local_version']}'"),
                    (manifest["dependency_change"]["old"], manifest["dependency_change"]["new"])]
    new_text = old_text
    for old, new in replacements:
        require(new_text.count(old) == 1, f"预期setup.py只出现一次: {old}")
        new_text = new_text.replace(old, new)
    computed_patch = "".join(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                                fromfile="a/setup.py", tofile="b/setup.py", n=0)).encode("utf-8")
    patch_raw = (HERE / manifest["patch"]).read_bytes()
    require(computed_patch == patch_raw, "锁定补丁不等于setup.py实际两处修改")
    (source_dir / "setup.py").write_bytes(new_text.encode("utf-8"))
    require(all((source_dir / relative).read_bytes() == data for relative, data in original.items() if relative != "setup.py"), "setup.py外源文件改变")
    constraints = HERE / manifest["build_constraints"]
    require(constraints.read_text(encoding="utf-8").splitlines() == ["setuptools==80.9.0", "wheel==0.45.1"], "构建依赖须固定为既有M2版本")
    output = work / "wheels"
    command = [str(args.uv.resolve()), "build", "--wheel", "--python", str(args.python.resolve()),
               "--build-constraint", str(constraints), "--out-dir", str(output), str(source_dir)]
    env = os.environ.copy()
    env.update({"SOURCE_DATE_EPOCH": manifest["source_date_epoch"], "PYTHONHASHSEED": "0",
                "UV_CACHE_DIR": str((args.cache_dir or work / "uv-cache").resolve())})
    if args.proxy:
        env.update({"HTTP_PROXY": args.proxy, "HTTPS_PROXY": args.proxy})
    with (work / "build.stdout.log").open("xb") as stdout, (work / "build.stderr.log").open("xb") as stderr:
        result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=300)
    require(result.returncode == 0, f"正常wheel构建失败，见 {work / 'build.stderr.log'}")
    wheel = output / manifest["expected_wheel"]
    require(wheel.is_file() and len(list(output.glob("*.whl"))) == 1, "输出wheel不符合固定名称")
    require(item(wheel.read_bytes()) == {"bytes": manifest["expected_wheel_bytes"], "sha256": manifest["expected_wheel_sha256"]},
            "重建wheel字节与已登记固定产物不一致")
    inspected = inspect_wheel(wheel, original, manifest)
    provenance = {"schema_version": 1, "manifest": item(manifest_raw), "build_script": item(Path(__file__).read_bytes()),
                  "source": manifest["source"],
                  "patch": {"filename": manifest["patch"], **item(patch_raw)},
                  "setup_before": item(original["setup.py"]), "setup_after": item(new_text.encode("utf-8")),
                  "build_constraints": {"filename": constraints.name, **item(constraints.read_bytes())},
                  "source_date_epoch": env["SOURCE_DATE_EPOCH"], "pythonhashseed": env["PYTHONHASHSEED"],
                  "build_command": command, "build_exit": result.returncode,
                  "uv": subprocess.check_output([str(args.uv.resolve()), "--version"], text=True).strip(),
                  "python": subprocess.check_output([str(args.python.resolve()), "--version"], text=True).strip(),
                  "wheel": {"filename": wheel.name, **item(wheel.read_bytes())}, "inspection": inspected,
                  "source_files": {relative: item(data) for relative, data in sorted(original.items())},
                  "installed_environment_modified": False, "training_started": False,
                  "post_build_wheel_metadata_modified": False}
    write_new(work / "provenance.json", (json.dumps(provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir / wheel.name
        if target.exists():
            require(target.read_bytes() == wheel.read_bytes(), "正式输出存在不同字节同名wheel，不覆盖")
        else:
            shutil.copyfile(wheel, target)
    print(json.dumps({"wheel": str(wheel), "provenance": str(work / "provenance.json"),
                      "sha256": provenance["wheel"]["sha256"], "bytes": provenance["wheel"]["bytes"],
                      "runtime_payload_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
