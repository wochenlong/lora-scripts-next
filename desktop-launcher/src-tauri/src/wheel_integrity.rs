//! 从固定 wheel 本身推导文件身份；可编辑的 installed RECORD 永不扩写修复权限。
//! 本模块只读。调用方另外验证解释器、已安装包集合/版本，并持有工作区租约。
use crate::{
    model::{self, Layout},
    recipe::{GuiRecipe, WheelAsset},
};
use anyhow::{bail, Context, Result};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};

const MAX_ASSET: u64 = 512 * 1024 * 1024;
const MAX_TOTAL: u64 = 1024 * 1024 * 1024;
const MAX_METADATA: u64 = 2 * 1024 * 1024;
const MAX_ENTRIES: usize = 100_000;

#[derive(Debug, Serialize)]
pub(crate) struct IntegrityReport {
    pub environment: PathBuf,
    pub packages: Vec<PackageIntegrity>,
}

#[derive(Debug, Serialize)]
pub(crate) struct PackageIntegrity {
    pub name: String,
    pub version: String,
    /// verified_original_files 只表示 wheel 原文件与 RECORD 集合通过；生成项见 generated。
    pub status: String,
    pub missing: Vec<PathBuf>,
    pub damaged: Vec<PathBuf>,
    pub unsupported: Vec<String>,
    pub issues: Vec<String>,
    pub generated: Vec<GeneratedFile>,
    /// 全部为环境相对文件；从可信 wheel 推导，绝不从本地 RECORD 扩展。
    pub paths: Vec<PathBuf>,
}

#[derive(Debug, Serialize)]
pub(crate) struct GeneratedFile {
    pub path: PathBuf,
    pub kind: String,
    pub required: bool,
    pub present: bool,
    pub content_verified: bool,
}

impl IntegrityReport {
    pub(crate) fn original_files_verified(&self) -> bool {
        self.packages.iter().all(|package| {
            package.missing.is_empty()
                && package.damaged.is_empty()
                && package.unsupported.is_empty()
        })
    }
}

/// uv --reinstall 单包的允许文件闭包；不能把这个闭包当成内容验证结果。
pub(crate) fn package_paths(report: &IntegrityReport, name: &str) -> Vec<PathBuf> {
    let normalized = name.to_ascii_lowercase().replace(['_', '.'], "-");
    report
        .packages
        .iter()
        .find(|package| package.name == normalized)
        .map(|package| package.paths.clone())
        .unwrap_or_default()
}

pub(crate) fn inspect(
    layout: &Layout,
    environment: &Path,
    recipe: &GuiRecipe,
    wheelhouse: &Path,
) -> Result<IntegrityReport> {
    recipe.validate()?;
    inspect_assets(layout, environment, &recipe.wheels, wheelhouse)
}

#[derive(Clone)]
struct Expected {
    bytes: u64,
    sha256: String,
}

struct WheelFiles {
    originals: BTreeMap<PathBuf, Expected>,
    record: PathBuf,
    generated: BTreeMap<PathBuf, (String, bool)>,
    unsupported: Vec<String>,
}

fn key(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/").to_lowercase()
}

fn relative(value: &str) -> Result<PathBuf> {
    if value.len() > 4096 || value.contains('\\') {
        bail!("wheel 路径过长或使用反斜线");
    }
    let mut result = PathBuf::new();
    for part in value.split('/') {
        model::validate_component(part)?;
        result.push(part);
    }
    Ok(result)
}

fn parts(value: &str) -> Result<Vec<&str>> {
    relative(value)?;
    Ok(value.split('/').collect())
}

fn mapped(value: &str, data: &str) -> Result<PathBuf> {
    let components = parts(value)?;
    if components[0].ends_with(".data") {
        if components[0] != data || components.len() < 3 {
            bail!("wheel .data 目录与包身份不匹配");
        }
        let base = match components[1] {
            "purelib" | "platlib" => PathBuf::from("Lib/site-packages"),
            "scripts" => PathBuf::from("Scripts"),
            "data" => PathBuf::new(),
            _ => bail!("不支持 wheel 安装 scheme：{}", components[1]),
        };
        Ok(base.join(components[2..].iter().collect::<PathBuf>()))
    } else {
        Ok(Path::new("Lib/site-packages").join(relative(value)?))
    }
}

