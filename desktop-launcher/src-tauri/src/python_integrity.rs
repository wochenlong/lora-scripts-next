//! 固定 Python 归档的完整文件闭包；不运行解释器，也不信任安装目录自述摘要。
use crate::model::{self, Layout};
use anyhow::{bail, Context, Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    path::{Component, Path, PathBuf},
};

const VERSION: &str = "3.10.19";
const BUILD: &str = "20260211";
const TARGET: &str = "cpython-3.10.19-windows-x86_64-none";
const ALIAS: &str = "cpython-3.10-windows-x86_64-none";
const ARCHIVE: &str =
    "cpython-3.10.19+20260211-x86_64-pc-windows-msvc-install_only_stripped.tar.gz";
const ARCHIVE_SHA: &str = "b892f2c7eb0a04611688d6df7567a2745a204aac694d6d1c56c75b0717dab2d6";
const EXTERNALLY_MANAGED: &[u8] =
    b"[externally-managed]\nError=This Python installation is managed by uv and should not be modified.\n";
const MAX_FILE: u64 = 8 * 1024 * 1024;
const MAX_TREE: u64 = 64 * 1024 * 1024;
const MAX_NODES: usize = 5_000;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema_version: u32,
    python_version: String,
    python_build: String,
    python_abi: String,
    platform: String,
    archive_name: String,
    archive_sha256: String,
    archive_bytes: u64,
    archive_root: String,
    installation_directory: String,
    minor_alias: String,
    original_file_count: usize,
    original_file_bytes: u64,
    original_pyc_count: usize,
    expected_directory_count: usize,
    files: Vec<Entry>,
    uv_generated_files: Vec<Entry>,
    optional_root_files: Vec<Entry>,
    optional_empty_root_directories: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Entry {
    path: String,
    bytes: u64,
    sha256: String,
}

struct Spec {
    files: BTreeMap<String, Entry>,
    directories: BTreeSet<String>,
}

fn entry(path: &str, content: &[u8]) -> Entry {
    Entry {
        path: path.into(),
        bytes: content.len() as u64,
        sha256: format!("{:x}", Sha256::digest(content)),
    }
}

fn relative(value: &str) -> Result<()> {
    if value.is_empty()
        || value.contains('\\')
        || Path::new(value).is_absolute()
        || value.split('/').any(|part| matches!(part, "" | "." | ".."))
    {
        bail!("可信 Python 清单含非法相对路径");
    }
    for part in Path::new(value).components() {
        match part {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("Python 路径不是 UTF-8")?)?
            }
            _ => bail!("可信 Python 路径不允许跳转或盘符"),
        }
    }
    Ok(())
}

fn spec(entries: impl IntoIterator<Item = Entry>) -> Result<Spec> {
    let mut files = BTreeMap::new();
    let mut directories = BTreeSet::from([String::new()]);
    let mut total = 0u64;
    for entry in entries {
        relative(&entry.path)?;
        if entry.bytes > MAX_FILE
            || entry.sha256.len() != 64
            || !entry
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("可信 Python 文件长度或摘要无效");
        }
        total = total.checked_add(entry.bytes).context("Python 长度溢出")?;
        let mut parent = Path::new(&entry.path).parent();
        while let Some(path) = parent {
            directories.insert(path.to_string_lossy().replace('\\', "/"));
            parent = path.parent();
        }
        if files.insert(entry.path.clone(), entry).is_some() {
            bail!("可信 Python 文件路径重复");
        }
    }
    if files.is_empty() || total > MAX_TREE || files.len() + directories.len() > MAX_NODES {
        bail!("可信 Python 清单为空或超过固定限额");
    }
    let mut aliases = BTreeSet::new();
    for path in files.keys().chain(directories.iter()) {
        if !aliases.insert(path.to_ascii_lowercase()) {
            bail!("可信 Python 清单含大小写别名或文件目录冲突");
        }
    }
    Ok(Spec { files, directories })
}

