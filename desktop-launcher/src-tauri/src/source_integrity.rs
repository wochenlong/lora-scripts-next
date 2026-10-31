//! 候选源码完整清单来自固定摘要的源码ZIP与捆绑前端，绝不信任app内自述清单。
use crate::model::{self, Layout, Release};
use anyhow::{bail, Context, Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    path::{Component, Path},
};

const RECIPE: &str = "gui-cp310-win-x64-v1";
const LEGACY_MANIFEST: &str = ".source-integrity.json";
const CURRENT_COMMIT: &str = "4e68df240c63ab7cf2156ea7fafabf18df4671e8";
const PREVIOUS_COMMIT: &str = "89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d";
const FRONTEND_SHA: &str = "ae77496b39c5b59bb0d4f4ca5b4a3bd3043499818828c0eeeb7227c653996b9f";

/// 每个支持的源码发布保留自己的可信清单；绝不从安装目录读取校验依据。
/// 历史清单原字节来自已保存提交 b2436b4a，使用独立摘要固定其身份。
struct EmbeddedManifest {
    commit: &'static str,
    archive_sha256: &'static str,
    archive_bytes: u64,
    file_count: usize,
    file_bytes: u64,
    manifest_sha256: &'static str,
    json: &'static str,
}
const CURRENT: EmbeddedManifest = EmbeddedManifest {
    commit: CURRENT_COMMIT,
    archive_sha256: "60490c2eceaccb4d59b22f17867b12e68c2a5041b995a3692a38adc6691c0cfd",
    archive_bytes: 92_918_164,
    file_count: 1942,
    file_bytes: 139_738_581,
    manifest_sha256: "faaa2671e84614b4905b352b26adedd62f0ba3e2cc8d5edee430b646cb9989a0",
    json: include_str!("../../catalog/gui-candidate-source-v1.json"),
};
const PREVIOUS: EmbeddedManifest = EmbeddedManifest {
    commit: PREVIOUS_COMMIT,
    archive_sha256: "e53af2a77aa39c1f5e876c5cc73e78329c2cd5c616d0d5af7ac3eea637577022",
    archive_bytes: 57_465_913,
    file_count: 1844,
    file_bytes: 103_757_791,
    manifest_sha256: "bce3945607a7ec7925e843cd236e93c8fcd0e7f013291b24d4d84abb3117eccd",
    json: include_str!("../../catalog/gui-source-89a3b6ca-v1.json"),
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Manifest {
    schema_version: u32,
    pub(crate) source_commit: String,
    source_archive_sha256: String,
    source_archive_bytes: u64,
    pub(crate) frontend_sha256: String,
    pub(crate) frontend_bytes: u64,
    expected_file_count: usize,
    expected_file_bytes: u64,
    pub(crate) files: Vec<Entry>,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Entry {
    pub(crate) path: String,
    bytes: u64,
    sha256: String,
}

fn relative(value: &str) -> Result<()> {
    let path = Path::new(value);
    if value.is_empty() || value.contains('\\') || path.is_absolute() {
        bail!("可信源码清单包含非法相对路径");
    }
    for part in path.components() {
        match part {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("源码路径不是UTF-8")?)?
            }
            _ => bail!("可信源码路径不允许跳转或盘符"),
        }
    }
    if value.split('/').any(|part| matches!(part, "" | "." | "..")) {
        bail!("可信源码路径包含空组成部分");
    }
    Ok(())
}
fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn fingerprint(layout: &Layout, path: &Path) -> Result<(u64, String)> {
    layout.guard_path(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() > model::MAX_EXTRACT_BYTES {
        bail!("源码项目不是受限普通文件");
    }
    let mut input = File::open(path)?;
    let mut digest = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0; 65536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes = bytes.checked_add(count as u64).context("源码长度溢出")?;
        if bytes > model::MAX_EXTRACT_BYTES {
            bail!("源码文件读取超限");
        }
        digest.update(&buffer[..count]);
    }
    Ok((bytes, format!("{:x}", digest.finalize())))
}
type EntrySpec<'a> = (BTreeMap<&'a str, &'a Entry>, BTreeSet<String>);

