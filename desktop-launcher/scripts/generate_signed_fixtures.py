"""从当前固定配方重建公开 Ed25519 测试夹具；不提供生产签名能力。

运行需要 Python 3.11+ 和 cryptography，仅使用 RFC8032 已公开的测试种子。
夹具只有在启动器显式创建的新沙盒会话内才获得测试信任，不能作为生产发布
或远程更新的凭据。时间固定，不读取系统时钟；输入只读，输出路径必须显式指定。

候选配方变化时，先成组更新内置 catalog 与 Rust 信任摘要，再重新生成夹具；
本脚本只写 --output 指定的 JSON，不修改信任锚或现有源码。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib


LAUNCHER = Path(__file__).resolve().parents[1]
ISSUED_AT = 1793145600
EXPIRES_AT = 1893456000
ROOT_ID = "public-fixture-root-v1"
ROTATED_ID = "public-fixture-rotated-v2"
# RFC8032 section 7.1, TEST 1 and TEST 2. These are public test material.
PUBLIC_TEST_KEYS = {
    ROOT_ID: (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    ),
    ROTATED_ID: (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
    ),
}
ACTIONS = [
    "download_source",
    "isolated_entry_probe",
    "uv_locked_sync",
    "uv_venv",
    "verify_environment",
]


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 含重复字段：{key}")
        result[key] = value
    return result


def read_json(raw: bytes) -> dict:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"JSON 不支持常量：{value}")

    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )


def ordered(value: dict, fields: tuple[str, ...], label: str) -> dict:
    """按 Rust struct 声明顺序重建，遇到 schema 漂移必须显式修订脚本。"""
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{label} 字段与当前 Rust schema 不符")
    return {key: value[key] for key in fields}


def canonical_release(value: dict) -> dict:
    result = ordered(value, (
        "schema_version", "id", "channel", "version", "commit", "archive",
        "python", "uv", "environment_recipe", "profile_schema_version",
        "data_contract", "required_files",
    ), "Release")
    result["archive"] = ordered(result["archive"], (
        "url", "sha256", "bytes", "unpacked_bytes",
    ), "Archive")
    result["uv"] = ordered(result["uv"], (
        "version", "url", "sha256", "exe_sha256", "bytes",
    ), "UvAsset")
    return result


def canonical(value: object) -> str:
    def reject_floats(item: object) -> None:
        if isinstance(item, float):
            raise ValueError("签名 payload 不允许浮点数")
        if isinstance(item, dict):
            for child in item.values():
                reject_floats(child)
        elif isinstance(item, list):
            for child in item:
                reject_floats(child)

    reject_floats(value)
    # 不可 sort_keys：Rust serde 按结构体声明顺序重新编码并逐字校验。
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def public_test_signers() -> dict:
    # 延迟导入，--help 在未安装可选生成依赖时也可阅读。
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as error:
        raise ValueError("生成夹具需要 Python cryptography；--help 不依赖此模块") from error

    signers = {}
    for key_id, (seed_hex, expected_public_hex) in PUBLIC_TEST_KEYS.items():
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        actual = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        ).hex()
        if actual != expected_public_hex:
            raise ValueError(f"RFC8032 公开测试公钥不匹配：{key_id}")
        signers[key_id] = key
    return signers


def generate(recipe_raw: bytes, catalog_raw: bytes, shell_version: str) -> tuple[dict, dict]:
    recipe = read_json(recipe_raw)
    catalog = read_json(catalog_raw)
    if (recipe["schema_version"] != 1 or recipe["platform"] != "windows-x86_64"
            or recipe["candidate_only"] is not True or catalog["schema_version"] != 1):
        raise ValueError("只支持当前 Windows 候选配方和 v1 catalog 测试合同")
    matches = [item for item in catalog["releases"]
               if item["commit"] == recipe["source_commit"]
               and item["environment_recipe"] == recipe["id"]]
    if len(matches) != 1:
        raise ValueError("catalog 必须恰有一项与 recipe.source_commit 和 id 匹配")
    release = canonical_release(matches[0])
    if release["schema_version"] != 1 or release["profile_schema_version"] != 1:
        raise ValueError("只支持 v1 release/profile schema")
    recipe_sha = hashlib.sha256(recipe_raw).hexdigest()
    signed_release = {
        "release": release,
        "published_at": ISSUED_AT,
        "recipe_sha256": recipe_sha,
        "actions": ACTIONS.copy(),
    }
    signers = public_test_signers()

    def envelope(payload: dict, key_id: str) -> dict:
        text = canonical(payload)
        raw = text.encode("utf-8")
        signature = signers[key_id].sign(raw)
        # 每份输出在落盘前独立验签，不复用现有 JSON 中的任何签名文本。
        signers[key_id].public_key().verify(signature, raw)
        return {
            "schema_version": 1,
            "key_id": key_id,
            "payload": text,
            "signature_hex": signature.hex(),
        }

    def payload(sequence: int, *, include_release: bool = False,
                rotate: bool = False, revoke: bool = False,
                issued_at: int = ISSUED_AT, expires_at: int = EXPIRES_AT,
                platform: str = "windows-x86_64") -> dict:
        return {
            "schema_version": 1,
            "encoding": "nt-catalog-json-v1",
            "channel": "fixture",
            "sequence": sequence,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "platform": platform,
            "min_shell": shell_version,
            "profile_schema_version": 1,
            "releases": [signed_release] if include_release else [],
            "rotations": [{
                "key_id": ROTATED_ID,
                "public_key_hex": PUBLIC_TEST_KEYS[ROTATED_ID][1],
            }] if rotate else [],
            "revoked_keys": [],
            "revoked_releases": [release["id"]] if revoke else [],
        }

    valid = envelope(payload(1, include_release=True, rotate=True), ROOT_ID)
    fixtures = {
        "valid-v1": valid,
        "rotate-v2": envelope(payload(2, include_release=True), ROTATED_ID),
        "revoke-v3": envelope(payload(3, revoke=True), ROTATED_ID),
        "expired": envelope(payload(4, issued_at=1577836800, expires_at=1609459200), ROTATED_ID),
        "wrong-platform": envelope(payload(4, platform="linux-x86_64"), ROTATED_ID),
        "replay": valid.copy(),
        "shell-self-copy-policy": envelope({
            "schema_version": 1,
            "policy_id": "current-shell-self-copy-v1",
            "channel": "fixture",
            "platform": "windows-x86_64",
            "action": "replace_shell_self_copy",
            "current_relative": "shell-fixture/current/NextTrainerLauncher.exe",
            "candidate_relative": "shell-fixture/candidate/NextTrainerLauncher.exe",
            "max_bytes": 1073741824,
            "issued_at": ISSUED_AT,
            "expires_at": EXPIRES_AT,
        }, ROOT_ID),
    }
    return fixtures, {
        "scope": "public RFC8032 development fixtures only; not production trust",
        "release_id": release["id"],
        "source_commit": recipe["source_commit"],
        "recipe_sha256": recipe_sha,
        "min_shell": shell_version,
        "fixtures": list(fixtures),
        "verified_signatures": len(fixtures),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="必须显式指定输出 JSON 路径；默认拒绝覆盖已有文件")
    parser.add_argument("--recipe", type=Path,
                        default=LAUNCHER / "catalog/gui-cp310-win-x64-v1.json")
    parser.add_argument("--catalog", type=Path, default=LAUNCHER / "catalog/releases.json")
    parser.add_argument("--cargo-manifest", type=Path, default=LAUNCHER / "src-tauri/Cargo.toml",
                        help="读取 package.version 作为固定 min_shell")
    parser.add_argument("--force", action="store_true", help="显式允许覆盖指定输出文件")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.is_symlink() or (output.exists() and not args.force):
        parser.error("输出已存在或为符号链接；请选择新路径，或对普通文件显式使用 --force")
    if output.exists() and not output.is_file():
        parser.error("输出必须是普通文件路径")
    try:
        recipe_raw = args.recipe.read_bytes()
        catalog_raw = args.catalog.read_bytes()
        shell_version = tomllib.loads(args.cargo_manifest.read_text(encoding="utf-8"))["package"]["version"]
        fixtures, report = generate(recipe_raw, catalog_raw, shell_version)
        raw = (json.dumps(fixtures, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb" if args.force else "xb") as stream:
            stream.write(raw)
        report.update(output=str(output), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"生成公开测试夹具失败：{error}\n")


if __name__ == "__main__":
    main()