fn manifest() -> Result<Manifest> {
    let manifest: Manifest =
        serde_json::from_str(include_str!("../../catalog/gui-cp310-python-v1.json"))?;
    if manifest.schema_version != 1
        || manifest.python_version != VERSION
        || manifest.python_build != BUILD
        || manifest.python_abi != "cp310"
        || manifest.platform != "windows-x86_64-none"
        || manifest.archive_name != ARCHIVE
        || manifest.archive_sha256 != ARCHIVE_SHA
        || manifest.archive_bytes != 22_569_949
        || manifest.archive_root != "python"
        || manifest.installation_directory != TARGET
        || manifest.minor_alias != ALIAS
        || manifest.original_file_count != 4_182
        || manifest.files.len() != manifest.original_file_count
        || manifest.original_file_bytes != 61_989_516
        || manifest.original_pyc_count != 920
        || manifest.expected_directory_count != 371
        || manifest.uv_generated_files
            != [
                entry("BUILD", BUILD.as_bytes()),
                entry("Lib/EXTERNALLY-MANAGED", EXTERNALLY_MANAGED),
            ]
        || manifest.optional_root_files != [entry(".gitignore", b"*"), entry(".lock", b"")]
        || manifest.optional_empty_root_directories != [".temp"]
    {
        bail!("可信 Python 清单 schema 或固定制品身份无效");
    }
    let total = manifest.files.iter().try_fold(0u64, |total, file| {
        total.checked_add(file.bytes).context("Python 清单长度溢出")
    })?;
    let original = spec(manifest.files.iter().cloned())?;
    if total != manifest.original_file_bytes
        || manifest
            .files
            .iter()
            .filter(|file| file.path.ends_with(".pyc"))
            .count()
            != manifest.original_pyc_count
        || original.directories.len() - 1 != manifest.expected_directory_count
        || original
            .files
            .get("python.exe")
            .map(|file| file.sha256.as_str())
            != Some("fdfbf8f7d056a13e80460979a13aaf4528577f52b6141bb3dc3732cff7bd7cd6")
    {
        bail!("可信 Python 原文件清单计量或解释器身份不符");
    }
    Ok(manifest)
}

fn verify_file(layout: &Layout, path: &Path, expected: &Entry) -> Result<()> {
    layout.guard_path(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() != expected.bytes || expected.bytes > MAX_FILE {
        bail!("基础 Python 文件缺失、类型或长度不符：{}", expected.path);
    }
    let mut input = File::open(path)?.take(expected.bytes + 1);
    let mut digest = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0; 65_536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        digest.update(&buffer[..count]);
    }
    layout.guard_path(path)?;
    if bytes != expected.bytes || format!("{:x}", digest.finalize()) != expected.sha256 {
        bail!("基础 Python 文件内容改变：{}", expected.path);
    }
    Ok(())
}

fn verify_tree(layout: &Layout, base: &Path, expected: &Spec) -> Result<()> {
    fn walk(
        layout: &Layout,
        base: &Path,
        directory: &Path,
        expected: &Spec,
        seen: &mut BTreeSet<String>,
    ) -> Result<()> {
        layout.guard_path(directory)?;
        for item in fs::read_dir(directory)? {
            let item = item?;
            let path = item.path();
            layout.guard_path(&path)?;
            let relative = path
                .strip_prefix(base)?
                .to_str()
                .context("基础 Python 实际路径不是 UTF-8")?
                .replace('\\', "/");
            let kind = item.file_type()?;
            if kind.is_dir() {
                if !expected.directories.contains(&relative) {
                    bail!("基础 Python 含额外目录：{relative}");
                }
                walk(layout, base, &path, expected, seen)?;
            } else if kind.is_file() {
                let file = expected
                    .files
                    .get(&relative)
                    .with_context(|| format!("基础 Python 含额外文件：{relative}"))?;
                if !seen.insert(relative.to_ascii_lowercase()) {
                    bail!("基础 Python 含大小写路径别名");
                }
                verify_file(layout, &path, file)?;
            } else {
                bail!("基础 Python 含非普通文件：{relative}");
            }
        }
        Ok(())
    }
    layout.guard_path(base)?;
    let mut seen = BTreeSet::new();
    walk(layout, base, base, expected, &mut seen)?;
    if seen.len() != expected.files.len() {
        let missing = expected
            .files
            .keys()
            .find(|path| !seen.contains(&path.to_ascii_lowercase()))
            .context("基础 Python 文件计量不一致")?;
        bail!("基础 Python 原文件缺失：{missing}");
    }
    Ok(())
}