/// installed RECORD 的基准是 site-packages，允许正规 ../../Scripts；最终仍必须命中闭包。
fn record_path(value: &str) -> Result<PathBuf> {
    if value.is_empty() || value.len() > 4096 || value.contains('\\') {
        bail!("RECORD 路径无效");
    }
    let mut components = vec!["Lib", "site-packages"];
    for part in value.split('/') {
        if part == ".." {
            components.pop().context("RECORD 路径越出环境")?;
        } else {
            model::validate_component(part)?;
            components.push(part);
        }
    }
    if components.is_empty() {
        bail!("RECORD 不得指向环境根");
    }
    Ok(components.iter().collect())
}

/// 小型严格 CSV 阅读器，支持引号与 CRLF，拒绝重复/多字段/未终止引号。
fn csv_records(input: &str) -> Result<Vec<Vec<String>>> {
    let mut rows = Vec::new();
    let mut row = Vec::new();
    let mut field = String::new();
    let mut chars = input.chars().peekable();
    let mut quoted = false;
    let mut closed = false;
    let mut started = false;
    while let Some(ch) = chars.next() {
        if quoted {
            if ch == '"' {
                if chars.peek() == Some(&'"') {
                    chars.next();
                    field.push('"');
                } else {
                    quoted = false;
                    closed = true;
                }
            } else {
                field.push(ch);
            }
            continue;
        }
        match ch {
            '"' if !started => {
                quoted = true;
                started = true;
            }
            ',' => {
                row.push(std::mem::take(&mut field));
                closed = false;
                started = false;
            }
            '\n' | '\r' => {
                if ch == '\r' && chars.next() != Some('\n') {
                    bail!("RECORD 包含裸 CR");
                }
                row.push(std::mem::take(&mut field));
                if row.len() != 3 {
                    bail!("RECORD 必须恰有三列");
                }
                rows.push(std::mem::take(&mut row));
                if rows.len() > MAX_ENTRIES {
                    bail!("RECORD 行数超限");
                }
                closed = false;
                started = false;
            }
            _ if closed || ch == '"' => bail!("RECORD 引号格式无效"),
            _ => {
                field.push(ch);
                started = true;
            }
        }
    }
    if quoted {
        bail!("RECORD 引号未结束");
    }
    if started || !row.is_empty() {
        row.push(field);
        if row.len() != 3 {
            bail!("RECORD 必须恰有三列");
        }
        rows.push(row);
    }
    if rows.is_empty() {
        bail!("RECORD 为空");
    }
    Ok(rows)
}

fn hash_reader(input: &mut impl Read, limit: u64) -> Result<Expected> {
    let mut hash = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0; 65_536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes = bytes.checked_add(count as u64).context("文件体积溢出")?;
        if bytes > limit {
            bail!("文件超出完整性读取预算");
        }
        hash.update(&buffer[..count]);
    }
    Ok(Expected {
        bytes,
        sha256: format!("{:x}", hash.finalize()),
    })
}

fn small_text(input: &mut impl Read, bytes: u64) -> Result<String> {
    if bytes > MAX_METADATA {
        bail!("wheel 元数据超出2MiB上限");
    }
    let mut value = String::new();
    input.take(MAX_METADATA + 1).read_to_string(&mut value)?;
    if value.len() as u64 != bytes {
        bail!("wheel 元数据长度不符");
    }
    Ok(value)
}

#[derive(Default)]
struct PathAliases {
    files: BTreeMap<String, PathBuf>,
    directories: BTreeMap<String, PathBuf>,
}

