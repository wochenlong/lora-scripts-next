"""生成本地锁定依赖与原始声明清单；只读缓存，不访问网络。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tomllib


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    launcher = Path(__file__).resolve().parents[1]
    output = launcher / "LICENSES"
    output.mkdir(exist_ok=True)
    cargo_base = Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))) / "registry" / "src"
    registry_roots = sorted(cargo_base.glob("*")) if cargo_base.is_dir() else []
    packages: dict[tuple[str, str, str], dict] = {}
    locks: dict[str, str] = {}
    for relative in ["src-tauri/Cargo.lock", "shell-updater/Cargo.lock"]:
        lock_bytes = (launcher / relative).read_bytes()
        locks[relative] = sha(lock_bytes)
        for package in tomllib.loads(lock_bytes.decode("utf-8"))["package"]:
            if not package.get("source", "").startswith("registry+"):
                continue
            key = ("cargo", package["name"], package["version"])
            entry = packages.setdefault(key, {"ecosystem": key[0], "name": key[1], "version": key[2], "lockfiles": [], "license": None, "source": package["source"], "cache_status": "missing", "license_files": []})
            entry["lockfiles"].append(relative)
            candidates = [root / f"{key[1]}-{key[2]}" for root in registry_roots]
            cache = next((path for path in candidates if (path / "Cargo.toml").is_file()), None)
            if cache:
                metadata = tomllib.loads((cache / "Cargo.toml").read_text(encoding="utf-8"))["package"]
                entry.update(license=metadata.get("license"), repository=metadata.get("repository"), cache_status="present", _cache=cache)
                license_file = metadata.get("license-file") or metadata.get("license_file")
                if license_file and (cache / license_file).is_file():
                    entry["license_files"].append(license_file)
    npm_lock = launcher / "package-lock.json"
    locks["package-lock.json"] = sha(npm_lock.read_bytes())
    for relative, package in json.loads(npm_lock.read_text(encoding="utf-8"))["packages"].items():
        if not relative:
            continue
        name = package.get("name") or relative.rsplit("node_modules/", 1)[-1]
        version = package.get("version", "unknown")
        cache = launcher / relative
        metadata = {}
        if (cache / "package.json").is_file():
            metadata = json.loads((cache / "package.json").read_text(encoding="utf-8"))
        entry = {"ecosystem": "npm", "name": name, "version": version, "lockfiles": ["package-lock.json"], "license": package.get("license") or metadata.get("license"), "source": package.get("resolved"), "build_only": bool(package.get("dev")), "optional": bool(package.get("optional")), "cache_status": "present" if metadata else "missing", "license_files": []}
        if metadata:
            entry["_cache"] = cache
        packages[("npm", name, version)] = entry
    notices = ["# 第三方原始许可与声明", "", "按当前锁文件从本机缓存提取。包含构建依赖和其他平台的锁定依赖；缓存缺失请查 dependencies.json，不将本文件当作未提取项已审结。", ""]
    manifest = []
    for key, entry in sorted(packages.items()):
        cache = entry.pop("_cache", None)
        if cache:
            for path in sorted(cache.iterdir()):
                if path.is_file() and path.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT")) and path.stat().st_size <= 2 * 1024 * 1024:
                    entry["license_files"].append(path.name)
            entry["license_files"] = sorted(set(entry["license_files"]))
            contents = []
            supplemental = []
            # 单独平台包通常只装二进制；同版本主包的许可可直接本地提取，但标注关联来源，
            # 不把主包文本伪称为二进制子包自身携带的独立声明。
            related = None
            if key[0] == "npm" and key[1] == "@tauri-apps/cli-win32-x64-msvc":
                related = launcher / "node_modules/@tauri-apps/cli"
            elif key[0] == "npm" and key[1] == "@rolldown/binding-win32-x64-msvc":
                related = launcher / "node_modules/rolldown"
            if related and (related / "package.json").is_file():
                related_meta = json.loads((related / "package.json").read_text(encoding="utf-8"))
                if related_meta.get("version") == key[2]:
                    for path in sorted(related.iterdir()):
                        if path.is_file() and path.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "THIRD-PARTY-LICENSE")):
                            raw = path.read_bytes()
                            supplemental.append({"kind": "same_version_parent_package", "source": str(path.relative_to(launcher)), "sha256": sha(raw), "text": raw.decode("utf-8", errors="replace")})
            if not entry["license_files"] and key[0] == "cargo":
                # 有些crate只含源码头部许可。只提取原头部，不重构缺失完整文本。
                for path in [cache / "lib.rs", cache / "src/lib.rs"]:
                    if path.is_file():
                        text = path.read_text(encoding="utf-8", errors="replace")
                        if text.startswith("/*") and "*/" in text[:4096]:
                            header = text[:text.index("*/") + 2]
                            if "license" in header.lower() or "copyright" in header.lower():
                                supplemental.append({"kind": "source_header_only", "source": str(path.relative_to(cache)), "sha256": sha(header.encode()), "text": header})
                                break
            for relative in entry["license_files"]:
                path = cache / relative
                if not path.resolve().is_relative_to(cache.resolve()):
                    raise ValueError("许可文件超出缓存包")
                raw = path.read_bytes()
                contents.append({"path": relative, "sha256": sha(raw)})
                notices.extend([f"## {key[0]} / {key[1]} {key[2]} / {relative}", "", f"声明许可：`{entry['license'] or 'unknown'}`；来源：`{entry.get('source')}`；原文 SHA256：`{sha(raw)}`。", "", "````text", raw.decode("utf-8", errors="replace").replace("````", "` ` ` `"), "````", ""])
            entry["license_files"] = contents
            entry["supplemental_notices"] = []
            for record in supplemental:
                text = record.pop("text")
                entry["supplemental_notices"].append(record)
                notices.extend([f"## {key[0]} / {key[1]} {key[2]} / 关联声明", "", f"来源类型：`{record['kind']}`；位置：`{record['source']}`；摘要：`{record['sha256']}`。该段不代替缺失的包内完整许可。", "", "````text", text.replace("````", "` ` ` `"), "````", ""])
        entry["license_text_status"] = "extracted" if entry["license_files"] else "not_found_in_available_cache"
        manifest.append(entry)
    stats = {"packages": len(manifest), "cache_missing": sum(entry["cache_status"] == "missing" for entry in manifest), "license_unknown": sum(not entry["license"] for entry in manifest), "license_text_missing": sum(not entry["license_files"] for entry in manifest)}
    data = {"schema_version": 1, "scope": "launcher+helper+frontend locked dependencies including build/optional platforms; excludes downloaded trainer environments", "lock_sha256": locks, "summary": stats, "dependencies": manifest}
    (output / "dependencies.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Markdown展示统一换行和行尾空白；上列SHA始终来自原许可文件字节。
    rendered = "\n".join(line.rstrip() for line in "\n".join(notices).splitlines()).rstrip() + "\n"
    (output / "THIRD-PARTY-NOTICES.md").write_text(rendered, encoding="utf-8", newline="\n")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
