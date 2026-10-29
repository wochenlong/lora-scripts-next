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

const SOURCE_COMMIT: &str = "196ff12c16083d59c8be6711476c6fdb70c7112a";
const RECIPE: &str = "gui-cp310-win-x64-v1";
const SOURCE_SHA: &str = "37c69b284528b21e256ba9c1a4ca90ad4a4ffe8d0122e9ba7416e45f3f3899e9";
const FRONTEND_SHA: &str = "3c97a03bc4554248936ee4cbba6bb3f12bc413aecbbac9633400986da6801da1";
const LEGACY_MANIFEST: &str = ".source-integrity.json";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema_version: u32,
    source_commit: String,
    source_archive_sha256: String,
    source_archive_bytes: u64,
    frontend_sha256: String,
    frontend_bytes: u64,
    expected_file_count: usize,
    expected_file_bytes: u64,
    files: Vec<Entry>,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    path: String,
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
fn verify_entries(layout: &Layout, entries: &[Entry]) -> Result<()> {
    let mut expected = BTreeMap::new();
    let mut aliases = BTreeSet::new();
    let mut directories = BTreeSet::from([String::new()]);
    for entry in entries {
        relative(&entry.path)?;
        if entry.path == LEGACY_MANIFEST
            || !valid_sha(&entry.sha256)
            || !aliases.insert(entry.path.to_ascii_lowercase())
            || expected.insert(entry.path.as_str(), entry).is_some()
        {
            bail!("可信源码清单摘要无效或路径重复");
        }
        let mut parent = Path::new(&entry.path).parent();
        while let Some(path) = parent {
            directories.insert(path.to_string_lossy().replace('\\', "/"));
            parent = path.parent();
        }
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

pub(crate) fn verify(layout: &Layout, release: &Release) -> Result<()> {
    if release.commit != SOURCE_COMMIT
        || release.environment_recipe != RECIPE
        || release.archive.sha256 != SOURCE_SHA
        || release.archive.bytes != 49_234_359
    {
        bail!("该发布版本没有匹配的可信完整源码清单");
    }
    let manifest: Manifest =
        serde_json::from_str(include_str!("../../catalog/gui-candidate-source-v1.json"))?;
    if manifest.schema_version != 1
        || manifest.source_commit != SOURCE_COMMIT
        || manifest.source_archive_sha256 != SOURCE_SHA
        || manifest.source_archive_bytes != release.archive.bytes
        || manifest.frontend_sha256 != FRONTEND_SHA
        || manifest.frontend_bytes != 2_440_912
        || manifest.expected_file_count != manifest.files.len()
        || manifest.files.len() != 1741
    {
        bail!("可信源码清单身份或schema无效");
    }
    let bytes = manifest.files.iter().try_fold(0u64, |total, entry| {
        total.checked_add(entry.bytes).context("可信源码合计溢出")
    })?;
    if bytes != manifest.expected_file_bytes || bytes > model::MAX_EXTRACT_BYTES {
        bail!("可信源码清单合计长度无效");
    }
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
            .find(|release| release.commit != SOURCE_COMMIT)
            .unwrap();
        assert!(verify(&layout, &release).is_err());
        let manifest: Manifest = serde_json::from_str(raw).unwrap();
        assert_eq!(manifest.expected_file_count, 1741);
        assert_eq!(manifest.expected_file_bytes, 86_405_908);
    }
}