/// 静态清单和实际树使用同一套路径、摘要、计量及 Windows 名称校验。
fn entry_spec(entries: &[Entry]) -> Result<EntrySpec<'_>> {
    let mut expected = BTreeMap::new();
    let mut aliases = BTreeSet::new();
    let mut directories = BTreeSet::from([String::new()]);
    let mut total = 0u64;
    for entry in entries {
        relative(&entry.path)?;
        if entry.path == LEGACY_MANIFEST
            || !valid_sha(&entry.sha256)
            || entry.bytes > model::MAX_EXTRACT_BYTES
            || !aliases.insert(entry.path.to_ascii_lowercase())
            || expected.insert(entry.path.as_str(), entry).is_some()
        {
            bail!("可信源码清单摘要、长度无效或路径重复");
        }
        total = total.checked_add(entry.bytes).context("可信源码合计溢出")?;
        let mut parent = Path::new(&entry.path).parent();
        while let Some(path) = parent {
            directories.insert(path.to_string_lossy().replace('\\', "/"));
            parent = path.parent();
        }
    }
    if entries.is_empty() || total > model::MAX_EXTRACT_BYTES {
        bail!("可信源码清单为空或总长度超限");
    }
    let mut directory_aliases = BTreeSet::new();
    for directory in &directories {
        let alias = directory.to_ascii_lowercase();
        if aliases.contains(&alias) || !directory_aliases.insert(alias) {
            bail!("可信源码清单含文件目录冲突或 Windows 大小写目录别名");
        }
    }
    Ok((expected, directories))
}

fn verify_entries(layout: &Layout, entries: &[Entry]) -> Result<()> {
    let (expected, directories) = entry_spec(entries)?;
    for entry in entries {
        if fingerprint(layout, &layout.app.join(&entry.path))?
            != (entry.bytes, entry.sha256.clone())
        {
            bail!("候选源码缺失或改变：{}", entry.path);
        }
    }
    fn walk(
        layout: &Layout,
        directory: &Path,
        expected: &BTreeMap<&str, &Entry>,
        allowed_dirs: &BTreeSet<String>,
        seen: &mut BTreeSet<String>,
    ) -> Result<()> {
        layout.guard_path(directory)?;
        for item in fs::read_dir(directory)? {
            let item = item?;
            let path = item.path();
            layout.guard_path(&path)?;
            let relative = path
                .strip_prefix(&layout.app)?
                .to_str()
                .context("实际源码路径不是UTF-8")?
                .replace('\\', "/");
            if !seen.insert(relative.to_ascii_lowercase()) {
                bail!("候选源码存在Windows大小写路径别名");
            }
            let kind = item.file_type()?;
            if kind.is_dir() {
                if !allowed_dirs.contains(&relative) {
                    bail!("候选源码含额外目录：{relative}");
                }
                walk(layout, &path, expected, allowed_dirs, seen)?;
            } else if !kind.is_file()
                || (!expected.contains_key(relative.as_str()) && relative != LEGACY_MANIFEST)
            {
                bail!("候选源码含额外文件或非普通项目：{relative}");
            }
        }
        Ok(())
    }
    walk(
        layout,
        &layout.app,
        &expected,
        &directories,
        &mut BTreeSet::new(),
    )
}

fn decode_manifest(raw: &str, fixed: &EmbeddedManifest) -> Result<Manifest> {
    if format!("{:x}", Sha256::digest(raw.as_bytes())) != fixed.manifest_sha256 {
        bail!("可信源码清单原始摘要不匹配");
    }
    let manifest: Manifest = serde_json::from_str(raw)?;
    if manifest.schema_version != 1
        || manifest.source_commit != fixed.commit
        || manifest.source_archive_sha256 != fixed.archive_sha256
        || manifest.source_archive_bytes != fixed.archive_bytes
        || manifest.frontend_sha256 != FRONTEND_SHA
        || manifest.frontend_bytes != 2_446_848
        || manifest.expected_file_count != manifest.files.len()
        || manifest.expected_file_count != fixed.file_count
        || manifest.expected_file_bytes != fixed.file_bytes
    {
        bail!("可信源码清单身份或 schema 无效");
    }
    let bytes = manifest.files.iter().try_fold(0u64, |total, entry| {
        total.checked_add(entry.bytes).context("可信源码合计溢出")
    })?;
    if bytes != manifest.expected_file_bytes || bytes > model::MAX_EXTRACT_BYTES {
        bail!("可信源码清单合计长度无效");
    }
    entry_spec(&manifest.files)?;
    Ok(manifest)
}