fn verify_alias(layout: &Layout, alias: &Path, target: &Path) -> Result<()> {
    layout.guard_path(alias.parent().context("Python 别名缺少父目录")?)?;
    layout.guard_path(target)?;
    #[cfg(windows)]
    {
        if !junction::exists(alias)?
            || junction::get_target(alias)?.canonicalize()? != target.canonicalize()?
            || !target.is_dir()
        {
            bail!("Python minor 别名未指向同根固定 patch 目录");
        }
        Ok(())
    }
    #[cfg(not(windows))]
    bail!("Python minor junction 只允许在 Windows 使用")
}

fn verify_root(layout: &Layout, root: &Path, manifest: &Manifest) -> Result<()> {
    layout.guard_path(root)?;
    let target = root.join(TARGET);
    layout.guard_path(&target)?;
    if !target.is_dir() {
        bail!("固定基础 Python patch 目录缺失");
    }
    for item in fs::read_dir(root)? {
        let item = item?;
        let path = item.path();
        let name = item.file_name();
        let name = name.to_str().context("Python 版本根路径不是 UTF-8")?;
        if name == ALIAS {
            verify_alias(layout, &path, &target)?;
            continue;
        }
        layout.guard_path(&path)?;
        if name == TARGET && item.file_type()?.is_dir() {
            continue;
        }
        if let Some(file) = manifest
            .optional_root_files
            .iter()
            .find(|file| file.path == name)
        {
            verify_file(layout, &path, file)?;
        } else if manifest
            .optional_empty_root_directories
            .iter()
            .any(|dir| dir == name)
            && item.file_type()?.is_dir()
            && fs::read_dir(&path)?.next().transpose()?.is_none()
        {
            // uv 的可选 .temp 只能为空，不能成为额外运行时文件的藏身处。
        } else {
            bail!("Python 版本根含未知或非空控制项目：{name}");
        }
    }
    Ok(())
}

/// 校验完整基础解释器闭包；调用方必须在运行 Python/uv 环境探测前调用。
/// 原归档自带的 920 个 pyc 必须逐字节一致，任何后生字节码均作为额外文件拒绝。
pub(crate) fn verify(layout: &Layout) -> Result<PathBuf> {
    let root = layout.root.join("python").join(VERSION);
    verify_at(layout, &root)
}

/// The candidate remains under the same guarded workspace; no interpreter runs.
pub(crate) fn verify_at(layout: &Layout, root: &Path) -> Result<PathBuf> {
    let manifest = manifest()?;
    verify_root(layout, root, &manifest)?;
    let target = root.join(TARGET);
    let expected = spec(
        manifest
            .files
            .into_iter()
            .chain(manifest.uv_generated_files),
    )?;
    verify_tree(layout, &target, &expected)?;
    Ok(target.join("python.exe"))
}