fn add_path(aliases: &mut PathAliases, path: &Path) -> Result<()> {
    // 既拒绝大小写别名，也拒绝文件与另一文件父路径冲突。
    let mut parent = path.parent();
    while let Some(directory) = parent {
        let normalized = key(directory);
        if aliases.files.contains_key(&normalized)
            || aliases
                .directories
                .get(&normalized)
                .is_some_and(|known| known != directory)
        {
            bail!("wheel 文件父路径冲突或目录大小写别名");
        }
        aliases
            .directories
            .insert(normalized, directory.to_path_buf());
        parent = directory.parent();
    }
    let normalized = key(path);
    if aliases.directories.contains_key(&normalized)
        || aliases
            .files
            .insert(normalized, path.to_path_buf())
            .is_some()
    {
        bail!("wheel 文件重复、大小写别名或父子冲突");
    }
    Ok(())
}

fn entry_points(text: &str) -> Result<Vec<PathBuf>> {
    let mut active = false;
    let mut names = BTreeSet::new();
    let mut paths = Vec::new();
    for line in text.lines().map(str::trim) {
        if line.is_empty() || line.starts_with(['#', ';']) {
            continue;
        }
        if line.starts_with('[') && line.ends_with(']') {
            active = matches!(line, "[console_scripts]" | "[gui_scripts]");
        } else if active {
            let (name, target) = line.split_once('=').context("entry_points 缺少赋值")?;
            let name = name.trim();
            model::validate_component(name)?;
            if target.trim().is_empty() || !names.insert(name.to_ascii_lowercase()) {
                bail!("entry_points 重复或缺少入口");
            }
            paths.push(Path::new("Scripts").join(format!("{name}.exe")));
        }
    }
    Ok(paths)
}