/// 完整性检查和源码修复计划都从此入口取得已验证的可信闭包。
/// 这里只读取内嵌数据，不访问源码树，也不修改受管状态。
pub(crate) fn trusted_manifest(release: &Release) -> Result<Manifest> {
    release.validate()?;
    let fixed = match release.commit.as_str() {
        CURRENT_COMMIT => &CURRENT,
        PREVIOUS_COMMIT => &PREVIOUS,
        _ => bail!("该发布版本没有匹配的可信完整源码清单"),
    };
    if release.environment_recipe != RECIPE
        || release.archive.sha256 != fixed.archive_sha256
        || release.archive.bytes != fixed.archive_bytes
        || release.archive.unpacked_bytes != fixed.file_bytes
    {
        bail!("该发布版本与可信完整源码清单身份不符");
    }
    decode_manifest(fixed.json, fixed)
}

pub(crate) fn supports(release: &Release) -> bool {
    trusted_manifest(release).is_ok()
}

pub(crate) fn verify(layout: &Layout, release: &Release) -> Result<()> {
    let manifest = trusted_manifest(release)?;
    verify_entries(layout, &manifest.files)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "nt-source-manifest-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
        fn layout(&self) -> Layout {
            let layout = Layout::new(&self.0, &format!("dev-{}", "a".repeat(40))).unwrap();
            layout
                .ensure_dir(&layout.app.join("frontend/dist"))
                .unwrap();
            layout
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            if self.0.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .0
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-source-manifest-")
            {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
    }
    fn entry(path: &str, bytes: &[u8]) -> Entry {
        Entry {
            path: path.into(),
            bytes: bytes.len() as u64,
            sha256: format!("{:x}", Sha256::digest(bytes)),
        }
    }
    #[test]
    fn trusted_entries_ignore_local_manifest_but_detect_code_changes_and_omissions() {
        let fixture = Fixture::new();
        let layout = fixture.layout();
        let entries = vec![
            entry("gui.py", b"original"),
            entry("frontend/dist/index.html", b"bundled"),
        ];
        fs::write(layout.app.join("gui.py"), b"original").unwrap();
        fs::write(layout.app.join("frontend/dist/index.html"), b"bundled").unwrap();
        verify_entries(&layout, &entries).unwrap(); // 本地自述manifest不存在也可验证。
        fs::write(
            layout.app.join(LEGACY_MANIFEST),
            b"{not trusted, can be corrupt}",
        )
        .unwrap();
        verify_entries(&layout, &entries).unwrap();
        fs::write(layout.app.join("gui.py"), b"tampered").unwrap();
        assert!(verify_entries(&layout, &entries).is_err());
        fs::write(layout.app.join("gui.py"), b"original").unwrap();
        fs::remove_file(layout.app.join("frontend/dist/index.html")).unwrap();
        assert!(verify_entries(&layout, &entries).is_err());
    }
    #[test]
    fn unexpected_files_directories_and_case_aliases_are_rejected() {
        let fixture = Fixture::new();
        let layout = fixture.layout();
        let entries = vec![
            entry("gui.py", b"original"),
            entry("frontend/dist/index.html", b"bundled"),
        ];
        fs::write(layout.app.join("gui.py"), b"original").unwrap();
        fs::write(layout.app.join("frontend/dist/index.html"), b"bundled").unwrap();
        fs::write(layout.app.join("injected.py"), b"extra").unwrap();
        assert!(verify_entries(&layout, &entries).is_err());
        fs::remove_file(layout.app.join("injected.py")).unwrap();
        fs::create_dir(layout.app.join("__pycache__")).unwrap();
        assert!(verify_entries(&layout, &entries).is_err());
        assert!(
            verify_entries(&layout, &[entries[0].clone(), entry("GUI.py", b"original")]).is_err()
        );
    }
    #[test]
    fn unknown_schema_fields_and_wrong_release_are_rejected() {
        let raw = include_str!("../../catalog/gui-candidate-source-v1.json");
        let mut value: serde_json::Value = serde_json::from_str(raw).unwrap();
        value["future_field"] = true.into();
        assert!(serde_json::from_value::<Manifest>(value).is_err());
        let fixture = Fixture::new();
        let layout = fixture.layout();
        let release = model::Catalog::embedded()
            .unwrap()
            .releases
            .into_iter()
            .find(|release| !matches!(release.commit.as_str(), CURRENT_COMMIT | PREVIOUS_COMMIT))
            .unwrap();
        assert!(verify(&layout, &release).is_err());
        let manifest: Manifest = serde_json::from_str(raw).unwrap();
        assert_eq!(manifest.expected_file_count, 1942);
        assert_eq!(manifest.expected_file_bytes, 139738581);
    }

    #[test]
    fn embedded_current_and_previous_manifests_match_exact_release_identities() {
        let catalog = model::Catalog::embedded().unwrap();
        for fixed in [&CURRENT, &PREVIOUS] {
            let release = catalog
                .releases
                .iter()
                .find(|release| release.commit == fixed.commit)
                .unwrap();
            let manifest = trusted_manifest(release).unwrap();
            assert!(supports(release));
            assert_eq!(manifest.files.len(), fixed.file_count);
            assert_eq!(manifest.expected_file_bytes, fixed.file_bytes);
            assert_eq!(
                manifest.files.iter().map(|entry| entry.bytes).sum::<u64>(),
                fixed.file_bytes
            );
            assert!(manifest
                .files
                .iter()
                .any(|entry| entry.path == "frontend/dist/index.html"));
            assert!(manifest.files.iter().any(|entry| entry.path == "gui.py"));
            let mut wrong_archive = release.clone();
            wrong_archive.archive.sha256 = "a".repeat(64);
            assert!(!supports(&wrong_archive));
            let mut wrong_length = release.clone();
            wrong_length.archive.bytes += 1;
            assert!(!supports(&wrong_length));
            let mut wrong_expanded_length = release.clone();
            wrong_expanded_length.archive.unpacked_bytes += 1;
            assert!(!supports(&wrong_expanded_length));
        }
        for release in catalog
            .releases
            .iter()
            .filter(|release| !matches!(release.commit.as_str(), CURRENT_COMMIT | PREVIOUS_COMMIT))
        {
            assert!(!supports(release));
        }
        assert_eq!(
            PREVIOUS.manifest_sha256,
            "bce3945607a7ec7925e843cd236e93c8fcd0e7f013291b24d4d84abb3117eccd"
        );
    }

    #[test]
    fn modified_embedded_manifest_bytes_cannot_replace_trusted_history() {
        for fixed in [&CURRENT, &PREVIOUS] {
            let changed = fixed.json.replacen("gui.py", "gui.pz", 1);
            assert_ne!(changed, fixed.json);
            assert!(decode_manifest(&changed, fixed).is_err());
        }
    }

    #[test]
    fn trusted_manifest_metadata_rejects_unsafe_paths_sizes_and_aliases() {
        assert!(entry_spec(&[entry("../gui.py", b"unsafe")]).is_err());
        assert!(entry_spec(&[entry("dir\\gui.py", b"unsafe")]).is_err());
        assert!(entry_spec(&[entry("dir", b"file"), entry("dir/gui.py", b"file")]).is_err());
        assert!(entry_spec(&[entry("Dir/a.py", b"a"), entry("dir/b.py", b"b")]).is_err());
        let mut invalid_digest = entry("gui.py", b"x");
        invalid_digest.sha256 = "g".repeat(64);
        assert!(entry_spec(&[invalid_digest]).is_err());
        let mut excessive = entry("gui.py", b"x");
        excessive.bytes = model::MAX_EXTRACT_BYTES + 1;
        assert!(entry_spec(&[excessive]).is_err());
    }
}