pub(crate) fn trusted_paths() -> Result<Vec<String>> {
    let manifest = manifest()?;
    Ok(manifest
        .files
        .into_iter()
        .chain(manifest.uv_generated_files)
        .map(|entry| format!("{TARGET}/{}", entry.path))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        root: PathBuf,
        layout: Layout,
        python: PathBuf,
        target: PathBuf,
        expected: Spec,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-python-integrity-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&root).unwrap();
            let layout = Layout::new(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let python = root.join("python").join(VERSION);
            let target = python.join(TARGET);
            let files = [
                ("python.exe", b"fixture interpreter".as_slice()),
                ("python310.dll", b"fixture library".as_slice()),
                ("Lib/os.py", b"original stdlib".as_slice()),
                (
                    "Lib/__pycache__/os.cpython-310.pyc",
                    b"packaged bytecode".as_slice(),
                ),
                ("BUILD", BUILD.as_bytes()),
                ("Lib/EXTERNALLY-MANAGED", EXTERNALLY_MANAGED),
            ];
            for (path, bytes) in &files {
                layout
                    .ensure_dir(target.join(path).parent().unwrap())
                    .unwrap();
                fs::write(target.join(path), bytes).unwrap();
            }
            let expected = spec(files.iter().map(|(path, bytes)| entry(path, bytes))).unwrap();
            Self {
                root,
                layout,
                python,
                target,
                expected,
            }
        }
        fn verify(&self) -> Result<()> {
            verify_root(&self.layout, &self.python, &manifest()?)?;
            verify_tree(&self.layout, &self.target, &self.expected)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            if self.root.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .root
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-python-integrity-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }

    #[test]
    fn trusted_catalog_includes_original_bytecode_and_fixed_uv_markers() {
        let manifest = manifest().unwrap();
        let expected = spec(
            manifest
                .files
                .into_iter()
                .chain(manifest.uv_generated_files),
        )
        .unwrap();
        assert_eq!(expected.files.len(), 4_184);
        assert!(expected
            .files
            .contains_key("Lib/__pycache__/os.cpython-310.pyc"));
        assert!(expected.files.contains_key("BUILD"));
        assert!(expected.files.contains_key("Lib/EXTERNALLY-MANAGED"));
    }

    #[test]
    fn runtime_dll_stdlib_and_packaged_bytecode_changes_or_omissions_are_rejected() {
        let fixture = Fixture::new();
        fixture.verify().unwrap();
        for path in [
            "python310.dll",
            "Lib/os.py",
            "Lib/__pycache__/os.cpython-310.pyc",
        ] {
            let original = fs::read(fixture.target.join(path)).unwrap();
            fs::write(fixture.target.join(path), b"changed runtime").unwrap();
            assert!(fixture.verify().is_err());
            fs::write(fixture.target.join(path), original).unwrap();
        }
        fs::remove_file(fixture.target.join("BUILD")).unwrap();
        assert!(fixture.verify().is_err());
    }

    #[test]
    fn new_bytecode_unknown_directories_and_untrusted_uv_controls_are_rejected() {
        let fixture = Fixture::new();
        fixture.verify().unwrap();
        let bytecode = fixture.target.join("Lib/__pycache__/new.cpython-310.pyc");
        fs::write(&bytecode, b"new bytecode").unwrap();
        assert!(fixture.verify().is_err());
        fs::remove_file(bytecode).unwrap();
        fs::create_dir(fixture.target.join("extra")).unwrap();
        assert!(fixture.verify().is_err());
        fs::remove_dir(fixture.target.join("extra")).unwrap();
        fs::write(fixture.python.join(".gitignore"), b"*").unwrap();
        fs::write(fixture.python.join(".lock"), b"").unwrap();
        fs::create_dir(fixture.python.join(".temp")).unwrap();
        fixture.verify().unwrap();
        fs::write(fixture.python.join(".temp/untrusted.py"), b"extra").unwrap();
        assert!(fixture.verify().is_err());
        fs::remove_file(fixture.python.join(".temp/untrusted.py")).unwrap();
        fs::write(fixture.python.join(".gitignore"), b"changed").unwrap();
        assert!(fixture.verify().is_err());
    }

    #[cfg(windows)]
    #[test]
    fn only_exact_minor_junction_is_allowed_and_nested_reparse_is_rejected() {
        let fixture = Fixture::new();
        let alias = fixture.python.join(ALIAS);
        junction::create(&fixture.target, &alias).unwrap();
        fixture.verify().unwrap();
        junction::delete(&alias).unwrap();
        fs::remove_dir(&alias).unwrap();
        let foreign = fixture.root.join("foreign");
        fs::create_dir(&foreign).unwrap();
        junction::create(&foreign, &alias).unwrap();
        assert!(fixture.verify().is_err());
        junction::delete(&alias).unwrap();
        fs::remove_dir(&alias).unwrap();
        let nested = fixture.target.join("Lib/redirect");
        junction::create(&foreign, &nested).unwrap();
        assert!(fixture.verify().is_err());
        junction::delete(&nested).unwrap();
        fs::remove_dir(nested).unwrap();
    }
}
