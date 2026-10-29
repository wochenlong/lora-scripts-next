//! 显式资料复制和完整运行组合切换。源只读；导入副本不自动激活、不接管旧环境。
use crate::model::{self, Catalog, Registry, WorkspaceMutation};
use crate::operations::CancelToken;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

const VERSION: u32 = 1;
const MAX_FILES: usize = 20_000;
const MAX_BYTES: u64 = 512 * 1024 * 1024;
static NEXT_WRITE: AtomicU64 = AtomicU64::new(0);

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(value: &impl Serialize) -> Result<String> {
    Ok(hash(&serde_json::to_vec(value)?))
}
fn schema(version: u32) -> Result<()> {
    if version != VERSION {
        bail!("资料协议版本不受支持，保留原件并拒绝写入");
    }
    Ok(())
}
fn regular_chain(path: &Path) -> Result<()> {
    if !path.is_absolute() {
        bail!("资料路径必须为绝对路径");
    }
    for component in path.components() {
        if matches!(component, Component::ParentDir | Component::CurDir) {
            bail!("资料路径不得含点或上级目录");
        }
        if let Component::Normal(name) = component {
            model::validate_component(name.to_str().context("资料路径必须为Unicode")?)?;
        }
    }
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(info) => {
                #[cfg(windows)]
                let linked = {
                    use std::os::windows::fs::MetadataExt;
                    info.file_attributes() & 0x400 != 0
                };
                #[cfg(not(windows))]
                let linked = info.file_type().is_symlink();
                if linked || info.file_type().is_symlink() {
                    bail!("复制资料不接受目录联接或符号链接");
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
fn profile_id(id: &str) -> Result<()> {
    model::validate_component(id)?;
    if id.len() > 64 {
        bail!("profile ID过长");
    }
    Ok(())
}
fn owned(root: &Path, path: &Path) -> Result<()> {
    if !path.starts_with(root) {
        bail!("资料目标超出工作区");
    }
    regular_chain(path)
}
fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() {
        bail!("资料相对路径为空");
    }
    for component in path.components() {
        let Component::Normal(name) = component else {
            bail!("资料清单路径必须是普通相对路径");
        };
        model::validate_component(name.to_str().context("资料路径必须为Unicode")?)?;
    }
    Ok(())
}
fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn optional_bytes(path: &Path) -> Result<Option<Vec<u8>>> {
    regular_chain(path)?;
    if path.exists() {
        let metadata = fs::symlink_metadata(path)?;
        if !metadata.is_file() || metadata.len() > 32 * 1024 * 1024 {
            bail!("资料控制文件不是受限普通文件");
        }
    }
    match read_bounded(path, 32 * 1024 * 1024) {
        Ok(v) => Ok(Some(v)),
        Err(e)
            if e.downcast_ref::<std::io::Error>()
                .is_some_and(|v| v.kind() == std::io::ErrorKind::NotFound) =>
        {
            Ok(None)
        }
        Err(e) => Err(e),
    }
}
fn read_bounded(path: &Path, limit: u64) -> Result<Vec<u8>> {
    regular_chain(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() > limit {
        bail!("资料文件不是受限普通文件");
    }
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(limit.saturating_add(1))
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        bail!("读取期间资料超出上限");
    }
    Ok(bytes)
}
fn raw_hash(path: &Path) -> Result<Option<String>> {
    Ok(optional_bytes(path)?.map(|v| hash(&v)))
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExternalPath {
    pub kind: String,
    pub path: PathBuf,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ImportRequest {
    pub release_id: String,
    pub source_root: PathBuf,
    pub profile_id: String,
    #[serde(default)]
    pub include_credentials: bool,
    #[serde(default)]
    pub external_paths: Vec<ExternalPath>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CopyItem {
    pub source_relative: PathBuf,
    pub target_relative: PathBuf,
    pub bytes: u64,
    pub sha256: String,
    pub target_bytes: u64,
    pub target_sha256: String,
    pub transformation: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Reference {
    pub kind: String,
    pub absolute_path: PathBuf,
    pub exists: bool,
    pub is_directory: bool,
    pub metadata_bytes: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Scan {
    pub schema_version: u32,
    pub source_root: PathBuf,
    pub files: Vec<CopyItem>,
    pub directories: Vec<PathBuf>,
    pub references: Vec<Reference>,
    pub excluded: Vec<String>,
    pub unsupported: Vec<String>,
    pub copy_bytes: u64,
    pub source_fingerprint: String,
}

fn secret_name(name: &str) -> bool {
    let n = name.to_ascii_lowercase();
    n == ".env"
        || n.starts_with(".env.")
        || [
            "credential",
            "secret",
            "token",
            "password",
            "api_key",
            "apikey",
        ]
        .iter()
        .any(|v| n.contains(v))
}
fn contains_credentials(bytes: &[u8]) -> bool {
    // 不输出内容；含凭据字段的整份设置文件默认不复制，避免误把嵌入秘密当普通设置。
    let text = String::from_utf8_lossy(bytes).to_ascii_lowercase();
    [
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "password",
        "secret_key",
        "authorization",
        "\"token\"",
        "\"secret\"",
        "\"credentials\"",
        "\"auth\"",
    ]
    .iter()
    .any(|key| text.contains(key))
}
fn json_paths(value: &mut serde_json::Value, source: &Path, path_map: bool) -> Result<()> {
    match value {
        serde_json::Value::Object(fields) => {
            if path_map {
                fields.remove("python");
            } // 旧Python/venv绝不接管，按新配方单独重建。
            for (key, item) in fields {
                if key == "schema_version" && item.as_u64() != Some(1) {
                    bail!("源资料含未知schema，保留原件并拒绝导入");
                }
                let path_key = path_map
                    || matches!(
                        key.as_str(),
                        "last_path"
                            | "path"
                            | "config_path"
                            | "pretrained_model_name_or_path"
                            | "vae"
                            | "dataset_config"
                            | "resume"
                            | "model_name_or_path"
                    )
                    || key.ends_with("_path")
                    || key.ends_with("_dir")
                    || key.ends_with("_file");
                if path_key {
                    if let Some(text) = item.as_str() {
                        if !text.is_empty() && !text.contains("://") {
                            let path = Path::new(text);
                            let model_id = matches!(
                                key.as_str(),
                                "pretrained_model_name_or_path" | "model_name_or_path" | "vae"
                            );
                            if model_id
                                && !path.is_absolute()
                                && !source.join(path).exists()
                                && !text.starts_with('.')
                                && !text.contains('\\')
                                && path.extension().is_none()
                                && path.components().count() <= 2
                            {
                                // 保留可识别的Hub标识；缺失但明确本地的路径仍绝对化并由入口验证拒绝。
                                continue;
                            }
                            let resolved = if path.is_absolute() {
                                path.to_path_buf()
                            } else {
                                source.join(path)
                            };
                            regular_chain(&resolved)?;
                            *item =
                                serde_json::Value::String(resolved.to_string_lossy().into_owned());
                        }
                        continue;
                    }
                }
                json_paths(
                    item,
                    source,
                    key == "paths" || (path_map && item.is_object()),
                )?;
            }
        }
        serde_json::Value::Array(values) => {
            for item in values {
                json_paths(item, source, path_map)?;
            }
        }
        _ => (),
    }
    Ok(())
}
fn copied_bytes(source: &Path, item: &CopyItem) -> Result<Vec<u8>> {
    let bytes = read_bounded(source, MAX_BYTES)?;
    if bytes.len() as u64 != item.bytes || hash(&bytes) != item.sha256 {
        bail!("源资料实体已变化，需要重新扫描");
    }
    match item.transformation.as_str() {
        "copy" => Ok(bytes),
        "json-absolute-paths-v1" => {
            let mut value: serde_json::Value =
                serde_json::from_slice(&bytes).context("不支持的JSON资料")?;
            let root = source
                .ancestors()
                .nth(item.source_relative.components().count())
                .context("源资料根缺失")?;
            json_paths(&mut value, root, false)?;
            Ok(serde_json::to_vec_pretty(&value)?)
        }
        _ => bail!("未知资料转换器"),
    }
}
fn reference(kind: &str, path: &Path, source: &Path) -> Result<Reference> {
    if !matches!(kind, "model" | "dataset") {
        bail!("外部引用只支持模型或数据集");
    }
    let absolute_path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        source.join(path)
    };
    regular_chain(&absolute_path)?;
    let metadata = match fs::metadata(&absolute_path) {
        Ok(v) => Some(v),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    Ok(Reference {
        kind: kind.into(),
        absolute_path,
        exists: metadata.is_some(),
        is_directory: metadata.as_ref().is_some_and(|v| v.is_dir()),
        metadata_bytes: metadata.as_ref().map_or(0, |v| v.len()),
    })
}
fn scan_request(request: &ImportRequest) -> Result<Scan> {
    regular_chain(&request.source_root)?;
    if !request.source_root.is_dir() {
        bail!("源安装目录不存在");
    }
    model::validate_release_id(&request.release_id)?;
    profile_id(&request.profile_id)?;
    if let Some(raw) = optional_bytes(&request.source_root.join("profile.json"))? {
        let descriptor: serde_json::Value = serde_json::from_slice(&raw)?;
        if descriptor["schema_version"] != VERSION || !descriptor["id"].is_string() {
            bail!("源profile格式未知，拒绝导入");
        }
    }
    if request.source_root.join("state/registry.json").exists() {
        Registry::load(&request.source_root)?;
    }
    let mut result = Scan {
        schema_version: VERSION,
        source_root: request.source_root.clone(),
        files: vec![],
        directories: vec![],
        references: vec![],
        excluded: vec![],
        unsupported: vec![],
        copy_bytes: 0,
        source_fingerprint: String::new(),
    };
    fn walk(
        source: &Path,
        destination: &Path,
        request: &ImportRequest,
        scan: &mut Scan,
    ) -> Result<()> {
        regular_chain(source)?;
        if source
            .strip_prefix(&request.source_root)?
            .components()
            .count()
            > 128
        {
            bail!("资料目录层数超过128上限");
        }
        if scan.files.len() + scan.directories.len() >= MAX_FILES {
            bail!("资料条目超出20000上限");
        }
        let metadata = fs::metadata(source)?;
        if metadata.is_dir() {
            scan.directories.push(destination.into());
            let mut entries = fs::read_dir(source)?
                .take(MAX_FILES + 1)
                .collect::<std::io::Result<Vec<_>>>()?;
            if entries.len() > MAX_FILES {
                bail!("资料目录条目超过上限");
            }
            entries.sort_by_key(|e| e.file_name());
            for entry in entries {
                let name = entry.file_name().to_string_lossy().into_owned();
                model::validate_component(&name)?;
                if !request.include_credentials && secret_name(&name) {
                    scan.excluded.push(
                        entry
                            .path()
                            .strip_prefix(&request.source_root)?
                            .to_string_lossy()
                            .into_owned(),
                    );
                    continue;
                }
                walk(&entry.path(), &destination.join(name), request, scan)?;
            }
        } else if metadata.is_file() {
            let extension = source
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if ["safetensors", "ckpt", "pt", "pth", "bin", "onnx"].contains(&extension.as_str()) {
                scan.references
                    .push(reference("model", source, &request.source_root)?);
                return Ok(());
            }
            let target_text = destination.to_string_lossy().replace('\\', "/");
            let configuration =
                target_text.starts_with("user_data/") || target_text.starts_with("compat/");
            if configuration && extension != "json" {
                scan.unsupported.push(
                    source
                        .strip_prefix(&request.source_root)?
                        .to_string_lossy()
                        .into_owned(),
                );
                return Ok(());
            }
            if scan.files.len() >= MAX_FILES
                || metadata.len() > MAX_BYTES
                || scan
                    .copy_bytes
                    .checked_add(metadata.len())
                    .is_none_or(|n| n > MAX_BYTES)
            {
                bail!("资料复制超出单次512MiB或20000文件上限；模型/数据集请使用引用");
            }
            let bytes = read_bounded(source, MAX_BYTES)?;
            if !request.include_credentials && contains_credentials(&bytes) {
                scan.excluded.push(
                    source
                        .strip_prefix(&request.source_root)?
                        .to_string_lossy()
                        .into_owned(),
                );
                return Ok(());
            }
            let mut item = CopyItem {
                source_relative: source.strip_prefix(&request.source_root)?.into(),
                target_relative: destination.into(),
                bytes: bytes.len() as u64,
                sha256: hash(&bytes),
                target_bytes: 0,
                target_sha256: String::new(),
                transformation: if configuration {
                    "json-absolute-paths-v1"
                } else {
                    "copy"
                }
                .into(),
            };
            let output = copied_bytes(source, &item)?;
            item.target_bytes = output.len() as u64;
            item.target_sha256 = hash(&output);
            scan.copy_bytes = scan
                .copy_bytes
                .checked_add(item.target_bytes)
                .context("资料容量溢出")?;
            if scan.copy_bytes > MAX_BYTES {
                bail!("转换后的资料超过512MiB上限");
            }
            scan.files.push(item);
        } else {
            bail!("源资料含非普通文件，拒绝复制");
        }
        Ok(())
    }
    let mappings = [
        ("user_data", PathBuf::from("user_data")),
        ("presets", PathBuf::from("user_data/presets")),
        (
            "config",
            PathBuf::from("compat")
                .join(&request.release_id)
                .join("config"),
        ),
        (
            "toml",
            PathBuf::from("compat")
                .join(&request.release_id)
                .join("toml"),
        ),
        ("output", PathBuf::from("library/output")),
        ("outputs", PathBuf::from("library/output")),
        (
            "assets/config.json",
            PathBuf::from("compat")
                .join(&request.release_id)
                .join("assets/config.json"),
        ),
    ];
    for (source, target) in &mappings {
        let path = request.source_root.join(source);
        if path.exists() {
            walk(&path, target, request, &mut result)?;
        }
    }
    for (name, kind) in [
        ("sd-models", "model"),
        ("models", "model"),
        ("datasets", "dataset"),
    ] {
        let path = request.source_root.join(name);
        if path.exists() {
            result
                .references
                .push(reference(kind, &path, &request.source_root)?);
        }
    }
    for value in &request.external_paths {
        result
            .references
            .push(reference(&value.kind, &value.path, &request.source_root)?);
    }
    for entry in fs::read_dir(&request.source_root)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if !mappings.iter().any(|(n, _)| *n == name)
            && !["sd-models", "models", "datasets"].contains(&name.as_str())
        {
            result.unsupported.push(name);
        }
    }
    result
        .files
        .sort_by(|a, b| a.target_relative.cmp(&b.target_relative));
    result.directories.sort();
    result.directories.dedup();
    result.excluded.sort();
    result.unsupported.sort();
    result
        .references
        .sort_by(|a, b| (&a.kind, &a.absolute_path).cmp(&(&b.kind, &b.absolute_path)));
    result.references.dedup();
    result.source_fingerprint = digest(&result)?;
    Ok(result)
}

/// 只读扫描不调用旧环境/训练器、不创建工作区；凭据内容不返回给普通诊断。
#[cfg(test)]
pub fn scan(request: &ImportRequest) -> Result<Scan> {
    scan_request(request)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MigrationPlan {
    pub schema_version: u32,
    pub request: ImportRequest,
    pub scan: Scan,
    pub target_profile: PathBuf,
    pub conflicts: Vec<String>,
    pub registry_sha256: Option<String>,
    pub bindings_sha256: Option<String>,
    pub peak_copy_bytes: u64,
    pub plan_sha256: String,
}
pub fn preview(root: &Path, request: &ImportRequest) -> Result<MigrationPlan> {
    regular_chain(root)?;
    let _ = Registry::load(root)?;
    let _ = load_bindings(root)?;
    let scan = scan_request(request)?;
    let source = fs::canonicalize(&request.source_root)?;
    let existing_root = if root.exists() {
        fs::canonicalize(root)?
    } else {
        root.to_path_buf()
    };
    if source.starts_with(&existing_root) || existing_root.starts_with(&source) {
        bail!("源安装与目标工作区不得重叠");
    }
    let target_profile = root.join("profiles").join(&request.profile_id);
    owned(root, &target_profile)?;
    let mut conflicts = vec![];
    if target_profile.exists() || request.profile_id == "default" {
        conflicts.push("目标profile已存在或是default；请选择全新profile ID，不合并或覆盖".into());
    }
    let mut paths = BTreeMap::new();
    for file in &scan.files {
        let key = file.target_relative.to_string_lossy().to_lowercase();
        if paths.insert(key, &file.source_relative).is_some() {
            conflicts.push(format!(
                "源文件映射冲突：{}；请先在源副本明确解决",
                file.target_relative.display()
            ));
        }
    }
    for directory in &scan.directories {
        if paths.contains_key(&directory.to_string_lossy().to_lowercase()) {
            conflicts.push(format!("资料文件与目录映射冲突：{}", directory.display()));
        }
    }
    for file in &scan.files {
        for parent in file.target_relative.ancestors().skip(1) {
            if paths.contains_key(&parent.to_string_lossy().to_lowercase()) {
                conflicts.push(format!(
                    "资料文件占用了其它资料的父目录：{}",
                    parent.display()
                ));
            }
        }
    }
    for reference in &scan.references {
        if !reference.exists {
            conflicts.push(format!(
                "外部引用不存在：{}",
                reference.absolute_path.display()
            ));
        }
    }
    let peak_copy_bytes = scan.copy_bytes.checked_mul(2).context("空间估计溢出")?;
    let existing = root
        .ancestors()
        .find(|p| p.is_dir())
        .context("目标磁盘不存在")?;
    let available = fs2::available_space(existing)?;
    if available < peak_copy_bytes.saturating_add(1024 * 1024) {
        conflicts.push(format!(
            "目标磁盘空间不足：需至少{}字节，可用{}字节",
            peak_copy_bytes.saturating_add(1024 * 1024),
            available
        ));
    }
    let mut plan = MigrationPlan {
        schema_version: VERSION,
        request: request.clone(),
        scan,
        target_profile,
        conflicts,
        registry_sha256: raw_hash(&root.join("state/registry.json"))?,
        bindings_sha256: raw_hash(&root.join("state/profile-bindings.json"))?,
        peak_copy_bytes,
        plan_sha256: String::new(),
    };
    plan.plan_sha256 = digest(&plan)?;
    Ok(plan)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ImportReceipt {
    pub schema_version: u32,
    pub transaction: String,
    pub profile_id: String,
    pub plan_sha256: String,
    pub source_fingerprint: String,
    pub status: String,
    pub copied_bytes: u64,
    pub activated: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ImportIntent {
    schema_version: u32,
    plan: MigrationPlan,
    receipt: ImportReceipt,
}
fn import_paths(root: &Path, id: &str) -> Result<(PathBuf, PathBuf)> {
    model::validate_component(id)?;
    if !id.starts_with("data-import-") {
        bail!("资料事务ID无效");
    }
    Ok((
        root.join("state/data-imports").join(format!("{id}.json")),
        root.join("staging").join(id),
    ))
}
fn verify_file(path: &Path, item: &CopyItem) -> Result<()> {
    regular_chain(path)?;
    let bytes = read_bounded(path, item.target_bytes.min(MAX_BYTES))?;
    if bytes.len() as u64 != item.target_bytes || hash(&bytes) != item.target_sha256 {
        bail!("资料实体已变化，需要重新扫描");
    }
    Ok(())
}
fn validate_intent(root: &Path, intent: &ImportIntent) -> Result<()> {
    schema(intent.schema_version)?;
    schema(intent.plan.schema_version)?;
    schema(intent.plan.scan.schema_version)?;
    schema(intent.receipt.schema_version)?;
    let plan = &intent.plan;
    let receipt = &intent.receipt;
    model::validate_release_id(&plan.request.release_id)?;
    profile_id(&plan.request.profile_id)?;
    regular_chain(&plan.request.source_root)?;
    let mut expected = plan.clone();
    expected.plan_sha256.clear();
    let mut observed = plan.scan.clone();
    observed.source_fingerprint.clear();
    if digest(&expected)? != plan.plan_sha256
        || !valid_sha(&plan.plan_sha256)
        || digest(&observed)? != plan.scan.source_fingerprint
        || plan.scan.source_root != plan.request.source_root
        || !plan.conflicts.is_empty()
        || plan.target_profile != root.join("profiles").join(&plan.request.profile_id)
        || plan.request.profile_id == "default"
    {
        bail!("导入计划身份/摘要无效");
    }
    let transaction = format!(
        "data-import-{}-{}",
        plan.request.profile_id,
        &plan.plan_sha256[..16]
    );
    if receipt.transaction != transaction
        || receipt.profile_id != plan.request.profile_id
        || receipt.plan_sha256 != plan.plan_sha256
        || receipt.source_fingerprint != plan.scan.source_fingerprint
        || receipt.copied_bytes != plan.scan.copy_bytes
        || receipt.activated
        || !matches!(receipt.status.as_str(), "copying" | "committed")
    {
        bail!("导入回执与计划不符");
    }
    let mut names = BTreeSet::new();
    let mut total = 0u64;
    for file in &plan.scan.files {
        relative(&file.source_relative)?;
        relative(&file.target_relative)?;
        if !valid_sha(&file.sha256)
            || !valid_sha(&file.target_sha256)
            || !matches!(
                file.transformation.as_str(),
                "copy" | "json-absolute-paths-v1"
            )
            || !names.insert(file.target_relative.to_string_lossy().to_lowercase())
        {
            bail!("资料文件清单无效或重复");
        }
        if !model::PROFILE_DIRECTORIES
            .iter()
            .any(|d| file.target_relative.starts_with(d))
        {
            bail!("资料文件不在固定profile目录中");
        }
        total = total
            .checked_add(file.target_bytes)
            .context("资料容量溢出")?;
    }
    if total != plan.scan.copy_bytes
        || total > MAX_BYTES
        || plan.scan.files.len() + plan.scan.directories.len() > MAX_FILES
    {
        bail!("资料容量不符合意图");
    }
    for directory in &plan.scan.directories {
        relative(directory)?;
    }
    for value in &plan.scan.references {
        regular_chain(&value.absolute_path)?;
        if !matches!(value.kind.as_str(), "model" | "dataset") {
            bail!("引用类型无效");
        }
    }
    Ok(())
}
fn expected_receipt(intent: &ImportIntent) -> ImportReceipt {
    let mut r = intent.receipt.clone();
    r.status = "committed".into();
    r
}
fn metadata_values(intent: &ImportIntent) -> Vec<(&'static str, serde_json::Value)> {
    vec![
        (
            "profile.json",
            serde_json::json!({"schema_version":VERSION,"id":intent.plan.request.profile_id}),
        ),
        (
            "external-paths.json",
            serde_json::json!(intent.plan.scan.references),
        ),
        (
            "import-receipt.json",
            serde_json::json!(expected_receipt(intent)),
        ),
    ]
}
fn inspect_payload(root: &Path, intent: &ImportIntent, complete: bool) -> Result<()> {
    regular_chain(root)?;
    if !root.exists() {
        if complete {
            bail!("已提交profile缺失");
        }
        return Ok(());
    }
    let mut files: BTreeSet<PathBuf> = intent
        .plan
        .scan
        .files
        .iter()
        .map(|f| f.target_relative.clone())
        .collect();
    files.extend(
        metadata_values(intent)
            .iter()
            .map(|(name, _)| PathBuf::from(name)),
    );
    let mut directories: BTreeSet<PathBuf> = intent.plan.scan.directories.iter().cloned().collect();
    directories.extend(model::PROFILE_DIRECTORIES.iter().map(PathBuf::from));
    // 声明的空目录也由 create_dir_all 建立；它们的必需祖先须与文件祖先同样核对。
    for path in files.iter().chain(intent.plan.scan.directories.iter()) {
        for parent in path
            .ancestors()
            .skip(1)
            .filter(|p| !p.as_os_str().is_empty())
        {
            directories.insert(parent.into());
        }
    }
    fn walk(
        base: &Path,
        current: &Path,
        files: &BTreeSet<PathBuf>,
        directories: &BTreeSet<PathBuf>,
    ) -> Result<()> {
        regular_chain(current)?;
        for entry in fs::read_dir(current)? {
            let entry = entry?;
            regular_chain(&entry.path())?;
            let path = entry.path();
            let rel = path.strip_prefix(base)?;
            if entry.file_type()?.is_dir() {
                if !directories.contains(rel) {
                    bail!("资料副本含清单外目录，拒绝发布");
                }
                walk(base, &path, files, directories)?;
            } else if !entry.file_type()?.is_file() || !files.contains(rel) {
                bail!("资料副本含清单外实体，拒绝发布");
            }
        }
        Ok(())
    }
    walk(root, root, &files, &directories)?;
    for file in &intent.plan.scan.files {
        let path = root.join(&file.target_relative);
        if complete || path.exists() {
            verify_file(&path, file)?;
        }
    }
    for (name, value) in metadata_values(intent) {
        let path = root.join(name);
        if complete || path.exists() {
            let observed: serde_json::Value = serde_json::from_slice(&fs::read(path)?)?;
            if observed != value {
                bail!("资料副本元数据不符");
            }
        }
    }
    Ok(())
}
fn continue_import(
    ctx: &WorkspaceMutation,
    intent: &mut ImportIntent,
    cancel: &CancelToken,
) -> Result<ImportReceipt> {
    let root = &ctx.layout().root;
    validate_intent(root, intent)?;
    let (intent_path, staged) = import_paths(root, &intent.receipt.transaction)?;
    if intent.plan.request.release_id
        != ctx
            .layout()
            .release_dir
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
        || intent.receipt.plan_sha256 != intent.plan.plan_sha256
        || intent.plan.target_profile != root.join("profiles").join(&intent.plan.request.profile_id)
    {
        bail!("导入意图与工作区身份不符");
    }
    owned(root, &staged)?;
    owned(root, &intent.plan.target_profile)?;
    owned(root, &intent_path)?;
    if intent.plan.target_profile.exists() {
        inspect_payload(&intent.plan.target_profile, intent, true)?;
        intent.receipt = expected_receipt(intent);
        model::write_json_atomic(&intent_path, intent)?;
        return Ok(intent.receipt.clone());
    }
    if intent.receipt.status == "committed" {
        bail!("已提交profile缺失，保留意图等待人工诊断");
    }
    cancel.check()?;
    let observed = scan_request(&intent.plan.request)?;
    if observed != intent.plan.scan {
        bail!("源资料或引用变化，保留未完成副本并要求重新扫描");
    }
    if raw_hash(&root.join("state/registry.json"))? != intent.plan.registry_sha256
        || raw_hash(&root.join("state/profile-bindings.json"))? != intent.plan.bindings_sha256
    {
        bail!("活动绑定在导入期间改变，拒绝发布副本");
    }
    {
        let payload = staged.join("payload");
        let partial = staged.join("partial");
        let owner = staged.join("owner.json");
        let identity = serde_json::json!({"schema_version":VERSION,"transaction":intent.receipt.transaction,"plan_sha256":intent.plan.plan_sha256});
        if staged.exists() {
            let observed: serde_json::Value = serde_json::from_slice(&fs::read(&owner)?)?;
            if observed != identity {
                bail!("资料暂存目录不属于该意图");
            }
            for entry in fs::read_dir(&staged)? {
                let name = entry?.file_name();
                if name != "payload" && name != "partial" && name != "owner.json" {
                    bail!("资料暂存出现未知实体");
                }
            }
        } else {
            ctx.layout().ensure_dir(&staged)?;
            model::write_json_atomic(&owner, &identity)?;
        }
        ctx.layout().ensure_dir(&payload)?;
        ctx.layout().ensure_dir(&partial)?;
        for entry in fs::read_dir(&partial)? {
            let entry = entry?;
            regular_chain(&entry.path())?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if !(0..intent.plan.scan.files.len()).any(|i| name == format!("{i}.part"))
                || !entry.file_type()?.is_file()
            {
                bail!("资料分片目录有未知实体");
            }
        }
        inspect_payload(&payload, intent, false)?;
        ctx.layout().ensure_dir(&staged)?;
        for directory in &intent.plan.scan.directories {
            ctx.layout().ensure_dir(&payload.join(directory))?;
        }
        for (index, file) in intent.plan.scan.files.iter().enumerate() {
            cancel.check()?;
            let source = intent.plan.request.source_root.join(&file.source_relative);
            let output_bytes = copied_bytes(&source, file)?;
            if output_bytes.len() as u64 != file.target_bytes
                || hash(&output_bytes) != file.target_sha256
            {
                bail!("资料转换输出改变");
            }
            let target = payload.join(&file.target_relative);
            owned(root, &target)?;
            if target.exists() {
                verify_file(&target, file)?;
                continue;
            }
            ctx.layout()
                .ensure_dir(target.parent().context("资料目标缺少父目录")?)?;
            let temp = partial.join(format!("{index}.part"));
            owned(root, &temp)?;
            let offset = if temp.exists() {
                let prefix = fs::read(&temp)?;
                if !output_bytes.starts_with(&prefix) {
                    bail!("资料中断分片非本意图输出前缀，保留现场");
                }
                prefix.len()
            } else {
                0
            };
            let mut output = fs::OpenOptions::new()
                .append(true)
                .create(true)
                .open(&temp)?;
            for chunk in output_bytes[offset..].chunks(65536) {
                cancel.check()?;
                output.write_all(chunk)?;
            }
            output.sync_all()?;
            drop(output);
            verify_file(&temp, file)?;
            fs::rename(&temp, &target)?;
        }
        if scan_request(&intent.plan.request)? != intent.plan.scan {
            bail!("源资料复制后变化，不发布混合快照");
        }
        for (name, value) in metadata_values(intent) {
            model::write_json_atomic(&payload.join(name), &value)?;
        }
        for name in model::PROFILE_DIRECTORIES {
            ctx.layout().ensure_dir(&payload.join(name))?;
        }
        inspect_payload(&payload, intent, true)?;
        cancel.check()?;
        if intent.plan.target_profile.exists() {
            bail!("目标profile在提交前出现，拒绝覆盖");
        }
        fs::rename(&payload, &intent.plan.target_profile)?;
    }
    intent.receipt.status = "committed".into();
    model::write_json_atomic(&intent_path, intent)?;
    Ok(intent.receipt.clone())
}
pub fn execute(
    ctx: &WorkspaceMutation,
    request: &ImportRequest,
    expected_sha: &str,
    cancel: &CancelToken,
) -> Result<ImportReceipt> {
    let plan = preview(&ctx.layout().root, request)?;
    if plan.plan_sha256 != expected_sha || !plan.conflicts.is_empty() {
        bail!("导入计划已改变或仍有未解决冲突，请重新预览");
    }
    let transaction = format!(
        "data-import-{}-{}",
        request.profile_id,
        &plan.plan_sha256[..16]
    );
    let (path, _) = import_paths(&ctx.layout().root, &transaction)?;
    if path.exists() {
        bail!("已有此导入事务，请使用恢复入口");
    }
    let mut intent = ImportIntent {
        schema_version: VERSION,
        receipt: ImportReceipt {
            schema_version: VERSION,
            transaction,
            profile_id: request.profile_id.clone(),
            plan_sha256: plan.plan_sha256.clone(),
            source_fingerprint: plan.scan.source_fingerprint.clone(),
            status: "copying".into(),
            copied_bytes: plan.scan.copy_bytes,
            activated: false,
        },
        plan,
    };
    owned(&ctx.layout().root, &path)?;
    model::write_json_atomic(&path, &intent)?;
    continue_import(ctx, &mut intent, cancel)
}
pub fn recover(
    ctx: &WorkspaceMutation,
    transaction: &str,
    cancel: &CancelToken,
) -> Result<ImportReceipt> {
    let (path, _) = import_paths(&ctx.layout().root, transaction)?;
    owned(&ctx.layout().root, &path)?;
    let mut intent: ImportIntent = serde_json::from_slice(&fs::read(path)?)?;
    if intent.receipt.transaction != transaction {
        bail!("导入事务身份不符");
    }
    continue_import(ctx, &mut intent, cancel)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub release_id: String,
    pub profile_id: String,
    pub profile_schema_version: u32,
    pub environment_instance_ids: BTreeMap<String, String>,
    pub environment_generations: BTreeMap<String, u64>,
    pub healthy_at: Option<u64>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Bindings {
    pub schema_version: u32,
    pub generation: u64,
    pub current: Option<Binding>,
    pub previous_known_good: Option<Binding>,
}
fn load_bindings(root: &Path) -> Result<Option<Bindings>> {
    let Some(raw) = optional_bytes(&root.join("state/profile-bindings.json"))? else {
        return Ok(None);
    };
    let value: Bindings = serde_json::from_slice(&raw)?;
    schema(value.schema_version)?;
    if value.generation == 0 {
        bail!("资料绑定代次无效");
    }
    for binding in [&value.current, &value.previous_known_good]
        .into_iter()
        .flatten()
    {
        model::validate_release_id(&binding.release_id)?;
        profile_id(&binding.profile_id)?;
        schema(binding.profile_schema_version)?;
        validate_binding_shape(binding)?;
    }
    if value
        .previous_known_good
        .as_ref()
        .is_some_and(|b| b.healthy_at.is_none())
    {
        bail!("上一资料组合没有真实健康记录");
    }
    Ok(Some(value))
}
pub fn has_bindings(root: &Path) -> Result<bool> {
    Ok(load_bindings(root)?.is_some())
}
/// Layout只在Registry权威release与已提交侧档相符时使用新profile；未知schema拒读。
pub fn load_active_profile(root: &Path, release_id: &str) -> Result<Option<String>> {
    // 恢复入口仍须能构造Layout并持锁；启动/普通变更由调用层显式检查gate。
    if binding_pending(root)? {
        return Ok(None);
    }
    let Some(bindings) = load_bindings(root)? else {
        return Ok(None);
    };
    let registry = Registry::load(root)?;
    if let Some(current) = bindings.current {
        if registry.current.as_deref() == Some(release_id) {
            if current.release_id != release_id {
                return Ok(None); // 普通入口拒绝不完整组合；恢复入口仍可先构造布局持锁。
            }
            let descriptor_path = root
                .join("profiles")
                .join(&current.profile_id)
                .join("profile.json");
            let descriptor: serde_json::Value = serde_json::from_slice(
                &optional_bytes(&descriptor_path)?.context("活动profile描述缺失")?,
            )?;
            if descriptor != serde_json::json!({"schema_version":VERSION,"id":current.profile_id}) {
                bail!("profile描述与绑定不符");
            }
            return Ok(Some(current.profile_id));
        }
    }
    Ok(None)
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BindingRequest {
    pub binding: Binding,
    pub expected_generation: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BindingPlan {
    pub request: BindingRequest,
    pub old_bindings: Option<Bindings>,
    pub default_upgrade: Option<Bindings>,
    pub registry_sha256: Option<String>,
    pub profile_sha256: String,
    pub environment_state_sha256: BTreeMap<String, String>,
    pub plan_sha256: String,
}
fn validate_binding_shape(binding: &Binding) -> Result<()> {
    model::validate_release_id(&binding.release_id)?;
    profile_id(&binding.profile_id)?;
    schema(binding.profile_schema_version)?;
    if !binding.environment_instance_ids.contains_key("gui")
        || binding
            .environment_instance_ids
            .keys()
            .ne(binding.environment_generations.keys())
        || binding.environment_generations.values().any(|v| *v == 0)
    {
        bail!("三元环境绑定不完整");
    }
    for (component, id) in &binding.environment_instance_ids {
        if !matches!(
            component.as_str(),
            "gui" | "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth"
        ) {
            bail!("未知环境组件");
        }
        model::validate_component(id)?;
    }
    Ok(())
}
fn state_path(root: &Path, binding: &Binding, component: &str) -> PathBuf {
    if component == "gui" {
        root.join("state/instances").join(format!(
            "{}.json",
            binding.environment_instance_ids[component]
        ))
    } else {
        root.join("state/engines")
            .join(&binding.release_id)
            .join(component)
            .join("state.json")
    }
}
fn validate_binding(root: &Path, binding: &Binding) -> Result<()> {
    validate_binding_selected(root, binding, None)
}
fn validate_binding_selected(root: &Path, binding: &Binding, selected: Option<&str>) -> Result<()> {
    validate_binding_shape(binding)?;
    let release = Catalog::embedded()?.release(&binding.release_id)?.clone();
    if release.profile_schema_version != binding.profile_schema_version {
        bail!("发布不能读取该profile schema");
    }
    let descriptor = root
        .join("profiles")
        .join(&binding.profile_id)
        .join("profile.json");
    regular_chain(&descriptor)?;
    let value: serde_json::Value = serde_json::from_slice(&fs::read(descriptor)?)?;
    if value != serde_json::json!({"schema_version":VERSION,"id":binding.profile_id}) {
        bail!("profile未知或描述不兼容");
    }
    let registry = Registry::load(root)?;
    if !registry
        .installed
        .iter()
        .any(|i| i.release_id == binding.release_id)
    {
        bail!("绑定版本尚未安装");
    }
    if binding
        .environment_instance_ids
        .keys()
        .ne(binding.environment_generations.keys())
        || !binding.environment_instance_ids.contains_key("gui")
    {
        bail!("完整三元绑定必须包含GUI及匹配代次");
    }
    for (component, id) in &binding.environment_instance_ids {
        if selected.is_some_and(|v| v != component) {
            continue;
        }
        model::validate_component(component)?;
        model::validate_component(id)?;
        let generation = binding.environment_generations[component];
        if component == "gui" {
            let gui = registry
                .gui_binding(&binding.release_id)
                .context("GUI环境绑定缺失")?;
            if gui.instance_id != *id || gui.generation != generation {
                bail!("GUI环境代次/身份已变化；回退旧组合前请先使用GUI实例回退恢复匹配实例及代次");
            }
            let path = state_path(root, binding, component);
            let state: serde_json::Value =
                serde_json::from_slice(&optional_bytes(&path)?.context("GUI实例状态缺失")?)?;
            if !matches!(state["schema_version"].as_u64(), Some(1..=3))
                || state["component"] != "gui"
                || state["instance_id"] != *id
                || state["release_id"] != binding.release_id
                || state["generation"] != generation
                || state["validated_generation"] != generation
                || state["dirty"] != false
                || !state["pending"].is_null()
                || !state["base_python_pending"].is_null()
            {
                bail!("GUI状态未通过当前代次验证或仍待恢复");
            }
        } else {
            if !matches!(
                component.as_str(),
                "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth"
            ) {
                bail!("未知引擎绑定");
            }
            let path = root
                .join("state/engines")
                .join(&binding.release_id)
                .join(component)
                .join("state.json");
            regular_chain(&path)?;
            let state: serde_json::Value = serde_json::from_slice(&fs::read(&path)?)?;
            if state["schema_version"] != 1
                || state["release_id"] != binding.release_id
                || state["engine_id"] != *component
                || state["instance_id"] != *id
                || state["generation"] != generation
                || state["validated_generation"] != generation
                || state["dirty"] != false
                || state["status"] != "ready"
                || !state["pending"].is_null()
            {
                bail!("引擎环境身份、状态或验证代次不匹配");
            }
            profile_id(
                state["profile_id"]
                    .as_str()
                    .context("引擎建立profile标识缺失")?,
            )?;
            let expected = format!("instances/{id}/{generation}.json");
            if state["receipt_relative"] != expected {
                bail!("引擎收据路径不符合固定实例/代次");
            }
            let receipt_path = path.parent().context("引擎状态目录缺失")?.join(expected);
            regular_chain(&receipt_path)?;
            let receipt_bytes = fs::read(receipt_path)?;
            if state["receipt_sha256"] != hash(&receipt_bytes) {
                bail!("引擎收据摘要不符");
            }
            let receipt: serde_json::Value = serde_json::from_slice(&receipt_bytes)?;
            for key in [
                "schema_version",
                "release_id",
                "engine_id",
                "instance_id",
                "generation",
                "lock_sha256",
                "recipe_sha256",
            ] {
                if receipt[key] != state[key] || state[key].is_null() {
                    bail!("引擎状态与收据身份不符");
                }
            }
        }
    }
    Ok(())
}
fn default_binding(registry: &Registry, id: &str) -> Result<Binding> {
    let gui = registry
        .gui_binding(id)
        .context("旧default缺少正式GUI实例，需先完成环境登记")?;
    Ok(Binding {
        release_id: id.into(),
        profile_id: "default".into(),
        profile_schema_version: VERSION,
        environment_instance_ids: BTreeMap::from([("gui".into(), gui.instance_id.clone())]),
        environment_generations: BTreeMap::from([("gui".into(), gui.generation)]),
        healthy_at: registry
            .installed
            .iter()
            .find(|i| i.release_id == id)
            .and_then(|i| i.healthy_at),
    })
}
fn default_upgrade(registry: &Registry) -> Result<Bindings> {
    Ok(Bindings {
        schema_version: VERSION,
        generation: 0,
        current: registry
            .current
            .as_deref()
            .map(|id| default_binding(registry, id))
            .transpose()?,
        previous_known_good: registry
            .previous_known_good
            .as_deref()
            .map(|id| default_binding(registry, id))
            .transpose()?,
    })
}
pub fn preview_binding(root: &Path, request: &BindingRequest) -> Result<BindingPlan> {
    assert_binding_ready(root)?;
    validate_binding(root, &request.binding)?;
    let old_bindings = load_bindings(root)?;
    if request.expected_generation != old_bindings.as_ref().map_or(0, |v| v.generation) {
        bail!("资料绑定代次已变化");
    }
    let registry = Registry::load(root)?;
    registry.assert_base_python_ready()?;
    if let Some(bindings) = &old_bindings {
        if bindings.current.as_ref().map(|b| &b.release_id) != registry.current.as_ref() {
            bail!("当前资料侧档与Registry不符，请先恢复完整组合");
        }
    }
    let upgrade = if old_bindings.is_none() {
        Some(default_upgrade(&registry)?)
    } else {
        None
    };
    let environment_state_sha256 = request
        .binding
        .environment_instance_ids
        .keys()
        .map(|component| {
            Ok((
                component.clone(),
                raw_hash(&state_path(root, &request.binding, component))?
                    .context("环境状态缺失")?,
            ))
        })
        .collect::<Result<_>>()?;
    let mut plan = BindingPlan {
        request: request.clone(),
        old_bindings,
        default_upgrade: upgrade,
        registry_sha256: raw_hash(&root.join("state/registry.json"))?,
        profile_sha256: raw_hash(
            &root
                .join("profiles")
                .join(&request.binding.profile_id)
                .join("profile.json"),
        )?
        .context("profile缺失")?,
        environment_state_sha256,
        plan_sha256: String::new(),
    };
    plan.plan_sha256 = digest(&plan)?;
    Ok(plan)
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BindingIntent {
    schema_version: u32,
    transaction: String,
    root_absolute: PathBuf,
    status: String,
    old_registry: Vec<u8>,
    old_bindings: Option<Vec<u8>>,
    new_registry: Registry,
    new_bindings: Bindings,
    intent_sha256: String,
}
fn binding_intent(root: &Path) -> PathBuf {
    root.join("state/profile-binding-intent.json")
}
fn encoded(value: &impl Serialize) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn seal_intent(intent: &mut BindingIntent) -> Result<()> {
    intent.intent_sha256.clear();
    intent.intent_sha256 = digest(intent)?;
    Ok(())
}
fn validate_binding_intent(root: &Path, intent: &BindingIntent) -> Result<()> {
    schema(intent.schema_version)?;
    model::validate_component(&intent.transaction)?;
    if intent.root_absolute != root
        || !intent.transaction.starts_with("profile-binding-")
        || !matches!(
            intent.status.as_str(),
            "committing" | "committed" | "rolled_back"
        )
    {
        bail!("资料绑定意图身份/状态无效");
    }
    let mut expected = intent.clone();
    seal_intent(&mut expected)?;
    if expected.intent_sha256 != intent.intent_sha256 {
        bail!("资料绑定意图摘要不符");
    }
    let old: Registry = serde_json::from_slice(&intent.old_registry)?;
    old.validate()?;
    intent.new_registry.validate()?;
    schema(intent.new_bindings.schema_version)?;
    if intent.new_bindings.generation == 0
        || intent.new_bindings.current.as_ref().map(|b| &b.release_id)
            != intent.new_registry.current.as_ref()
    {
        bail!("新资料绑定与Registry authority不符");
    }
    for b in [
        &intent.new_bindings.current,
        &intent.new_bindings.previous_known_good,
    ]
    .into_iter()
    .flatten()
    {
        validate_binding_shape(b)?;
    }
    let old_generation = match &intent.old_bindings {
        Some(bytes) => {
            let value: Bindings = serde_json::from_slice(bytes)?;
            schema(value.schema_version)?;
            for b in [&value.current, &value.previous_known_good]
                .into_iter()
                .flatten()
            {
                validate_binding_shape(b)?;
            }
            if value.generation == 0
                || value.current.as_ref().map(|b| &b.release_id) != old.current.as_ref()
            {
                bail!("原资料绑定与原Registry不符");
            }
            value.generation
        }
        None => 0,
    };
    if old_generation.checked_add(1) != Some(intent.new_bindings.generation) {
        bail!("资料绑定意图代次不连续");
    }
    let mut reduced_old = old;
    let mut reduced_new = intent.new_registry.clone();
    reduced_old.current = None;
    reduced_new.current = None;
    reduced_old.previous_known_good = None;
    reduced_new.previous_known_good = None;
    for record in &mut reduced_old.installed {
        record.healthy_at = None;
    }
    for record in &mut reduced_new.installed {
        record.healthy_at = None;
    }
    if reduced_old != reduced_new {
        bail!("资料绑定事务试图改变非绑定Registry字段");
    }
    let backup = root.join("backups").join(&intent.transaction);
    regular_chain(&backup)?;
    if optional_bytes(&backup.join("registry.original.json"))?.as_ref()
        != Some(&intent.old_registry)
        || optional_bytes(&backup.join("profile-bindings.original.json"))? != intent.old_bindings
    {
        bail!("资料绑定原字节备份与意图不符");
    }
    Ok(())
}
pub fn assert_binding_ready(root: &Path) -> Result<()> {
    if binding_pending(root)? {
        bail!("完整资料绑定事务待恢复，禁止启动或变更版本");
    }
    Ok(())
}
fn binding_pending(root: &Path) -> Result<bool> {
    if let Some(bytes) = optional_bytes(&binding_intent(root))? {
        let intent: BindingIntent = serde_json::from_slice(&bytes)?;
        schema(intent.schema_version)?;
        validate_binding_intent(root, &intent)?;
        return Ok(intent.status == "committing");
    }
    Ok(false)
}
/// validator必须由调用层用私有资料入口实测；成功才原子提交Registry+侧档，绝不把导入成功当运行健康。
pub fn execute_binding(
    ctx: &WorkspaceMutation,
    request: &BindingRequest,
    expected_sha: &str,
    validator: impl FnOnce(&Binding, &Path) -> Result<()>,
) -> Result<Bindings> {
    let root = &ctx.layout().root;
    let plan = preview_binding(root, request)?;
    if plan.plan_sha256 != expected_sha {
        bail!("资料组合计划变化，需重新确认");
    }
    if ctx.layout().release_dir.file_name().unwrap_or_default()
        != request.binding.release_id.as_str()
    {
        bail!("租约发布与资料组合不符");
    }
    validator(
        &request.binding,
        &root.join("profiles").join(&request.binding.profile_id),
    )?;
    if preview_binding(root, request)?.plan_sha256 != expected_sha {
        bail!("入口验证后资料组合变化");
    }
    let mut registry = Registry::load(root)?;
    let effective = plan
        .old_bindings
        .as_ref()
        .or(plan.default_upgrade.as_ref())
        .context("缺少原资料组合")?;
    let current_old = effective.current.clone();
    let mut target = request.binding.clone();
    target.healthy_at = None;
    let previous = current_old
        .filter(|v| v.healthy_at.is_some())
        .or_else(|| effective.previous_known_good.clone());
    registry.current = Some(target.release_id.clone());
    registry.previous_known_good = previous
        .as_ref()
        .map(|v| v.release_id.clone())
        .filter(|v| v != &target.release_id);
    registry
        .installed
        .iter_mut()
        .find(|i| i.release_id == target.release_id)
        .context("目标版本缺失")?
        .healthy_at = None;
    registry.validate()?;
    let bindings = Bindings {
        schema_version: VERSION,
        generation: request
            .expected_generation
            .checked_add(1)
            .context("绑定代次耗尽")?,
        current: Some(target),
        previous_known_good: previous,
    };
    commit_bindings(ctx, registry, bindings.clone())?;
    Ok(bindings)
}
fn save_new(path: &Path, bytes: &[u8]) -> Result<()> {
    regular_chain(path)?;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}
fn commit_bindings(ctx: &WorkspaceMutation, registry: Registry, bindings: Bindings) -> Result<()> {
    let root = &ctx.layout().root;
    let old_registry = fs::read(root.join("state/registry.json"))?;
    let old_bindings = optional_bytes(&root.join("state/profile-bindings.json"))?;
    let transaction = format!(
        "profile-binding-{}-{}-{}",
        model::now(),
        std::process::id(),
        NEXT_WRITE.fetch_add(1, Ordering::Relaxed)
    );
    let backup = root.join("backups").join(&transaction);
    ctx.layout().ensure_dir(&backup)?;
    save_new(&backup.join("registry.original.json"), &old_registry)?;
    if let Some(bytes) = &old_bindings {
        save_new(&backup.join("profile-bindings.original.json"), bytes)?;
    }
    let mut intent = BindingIntent {
        schema_version: VERSION,
        transaction,
        root_absolute: root.clone(),
        status: "committing".into(),
        old_registry,
        old_bindings,
        new_registry: registry,
        new_bindings: bindings.clone(),
        intent_sha256: String::new(),
    };
    seal_intent(&mut intent)?;
    validate_binding_intent(root, &intent)?;
    model::write_json_atomic(&binding_intent(root), &intent)?;
    model::write_json_atomic(&root.join("state/profile-bindings.json"), &bindings)?;
    model::write_json_atomic(&root.join("state/registry.json"), &intent.new_registry)?;
    intent.status = "committed".into();
    seal_intent(&mut intent)?;
    model::write_json_atomic(&binding_intent(root), &intent)
}
/// 仅由真实受管入口成功后调用；健康事实与三元侧档在同一可恢复事务内写入。
pub fn mark_healthy(ctx: &WorkspaceMutation, release_id: &str) -> Result<()> {
    let root = &ctx.layout().root;
    assert_binding_ready(root)?;
    let mut registry = Registry::load(root)?;
    if ctx
        .layout()
        .release_dir
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        != release_id
    {
        bail!("健康租约版本不符");
    }
    let Some(mut bindings) = load_bindings(root)? else {
        registry.mark_healthy(release_id)?;
        return registry.store(root);
    };
    let current = bindings.current.as_mut().context("当前资料绑定缺失")?;
    if current.release_id != release_id
        || root.join("profiles").join(&current.profile_id) != ctx.layout().profile
    {
        bail!("实际服务资料档案与活动组合不符");
    }
    validate_binding(root, current)?;
    registry.mark_healthy(release_id)?;
    current.healthy_at = registry
        .installed
        .iter()
        .find(|i| i.release_id == release_id)
        .and_then(|i| i.healthy_at);
    bindings.generation = bindings.generation.checked_add(1).context("绑定代次耗尽")?;
    commit_bindings(ctx, registry, bindings)
}
/// 仅正式运行入口调用，检查完整组合；不放在Layout构造路径，避免妨碍修复持锁。
pub fn assert_current_environment(root: &Path, release_id: &str) -> Result<()> {
    assert_binding_ready(root)?;
    let Some(bindings) = load_bindings(root)? else {
        return Ok(());
    };
    let registry = Registry::load(root)?;
    let current = bindings.current.context("活动资料组合缺失")?;
    if registry.current.as_deref() != Some(release_id) || current.release_id != release_id {
        bail!("活动资料组合与Registry不符，请恢复或显式选择完整组合");
    }
    validate_binding(root, &current)
}
/// 合法GUI变更成功后，同租约同步当前组合；旧健康组合保持原实例和代次，不自动追认新环境。
pub fn sync_current_environment(ctx: &WorkspaceMutation, release_id: &str) -> Result<()> {
    sync_current_component(ctx, release_id, "gui")
}
/// 只同步此前已选择的引擎；安装新引擎不代表自动选择进当前资料组合。
pub fn sync_current_engine(
    ctx: &WorkspaceMutation,
    release_id: &str,
    engine_id: &str,
) -> Result<()> {
    if !matches!(
        engine_id,
        "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth"
    ) {
        bail!("未知引擎组件");
    }
    sync_current_component(ctx, release_id, engine_id)
}
fn sync_current_component(
    ctx: &WorkspaceMutation,
    release_id: &str,
    component: &str,
) -> Result<()> {
    let root = &ctx.layout().root;
    assert_binding_ready(root)?;
    if ctx
        .layout()
        .release_dir
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        != release_id
    {
        bail!("资料环境同步租约版本不符");
    }
    let Some(mut bindings) = load_bindings(root)? else {
        return Ok(());
    };
    let mut registry = Registry::load(root)?;
    if registry.current.as_deref() != Some(release_id) {
        return Ok(());
    }
    let current = bindings.current.as_mut().context("当前资料组合缺失")?;
    if current.release_id != release_id {
        bail!("资料环境同步不跨release隐式切换");
    }
    if !current.environment_instance_ids.contains_key(component) {
        return Ok(());
    }
    let (id, generation) = if component == "gui" {
        let binding = registry
            .gui_binding(release_id)
            .context("GUI权威实例缺失")?;
        (binding.instance_id.clone(), binding.generation)
    } else {
        let path = state_path(root, current, component);
        let state: serde_json::Value =
            serde_json::from_slice(&optional_bytes(&path)?.context("引擎权威状态缺失")?)?;
        (
            state["instance_id"]
                .as_str()
                .context("引擎实例ID缺失")?
                .to_string(),
            state["generation"].as_u64().context("引擎generation缺失")?,
        )
    };
    if current.environment_instance_ids.get(component) == Some(&id)
        && current.environment_generations.get(component) == Some(&generation)
    {
        return Ok(());
    }
    current
        .environment_instance_ids
        .insert(component.into(), id);
    current
        .environment_generations
        .insert(component.into(), generation);
    current.healthy_at = None;
    validate_binding_selected(root, current, Some(component))?;
    if let Some(installed) = registry
        .installed
        .iter_mut()
        .find(|v| v.release_id == release_id)
    {
        installed.healthy_at = None;
    }
    bindings.generation = bindings
        .generation
        .checked_add(1)
        .context("资料绑定代次耗尽")?;
    commit_bindings(ctx, registry, bindings)
}
/// 中断恢复总是精确还原旧控制字节；保留新profile和备份，不静默合并资料。
pub fn recover_binding(ctx: &WorkspaceMutation) -> Result<()> {
    let root = &ctx.layout().root;
    let path = binding_intent(root);
    let mut intent: BindingIntent = serde_json::from_slice(&fs::read(&path)?)?;
    validate_binding_intent(root, &intent)?;
    if intent.status == "committed" || intent.status == "rolled_back" {
        return Ok(());
    }
    if intent.status != "committing" {
        bail!("未知资料绑定事务状态");
    }
    let current = fs::read(root.join("state/registry.json"))?;
    if current != intent.old_registry && current != encoded(&intent.new_registry)? {
        bail!("当前Registry不是该事务允许的原字节前后状态，拒绝恢复覆盖");
    }
    let binding_path = root.join("state/profile-bindings.json");
    let raw = optional_bytes(&binding_path)?;
    if raw != intent.old_bindings
        && raw.as_deref() != Some(encoded(&intent.new_bindings)?.as_slice())
    {
        bail!("资料侧档出现非本事务变化");
    }
    // 使用原始字节，不能通过反序列化再编码声称原字节回退。
    atomic_bytes(&root.join("state/registry.json"), &intent.old_registry)?;
    match &intent.old_bindings {
        Some(raw) => atomic_bytes(&binding_path, raw)?,
        None => {
            if binding_path.exists() {
                fs::rename(
                    &binding_path,
                    root.join("backups")
                        .join(&intent.transaction)
                        .join("uncommitted-bindings.json"),
                )?;
            }
        }
    }
    intent.status = "rolled_back".into();
    seal_intent(&mut intent)?;
    model::write_json_atomic(&path, &intent)
}
fn atomic_bytes(path: &Path, bytes: &[u8]) -> Result<()> {
    regular_chain(path)?;
    let temp = path.with_extension(format!(
        "restore-{}-{}.part",
        std::process::id(),
        NEXT_WRITE.fetch_add(1, Ordering::Relaxed)
    ));
    regular_chain(&temp)?;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    replace_bytes(&temp, path)
}
#[cfg(windows)]
fn replace_bytes(temp: &Path, target: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, new: *const u16, flags: u32) -> i32;
    }
    let from: Vec<u16> = temp.as_os_str().encode_wide().chain(Some(0)).collect();
    let to: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    if unsafe { MoveFileExW(from.as_ptr(), to.as_ptr(), 0x1 | 0x8) } == 0 {
        return Err(std::io::Error::last_os_error()).context("资料控制原子恢复失败");
    }
    Ok(())
}
#[cfg(not(windows))]
fn replace_bytes(temp: &Path, target: &Path) -> Result<()> {
    fs::rename(temp, target)?;
    fs::File::open(target.parent().context("恢复目标缺少父目录")?)?.sync_all()?;
    Ok(())
}
pub fn rollback_plan(root: &Path) -> Result<BindingPlan> {
    let bindings = load_bindings(root)?.context("尚无可恢复资料组合")?;
    let previous = bindings
        .previous_known_good
        .context("没有已健康验证的上一完整资料组合")?;
    preview_binding(
        root,
        &BindingRequest {
            binding: previous,
            expected_generation: bindings.generation,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::operations::{OperationKind, OperationManager};
    struct Fixture {
        base: PathBuf,
        root: PathBuf,
        request: ImportRequest,
    }
    impl Fixture {
        fn new() -> Self {
            let base = std::env::temp_dir().join(format!(
                "launcher-m4-{}-{}",
                std::process::id(),
                NEXT_WRITE.fetch_add(1, Ordering::Relaxed)
            ));
            let root = base.join("新工作区 空格");
            let source = base.join("旧包 只读源");
            fs::create_dir_all(source.join("user_data/presets")).unwrap();
            fs::create_dir_all(source.join("datasets")).unwrap();
            fs::create_dir_all(source.join("assets")).unwrap();
            fs::write(source.join("user_data/settings.json"),br#"{"schema_version":1,"revision":0,"paths":{"datasets":"datasets","python":{"kohya":"venv/Scripts/python.exe"}}}"#).unwrap();
            fs::write(
                source.join("user_data/presets/first.json"),
                br#"{"schema_version":1,"config":{"train_data_dir":"datasets"}}"#,
            )
            .unwrap();
            fs::write(
                source.join("user_data/auth.json"),
                br#"{"token":"fixture-secret-value"}"#,
            )
            .unwrap();
            fs::write(
                source.join("assets/config.json"),
                br#"{"last_path":"datasets"}"#,
            )
            .unwrap();
            fs::write(
                source.join("assets/not-a-setting.safetensors"),
                b"never copied",
            )
            .unwrap();
            fs::create_dir_all(source.join("toml")).unwrap();
            fs::write(source.join("toml/old.toml"), b"train_data_dir='datasets'").unwrap();
            let release = Catalog::embedded().unwrap().releases()[0].id.clone();
            let request = ImportRequest {
                release_id: release,
                source_root: source,
                profile_id: "imported".into(),
                include_credentials: false,
                external_paths: vec![],
            };
            Self {
                base,
                root,
                request,
            }
        }
        fn setup_binding(&self) -> Binding {
            let release = Catalog::embedded()
                .unwrap()
                .release(&self.request.release_id)
                .unwrap()
                .clone();
            let mut registry = Registry {
                schema_version: 2,
                ..Registry::default()
            };
            registry.record_installed(&release).unwrap();
            registry
                .bind_gui(
                    &release.id,
                    model::EnvironmentBinding {
                        instance_id: "g0123456789abcdef".into(),
                        storage_version: 1,
                        recipe_id: release.environment_recipe.clone(),
                        recipe_sha256: "a".repeat(64),
                        generation: 1,
                    },
                )
                .unwrap();
            registry.activate(&release.id).unwrap();
            registry.mark_healthy(&release.id).unwrap();
            registry.store(&self.root).unwrap();
            let state = serde_json::json!({"schema_version":1,"component":"gui","instance_id":"g0123456789abcdef","release_id":release.id,"generation":1,"validated_generation":1,"dirty":false,"pending":null});
            model::write_json_atomic(
                &self.root.join("state/instances/g0123456789abcdef.json"),
                &state,
            )
            .unwrap();
            Binding {
                release_id: self.request.release_id.clone(),
                profile_id: self.request.profile_id.clone(),
                profile_schema_version: 1,
                environment_instance_ids: BTreeMap::from([(
                    "gui".into(),
                    "g0123456789abcdef".into(),
                )]),
                environment_generations: BTreeMap::from([("gui".into(), 1)]),
                healthy_at: None,
            }
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            if self.base.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .base
                    .file_name()
                    .is_some_and(|n| n.to_string_lossy().starts_with("launcher-m4-"))
            {
                let _ = fs::remove_dir_all(&self.base);
            }
        }
    }
    fn cancelled() -> CancelToken {
        let manager = OperationManager::default();
        let handle = manager
            .start("import-cancel", OperationKind::Execute)
            .unwrap();
        manager.cancel("import-cancel").unwrap();
        handle.cancel_token()
    }
    #[test]
    fn import_is_readonly_keeps_references_and_never_activates() {
        let f = Fixture::new();
        let before = scan(&f.request).unwrap();
        assert!(!f.root.exists());
        assert!(before.excluded.iter().any(|n| n.ends_with("auth.json")));
        assert!(before.unsupported.iter().any(|n| n.ends_with("old.toml")));
        assert!(before
            .files
            .iter()
            .all(|v| !v.source_relative.to_string_lossy().contains("safetensors")));
        assert!(before
            .references
            .iter()
            .any(|r| r.kind == "dataset"
                && r.absolute_path == f.request.source_root.join("datasets")));
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let original = Registry::load(&f.root).unwrap();
        let plan = preview(&f.root, &f.request).unwrap();
        assert!(plan.conflicts.is_empty());
        let receipt = execute(&ctx, &f.request, &plan.plan_sha256, &CancelToken::new()).unwrap();
        assert_eq!(receipt.status, "committed");
        assert!(!receipt.activated);
        assert_eq!(Registry::load(&f.root).unwrap(), original);
        assert_eq!(scan(&f.request).unwrap(), before);
        let settings: serde_json::Value = serde_json::from_slice(
            &fs::read(plan.target_profile.join("user_data/settings.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(
            settings["paths"]["datasets"],
            f.request
                .source_root
                .join("datasets")
                .to_string_lossy()
                .as_ref()
        );
        assert!(settings["paths"].get("python").is_none());
        assert!(!plan.target_profile.join("user_data/auth.json").exists());
    }
    #[test]
    fn empty_mapped_directories_import_and_recover_rejects_unlisted_directories() {
        for interrupted in [false, true] {
            let f = Fixture::new();
            // 没有可复制的 compat 文件时，空目录仍须允许其精确祖先。
            fs::remove_file(f.request.source_root.join("assets/config.json")).unwrap();
            fs::create_dir_all(f.request.source_root.join("toml/empty/nested")).unwrap();
            let before = scan(&f.request).unwrap();
            assert!(!before
                .files
                .iter()
                .any(|file| file.target_relative.starts_with("compat")));
            let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
            let original = Registry::load(&f.root).unwrap();
            let plan = preview(&f.root, &f.request).unwrap();
            let receipt = if interrupted {
                assert!(execute(&ctx, &f.request, &plan.plan_sha256, &cancelled()).is_err());
                let transaction = format!(
                    "data-import-{}-{}",
                    f.request.profile_id,
                    &plan.plan_sha256[..16]
                );
                let (_, staged) = import_paths(&f.root, &transaction).unwrap();
                let payload = staged.join("payload");
                let mapped = PathBuf::from("compat")
                    .join(&f.request.release_id)
                    .join("toml/empty/nested");
                ctx.layout().ensure_dir(&payload.join(&mapped)).unwrap();
                ctx.layout().ensure_dir(&staged.join("partial")).unwrap();
                model::write_json_atomic(
                    &staged.join("owner.json"),
                    &serde_json::json!({"schema_version":VERSION,"transaction":transaction,"plan_sha256":plan.plan_sha256}),
                )
                .unwrap();
                let unlisted = payload
                    .join("compat")
                    .join(&f.request.release_id)
                    .join("unlisted-empty");
                ctx.layout().ensure_dir(&unlisted).unwrap();
                let error = recover(&ctx, &transaction, &CancelToken::new()).unwrap_err();
                assert!(error.to_string().contains("资料副本含清单外目录"));
                assert!(unlisted.is_dir());
                assert!(!plan.target_profile.exists());
                // 只移动本测试创建的清单外目录，原拒绝现场不应由恢复入口删除。
                fs::rename(&unlisted, f.base.join("preserved-unlisted-empty")).unwrap();
                recover(&ctx, &transaction, &CancelToken::new()).unwrap()
            } else {
                execute(&ctx, &f.request, &plan.plan_sha256, &CancelToken::new()).unwrap()
            };
            assert_eq!(receipt.status, "committed");
            assert!(!receipt.activated);
            assert!(plan
                .target_profile
                .join("compat")
                .join(&f.request.release_id)
                .join("toml/empty/nested")
                .is_dir());
            assert_eq!(scan(&f.request).unwrap(), before);
            assert_eq!(Registry::load(&f.root).unwrap(), original);
            assert_eq!(
                recover(&ctx, &receipt.transaction, &CancelToken::new())
                    .unwrap()
                    .status,
                "committed"
            );
        }
    }
    #[test]
    fn stale_plans_conflicts_and_unknown_schema_fail_closed() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let plan = preview(&f.root, &f.request).unwrap();
        fs::write(
            f.request.source_root.join("assets/config.json"),
            b"{\"last_path\":\"changed\"}",
        )
        .unwrap();
        assert!(execute(&ctx, &f.request, &plan.plan_sha256, &CancelToken::new()).is_err());
        assert!(!plan.target_profile.exists());
        fs::create_dir_all(f.request.source_root.join("output")).unwrap();
        fs::create_dir_all(f.request.source_root.join("outputs")).unwrap();
        fs::write(f.request.source_root.join("output/a.txt"), b"a").unwrap();
        fs::write(f.request.source_root.join("outputs/A.txt"), b"b").unwrap();
        assert!(!preview(&f.root, &f.request).unwrap().conflicts.is_empty());
        fs::write(
            f.request.source_root.join("user_data/settings.json"),
            br#"{"schema_version":99}"#,
        )
        .unwrap();
        assert!(scan(&f.request).is_err());
    }
    #[test]
    fn cancelled_import_resumes_exact_partial_and_rejects_extra_payload() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let plan = preview(&f.root, &f.request).unwrap();
        assert!(execute(&ctx, &f.request, &plan.plan_sha256, &cancelled()).is_err());
        assert!(!plan.target_profile.exists());
        let transaction = format!(
            "data-import-{}-{}",
            f.request.profile_id,
            &plan.plan_sha256[..16]
        );
        let (_, staged) = import_paths(&f.root, &transaction).unwrap();
        ctx.layout().ensure_dir(&staged.join("payload")).unwrap();
        ctx.layout().ensure_dir(&staged.join("partial")).unwrap();
        model::write_json_atomic(&staged.join("owner.json"),&serde_json::json!({"schema_version":VERSION,"transaction":transaction,"plan_sha256":plan.plan_sha256})).unwrap();
        let output = copied_bytes(
            &f.request
                .source_root
                .join(&plan.scan.files[0].source_relative),
            &plan.scan.files[0],
        )
        .unwrap();
        fs::write(staged.join("partial/0.part"), &output[..3]).unwrap();
        fs::write(staged.join("payload/unowned.txt"), b"preserve").unwrap();
        assert!(recover(&ctx, &transaction, &CancelToken::new()).is_err());
        assert!(!plan.target_profile.exists());
        fs::rename(
            staged.join("payload/unowned.txt"),
            f.base.join("preserved-unowned.txt"),
        )
        .unwrap();
        assert_eq!(
            recover(&ctx, &transaction, &CancelToken::new())
                .unwrap()
                .status,
            "committed"
        );
        assert_eq!(
            recover(&ctx, &transaction, &CancelToken::new())
                .unwrap()
                .status,
            "committed"
        );
    }
    #[test]
    fn tampered_import_relative_paths_cannot_escape() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let plan = preview(&f.root, &f.request).unwrap();
        assert!(execute(&ctx, &f.request, &plan.plan_sha256, &cancelled()).is_err());
        let transaction = format!(
            "data-import-{}-{}",
            f.request.profile_id,
            &plan.plan_sha256[..16]
        );
        let (path, _) = import_paths(&f.root, &transaction).unwrap();
        let mut intent: ImportIntent = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        intent.plan.scan.files[0].target_relative = PathBuf::from("../outside.txt");
        model::write_json_atomic(&path, &intent).unwrap();
        assert!(recover(&ctx, &transaction, &CancelToken::new()).is_err());
        assert!(!f.root.join("outside.txt").exists());
    }
    #[test]
    fn legitimate_environment_changes_remain_recoverable_and_sync_without_rewriting_previous() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let import = preview(&f.root, &f.request).unwrap();
        execute(&ctx, &f.request, &import.plan_sha256, &CancelToken::new()).unwrap();
        let binding = f.setup_binding();
        let request = BindingRequest {
            binding,
            expected_generation: 0,
        };
        let plan = preview_binding(&f.root, &request).unwrap();
        execute_binding(&ctx, &request, &plan.plan_sha256, |_, _| Ok(())).unwrap();
        drop(ctx);
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        mark_healthy(&ctx, &f.request.release_id).unwrap();
        let previous = load_bindings(&f.root).unwrap().unwrap().previous_known_good;
        let mut registry = Registry::load(&f.root).unwrap();
        let mut gui = registry.gui_binding(&f.request.release_id).unwrap().clone();
        gui.generation = 2;
        registry.bind_gui(&f.request.release_id, gui).unwrap();
        registry.store(&f.root).unwrap();
        let path = f.root.join("state/instances/g0123456789abcdef.json");
        let mut state: serde_json::Value =
            serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        state["generation"] = 2.into();
        state["validated_generation"] = 2.into();
        model::write_json_atomic(&path, &state).unwrap();
        drop(ctx);
        assert_eq!(
            load_active_profile(&f.root, &f.request.release_id).unwrap(),
            Some("imported".into())
        );
        assert!(assert_current_environment(&f.root, &f.request.release_id).is_err());
        let controls_before = fs::read(f.root.join("state/registry.json")).unwrap();
        let other = Catalog::embedded()
            .unwrap()
            .releases()
            .iter()
            .find(|r| r.id != f.request.release_id)
            .unwrap()
            .id
            .clone();
        let mut engine = crate::core::Engine::new(f.root.clone(), std::sync::Arc::new(|_| {}));
        assert!(engine
            .start(&f.root)
            .err()
            .expect("旧tuple必须在实际启动前拒绝")
            .to_string()
            .contains("先使用GUI实例回退"));
        assert!(engine.select_release(&f.root, &other).is_err());
        assert!(engine.rollback_release(&f.root).is_err());
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            controls_before
        );
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        assert_eq!(ctx.layout().profile, f.root.join("profiles/imported"));
        sync_current_environment(&ctx, &f.request.release_id).unwrap();
        let bindings = load_bindings(&f.root).unwrap().unwrap();
        assert_eq!(
            bindings.current.as_ref().unwrap().environment_generations["gui"],
            2
        );
        assert!(bindings.current.as_ref().unwrap().healthy_at.is_none());
        assert_eq!(bindings.previous_known_good, previous);
        assert_current_environment(&f.root, &f.request.release_id).unwrap();
        let error = rollback_plan(&f.root).unwrap_err().to_string();
        assert!(error.contains("先使用GUI实例回退"));
    }
    #[test]
    fn binding_requires_validator_and_recovers_both_exact_control_files() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &f.request.release_id).unwrap();
        let import = preview(&f.root, &f.request).unwrap();
        execute(&ctx, &f.request, &import.plan_sha256, &CancelToken::new()).unwrap();
        let binding = f.setup_binding();
        let request = BindingRequest {
            binding,
            expected_generation: 0,
        };
        let plan = preview_binding(&f.root, &request).unwrap();
        assert!(plan.default_upgrade.is_some());
        let old = fs::read(f.root.join("state/registry.json")).unwrap();
        assert!(
            execute_binding(&ctx, &request, &plan.plan_sha256, |_, _| bail!(
                "fixture validator failure"
            ))
            .is_err()
        );
        assert_eq!(fs::read(f.root.join("state/registry.json")).unwrap(), old);
        execute_binding(&ctx, &request, &plan.plan_sha256, |_, profile| {
            if !profile.join("user_data/settings.json").is_file() {
                bail!("fixture profile absent");
            }
            Ok(())
        })
        .unwrap();
        assert_eq!(
            load_active_profile(&f.root, &f.request.release_id).unwrap(),
            Some("imported".into())
        );
        assert_eq!(
            rollback_plan(&f.root).unwrap().request.binding.profile_id,
            "default"
        );
        let path = binding_intent(&f.root);
        let mut intent: BindingIntent = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        intent.status = "committing".into();
        seal_intent(&mut intent).unwrap();
        model::write_json_atomic(&path, &intent).unwrap();
        assert!(assert_binding_ready(&f.root).is_err());
        assert_eq!(
            load_active_profile(&f.root, &f.request.release_id).unwrap(),
            None
        );
        recover_binding(&ctx).unwrap();
        assert_eq!(fs::read(f.root.join("state/registry.json")).unwrap(), old);
        assert!(!f.root.join("state/profile-bindings.json").exists());
        assert_binding_ready(&f.root).unwrap();
    }
}