fn wheel_files(
    layout: &Layout,
    asset: &WheelAsset,
    wheelhouse: &Path,
    unpacked: &mut u64,
) -> Result<WheelFiles> {
    model::validate_component(&asset.filename)?;
    if asset.bytes == 0 || asset.bytes > MAX_ASSET {
        bail!("wheel 超出512MiB上限");
    }
    let file = wheelhouse.join(&asset.filename);
    layout.guard_path(&file)?;
    let mut input =
        File::open(&file).with_context(|| format!("缺少可信 wheel：{}", file.display()))?;
    if !input.metadata()?.is_file() || input.metadata()?.len() != asset.bytes {
        bail!("wheel 必须为固定长度普通文件");
    }
    let actual = hash_reader(&mut input, MAX_ASSET)?;
    if actual.bytes != asset.bytes || actual.sha256 != asset.sha256 {
        bail!("wheel 整包身份不符：{}", asset.name);
    }
    input.seek(SeekFrom::Start(0))?;
    let identity: Vec<_> = asset.filename.split('-').collect();
    if identity.len() < 5 {
        bail!("wheel 文件名缺少包身份");
    }
    let dist = format!("{}-{}.dist-info", identity[0], identity[1]);
    let data = format!("{}-{}.data", identity[0], identity[1]);
    let record = Path::new("Lib/site-packages").join(&dist).join("RECORD");
    let source_record = format!("{dist}/RECORD");
    let source_entry_points = format!("{dist}/entry_points.txt");
    let mut archive = zip::ZipArchive::new(input)?;
    if archive.len() > MAX_ENTRIES {
        bail!("wheel 条目超限");
    }
    let mut originals = BTreeMap::new();
    let mut aliases = PathAliases::default();
    let mut source_paths = BTreeSet::new();
    let mut record_text = None;
    let mut console_paths = Vec::new();
    let mut unsupported = Vec::new();
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index)?;
        let name = entry.name().to_owned();
        if entry
            .unix_mode()
            .is_some_and(|mode| !matches!(mode & 0o170000, 0 | 0o040000 | 0o100000))
        {
            bail!("wheel 含符号链接或特殊文件");
        }
        let source = if entry.is_dir() {
            name.trim_end_matches('/')
        } else {
            &name
        };
        parts(source)?;
        if entry.is_dir() {
            continue;
        }
        if !source_paths.insert(name.clone()) {
            bail!("wheel 原路径重复");
        }
        let destination = mapped(&name, &data)?;
        add_path(&mut aliases, &destination)?;
        *unpacked = unpacked
            .checked_add(entry.size())
            .context("wheel 解压预算溢出")?;
        if entry.size() > MAX_ASSET || *unpacked > MAX_TOTAL {
            bail!("wheel 解压超出单文件512MiB或合计1GiB预算");
        }
        if name == source_record {
            let size = entry.size();
            record_text = Some(small_text(&mut entry, size)?);
            continue;
        }
        if name == source_entry_points {
            let size = entry.size();
            let text = small_text(&mut entry, size)?;
            console_paths = entry_points(&text)?;
            originals.insert(
                destination,
                Expected {
                    bytes: text.len() as u64,
                    sha256: format!("{:x}", Sha256::digest(text.as_bytes())),
                },
            );
        } else if name.starts_with(&format!("{data}/scripts/")) {
            let mut prefix = [0; 9];
            let mut count = 0;
            while count < prefix.len() {
                let read = entry.read(&mut prefix[count..])?;
                if read == 0 {
                    break;
                }
                count += read;
            }
            if prefix[..count].starts_with(b"#!python") {
                unsupported.push(format!(
                    "{}: uv 会转写 #!python，尚无可信内容验证器",
                    destination.display()
                ));
                // 仍完整读取以验证 ZIP CRC、长度和预算。
            }
            let mut chained = (&prefix[..count]).chain(&mut entry);
            let expected = hash_reader(&mut chained, MAX_ASSET)?;
            originals.insert(destination, expected);
        } else {
            let expected = hash_reader(&mut entry, MAX_ASSET)?;
            originals.insert(destination, expected);
        }
    }
    let record_text = record_text.context("wheel 缺少自身 RECORD")?;
    let mut recorded = BTreeSet::new();
    for row in csv_records(&record_text)? {
        relative(&row[0])?;
        if !recorded.insert(row[0].clone()) {
            bail!("wheel RECORD 路径重复");
        }
    }
    if recorded != source_paths {
        bail!("wheel RECORD 与真实 ZIP 文件集合不符");
    }
    let mut generated = BTreeMap::from([(record.clone(), ("rewritten_record".into(), true))]);
    for (name, required) in [
        ("INSTALLER", true),
        ("REQUESTED", false),
        ("direct_url.json", false),
        ("uv_cache.json", false),
    ] {
        let path = Path::new("Lib/site-packages").join(&dist).join(name);
        // 仅当前包顶层允许生成例外；vendor 内 dist-info 同名文件仍为原文件。
        if originals.contains_key(&path) {
            bail!("wheel 顶层包含保留安装器生成项");
        }
        generated.insert(path, (format!("installer_{name}"), required));
    }
    for path in console_paths {
        if originals.contains_key(&path) {
            bail!("入口脚本与 wheel 原文件冲突");
        }
        generated.insert(path, ("entry_point_executable_unverified".into(), true));
    }
    // uv 对 pip 的版本入口执行固定规则补全；不是由本地 RECORD 自由声明。
    if asset.name == "pip" && generated.contains_key(Path::new("Scripts/pip.exe")) {
        generated.insert(
            PathBuf::from("Scripts/pip3.10.exe"),
            ("uv_pip_python_minor_entry_unverified".into(), true),
        );
    }
    // 仅由可信 .py 唯一推导可选字节码，不接受 RECORD 自由声明缓存路径。
    for path in originals
        .keys()
        .filter(|path| path.extension().is_some_and(|ext| ext == "py"))
    {
        let stem = path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .context("Python 路径不是UTF-8")?;
        let parent = path
            .parent()
            .context("Python 路径无父目录")?
            .join("__pycache__");
        for suffix in ["", ".opt-1", ".opt-2"] {
            let derived = parent.join(format!("{stem}.cpython-310{suffix}.pyc"));
            // Some wheels ship bytecode as original content (e.g. NumPy).
            // Its trusted ZIP hash remains authoritative; it is not optional generated data.
            if originals.contains_key(&derived) {
                continue;
            }
            generated.insert(
                derived,
                ("optional_derived_bytecode_unverified".into(), false),
            );
        }
    }
    Ok(WheelFiles {
        originals,
        record,
        generated,
        unsupported,
    })
}

fn presence(layout: &Layout, environment: &Path, relative: &Path) -> Result<Option<fs::Metadata>> {
    let path = environment.join(relative);
    layout.guard_path(&path)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) => Ok(Some(metadata)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn check_record(text: &str, files: &WheelFiles) -> Result<()> {
    let mut seen = BTreeSet::new();
    for row in csv_records(text)? {
        let path = record_path(&row[0])?;
        if !files.originals.contains_key(&path) && !files.generated.contains_key(&path) {
            bail!(
                "installed RECORD 声明不在 wheel 闭包中的路径：{}",
                path.display()
            );
        }
        if !seen.insert(path) {
            bail!("installed RECORD 包含重复路径");
        }
        // 本地 hash/size 仅为安装器记账，不作为任何内容完整性依据。
    }
    if files.originals.keys().any(|path| !seen.contains(path))
        || !seen.contains(&files.record)
        || files
            .generated
            .iter()
            .any(|(path, (_, required))| *required && !seen.contains(path))
    {
        bail!("installed RECORD 漏掉 wheel 原文件或必要生成项");
    }
    Ok(())
}

fn inspect_assets(
    layout: &Layout,
    environment: &Path,
    assets: &[WheelAsset],
    wheelhouse: &Path,
) -> Result<IntegrityReport> {
    let environments = layout.root.join("environments");
    let compact = layout.root.join("e");
    let compact_id = environment.strip_prefix(&compact).ok().and_then(|path| {
        if path.components().count() == 1 {
            path.to_str()
        } else {
            None
        }
    });
    let compact_ok = compact_id.is_some_and(|id| {
        id.len() == 17
            && id.starts_with('g')
            && id[1..]
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    });
    if (!environment.starts_with(&environments) || environment == environments) && !compact_ok {
        bail!("完整性目标必须位于受管环境固定命名空间");
    }
    layout.guard_path(environment)?;
    layout.guard_path(wheelhouse)?;
    let mut compressed = 0u64;
    let mut unpacked = 0u64;
    let mut global_aliases = PathAliases::default();
    let mut package_names = BTreeSet::new();
    let mut packages = Vec::new();
    for asset in assets {
        if !package_names.insert(&asset.name) {
            bail!("包身份重复");
        }
        compressed = compressed
            .checked_add(asset.bytes)
            .context("wheel 总长度溢出")?;
        if compressed > MAX_TOTAL {
            bail!("wheel 整包总预算超过1GiB");
        }
        let files = wheel_files(layout, asset, wheelhouse, &mut unpacked)?;
        let mut package = PackageIntegrity {
            name: asset.name.clone(),
            version: asset.version.clone(),
            status: String::new(),
            missing: Vec::new(),
            damaged: Vec::new(),
            issues: Vec::new(),
            unsupported: files.unsupported.clone(),
            generated: Vec::new(),
            paths: Vec::new(),
        };
        for path in files.originals.keys().chain(files.generated.keys()) {
            add_path(&mut global_aliases, path)?;
            package.paths.push(path.clone());
        }
        for (path, expected) in &files.originals {
            match presence(layout, environment, path)? {
                None => package.missing.push(path.clone()),
                Some(metadata) if !metadata.is_file() || metadata.len() != expected.bytes => {
                    package.damaged.push(path.clone());
                }
                Some(_) => {
                    let actual = hash_reader(&mut File::open(environment.join(path))?, MAX_ASSET)?;
                    if actual.sha256 != expected.sha256 || actual.bytes != expected.bytes {
                        package.damaged.push(path.clone());
                    }
                }
            }
        }
        for (path, (kind, required)) in &files.generated {
            let present = match presence(layout, environment, path)? {
                None => {
                    if *required {
                        package.missing.push(path.clone());
                    }
                    false
                }
                Some(metadata) => {
                    if !metadata.is_file() {
                        package.damaged.push(path.clone());
                    }
                    metadata.is_file()
                }
            };
            package.generated.push(GeneratedFile {
                path: path.clone(),
                kind: kind.clone(),
                required: *required,
                present,
                content_verified: false,
            });
            if path == &files.record && present {
                let record_result = (|| {
                    let mut input = File::open(environment.join(path))?;
                    let bytes = input.metadata()?.len();
                    check_record(&small_text(&mut input, bytes)?, &files)
                })();
                if let Err(error) = record_result {
                    package.damaged.push(path.clone());
                    package
                        .issues
                        .push(format!("RECORD 集合校验失败：{error:#}"));
                }
            }
        }
        package.paths.sort();
        package.missing.sort();
        package.damaged.sort();
        package.damaged.dedup();
        package.status = if !package.unsupported.is_empty() {
            "unsupported"
        } else if !package.damaged.is_empty() {
            "damaged"
        } else if !package.missing.is_empty() {
            "missing"
        } else {
            "verified_original_files"
        }
        .into();
        packages.push(package);
    }
    Ok(IntegrityReport {
        environment: environment.to_path_buf(),
        packages,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::Write,
        sync::atomic::{AtomicU64, Ordering},
        time::{SystemTime, UNIX_EPOCH},
    };
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        layout: Layout,
        wheelhouse: PathBuf,
        asset: WheelAsset,
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.layout.root);
        }
    }
    impl Fixture {
        fn new(extra: &[(&str, &[u8])]) -> Self {
            let root = std::env::temp_dir().join(format!(
                "launcher-wheel-integrity-{}-{}-{}",
                std::process::id(),
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_nanos(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let layout = Layout::new(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let wheelhouse = root.join("cache/wheelhouse");
            fs::create_dir_all(&wheelhouse).unwrap();
            let mut entries = vec![
                ("demo/__init__.py", b"answer = 42\n".as_slice()),
                (
                    "demo-1.0.dist-info/METADATA",
                    b"Name: demo\nVersion: 1.0\n".as_slice(),
                ),
                (
                    "demo-1.0.dist-info/WHEEL",
                    b"Wheel-Version: 1.0\n".as_slice(),
                ),
                (
                    "demo-1.0.dist-info/entry_points.txt",
                    b"[console_scripts]\ndemo = demo:main\n".as_slice(),
                ),
            ];
            entries.extend_from_slice(extra);
            let mut record = entries
                .iter()
                .map(|(name, _)| format!("{name},,\n"))
                .collect::<String>();
            record.push_str("demo-1.0.dist-info/RECORD,,\n");
            entries.push(("demo-1.0.dist-info/RECORD", record.as_bytes()));
            let filename = "demo-1.0-py3-none-any.whl";
            let path = wheelhouse.join(filename);
            let mut writer = zip::ZipWriter::new(File::create(&path).unwrap());
            for (name, contents) in entries {
                writer
                    .start_file(name, zip::write::SimpleFileOptions::default())
                    .unwrap();
                writer.write_all(contents).unwrap();
            }
            writer.finish().unwrap();
            let observed = hash_reader(&mut File::open(&path).unwrap(), MAX_ASSET).unwrap();
            let mut asset = GuiRecipe::embedded().unwrap().wheels[0].clone();
            asset.name = "demo".into();
            asset.version = "1.0".into();
            asset.filename = filename.into();
            asset.bytes = observed.bytes;
            asset.sha256 = observed.sha256;
            Self {
                layout,
                wheelhouse,
                asset,
            }
        }
        fn install(&self) {
            let mut archive = zip::ZipArchive::new(
                File::open(self.wheelhouse.join(&self.asset.filename)).unwrap(),
            )
            .unwrap();
            for index in 0..archive.len() {
                let mut entry = archive.by_index(index).unwrap();
                let target = self
                    .layout
                    .environment
                    .join(mapped(entry.name(), "demo-1.0.data").unwrap());
                fs::create_dir_all(target.parent().unwrap()).unwrap();
                std::io::copy(&mut entry, &mut File::create(target).unwrap()).unwrap();
            }
            fs::create_dir_all(self.layout.environment.join("Scripts")).unwrap();
            fs::write(
                self.layout.environment.join("Scripts/demo.exe"),
                b"generated exe",
            )
            .unwrap();
            fs::write(
                self.layout
                    .environment
                    .join("Lib/site-packages/demo-1.0.dist-info/INSTALLER"),
                b"uv",
            )
            .unwrap();
            let record = self.record();
            let contents = fs::read_to_string(&record).unwrap();
            // uv 会重写 .data 路径，wheel 原始 RECORD 不能直接当安装后路径。
            let contents = contents
                .replace("demo-1.0.data/data/", "../../")
                .replace("demo-1.0.data/scripts/", "../../Scripts/");
            fs::write(
                record,
                format!("{contents}demo-1.0.dist-info/INSTALLER,,\n../../Scripts/demo.exe,,\n"),
            )
            .unwrap();
        }
        fn record(&self) -> PathBuf {
            self.layout
                .environment
                .join("Lib/site-packages/demo-1.0.dist-info/RECORD")
        }
        fn inspect(&self) -> Result<IntegrityReport> {
            inspect_assets(
                &self.layout,
                &self.layout.environment,
                std::slice::from_ref(&self.asset),
                &self.wheelhouse,
            )
        }
    }

    #[test]
    fn missing_package_and_generated_console_are_diagnosed() {
        let fixture = Fixture::new(&[]);
        let report = fixture.inspect().unwrap();
        assert_eq!(report.packages[0].status, "missing");
        assert!(report.packages[0]
            .missing
            .contains(&PathBuf::from("Scripts/demo.exe")));
        assert!(!report.original_files_verified());
        fixture.install();
        let report = fixture.inspect().unwrap();
        assert!(report.original_files_verified());
        assert!(report.packages[0]
            .generated
            .iter()
            .all(|item| !item.content_verified));
    }

    #[test]
    fn modified_original_cannot_hide_behind_forged_local_record_hashes() {
        let fixture = Fixture::new(&[]);
        fixture.install();
        fs::write(
            fixture
                .layout
                .environment
                .join("Lib/site-packages/demo/__init__.py"),
            b"answer = 99\n",
        )
        .unwrap();
        let record = fs::read_to_string(fixture.record())
            .unwrap()
            .replace("demo/__init__.py,,", "demo/__init__.py,sha256=forged,12");
        fs::write(fixture.record(), record).unwrap();
        let report = fixture.inspect().unwrap();
        assert_eq!(report.packages[0].status, "damaged");
        assert!(report.packages[0]
            .damaged
            .contains(&PathBuf::from("Lib/site-packages/demo/__init__.py")));
    }

    #[test]
    fn wheel_shipped_bytecode_stays_original_and_tampering_is_detected() {
        let fixture = Fixture::new(&[(
            "demo/__pycache__/__init__.cpython-310.pyc",
            b"trusted wheel bytecode",
        )]);
        fixture.install();
        let bytecode = PathBuf::from("Lib/site-packages/demo/__pycache__/__init__.cpython-310.pyc");
        let report = fixture.inspect().unwrap();
        assert!(report.original_files_verified());
        assert!(!report.packages[0]
            .generated
            .iter()
            .any(|file| file.path == bytecode));
        fs::write(
            fixture.layout.environment.join(&bytecode),
            b"altered wheel bytecode",
        )
        .unwrap();
        let report = fixture.inspect().unwrap();
        assert!(!report.original_files_verified());
        assert!(report.packages[0].damaged.contains(&bytecode));
    }

    #[test]
    fn record_injection_never_expands_repair_paths_and_omission_is_damaged() {
        let fixture = Fixture::new(&[]);
        fixture.install();
        let original = fs::read_to_string(fixture.record()).unwrap();
        fs::write(
            fixture.record(),
            format!("{original}../../../profiles/default/profile.json,,\n"),
        )
        .unwrap();
        let report = fixture.inspect().unwrap();
        assert_eq!(report.packages[0].status, "damaged");
        assert!(!package_paths(&report, "demo")
            .iter()
            .any(|path| key(path).contains("profiles")));
        fs::write(
            fixture.record(),
            original
                .lines()
                .filter(|line| !line.starts_with("demo/__init__.py,"))
                .collect::<Vec<_>>()
                .join("\n"),
        )
        .unwrap();
        assert_eq!(fixture.inspect().unwrap().packages[0].status, "damaged");
    }

    #[test]
    fn wheel_hash_traversal_reserved_name_and_case_alias_are_rejected() {
        let mut fixture = Fixture::new(&[]);
        fixture.asset.sha256 = "0".repeat(64);
        assert!(fixture.inspect().is_err());
        for name in [
            "../escape",
            "demo/CON.py",
            "demo/../escape",
            "demo\\escape",
            "DEMO/__INIT__.py",
            "DEMO/other.py",
        ] {
            let fixture = Fixture::new(&[(name, b"x")]);
            assert!(fixture.inspect().is_err(), "must reject {name}");
        }
    }

    #[test]
    fn data_and_scripts_map_within_environment_and_shebang_rewrite_is_unsupported() {
        let fixture = Fixture::new(&[
            ("demo-1.0.data/data/share/man/demo.1", b"manual"),
            ("demo-1.0.data/scripts/tool.exe", b"exe"),
        ]);
        fixture.install();
        let report = fixture.inspect().unwrap();
        assert!(report.original_files_verified());
        let paths = package_paths(&report, "demo");
        assert!(paths.contains(&PathBuf::from("share/man/demo.1")));
        assert!(paths.contains(&PathBuf::from("Scripts/tool.exe")));
        let fixture = Fixture::new(&[("demo-1.0.data/scripts/tool", b"#!python\npass\n")]);
        fixture.install();
        assert_eq!(fixture.inspect().unwrap().packages[0].status, "unsupported");
    }

    #[test]
    fn csv_quoted_paths_and_record_escape_are_strict() {
        assert_eq!(
            csv_records("\"demo/a,b.py\",hash,12\r\n").unwrap()[0][0],
            "demo/a,b.py"
        );
        assert!(csv_records("demo.py,hash,1,extra\n").is_err());
        assert!(csv_records("\"unfinished,,\n").is_err());
        assert!(record_path("../../../outside").is_err());
        assert!(record_path("../../Scripts/CON.exe").is_err());
        assert_eq!(
            record_path("../../Scripts/demo.exe").unwrap(),
            PathBuf::from("Scripts/demo.exe")
        );
    }

    #[cfg(windows)]
    #[test]
    fn installed_external_junction_is_rejected_without_reading_outside() {
        let fixture = Fixture::new(&[]);
        fixture.install();
        let outside = Fixture::new(&[]);
        let target = outside.layout.root.join("external-package");
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("__init__.py"), b"answer = 42\n").unwrap();
        let link = fixture.layout.environment.join("Lib/site-packages/demo");
        fs::remove_dir_all(&link).unwrap();
        junction::create(&target, &link).unwrap();
        let rejected = fixture.inspect().is_err();
        junction::delete(&link).unwrap();
        assert!(rejected);
        assert_eq!(
            fs::read(target.join("__init__.py")).unwrap(),
            b"answer = 42\n"
        );
    }

    #[cfg(unix)]
    #[test]
    fn installed_external_symlink_is_rejected_without_reading_outside() {
        let fixture = Fixture::new(&[]);
        fixture.install();
        let outside = Fixture::new(&[]);
        let link = fixture.layout.environment.join("Lib/site-packages/demo");
        fs::remove_dir_all(&link).unwrap();
        std::os::unix::fs::symlink(&outside.layout.root, &link).unwrap();
        assert!(fixture.inspect().is_err());
        fs::remove_file(link).unwrap();
    }
}
