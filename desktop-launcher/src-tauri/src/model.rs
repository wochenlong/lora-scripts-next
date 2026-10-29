//! 启动器持久化合同。调用方必须在修改期间持有 Layout 工作区锁。
use anyhow::{bail, Context, Result};
use fs2::FileExt;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use std::{
    collections::BTreeSet,
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

pub const WORKSPACE_MARKER: &str = "next-trainer-desktop-v1";
pub const SCHEMA_VERSION: u32 = 1;
pub const PROFILE_SCHEMA_VERSION: u32 = 1;
pub const MAX_DOWNLOAD_BYTES: u64 = 200_000_000;
/// 受固定配方授权的单个大wheel上限；旧源码目录仍沿用200MB限制。
pub const MAX_MANAGED_ASSET_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_EXTRACT_BYTES: u64 = 2_000_000_000;
pub const PROFILE_DIRECTORIES: &[&str] = &["user_data", "library", "compat"];
const RECEIPT: &str = "release.json";
const MARKER_FILE: &str = ".launcher-workspace";
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Archive {
    pub url: String,
    pub sha256: String,
    pub bytes: u64,
    pub unpacked_bytes: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UvAsset {
    pub version: String,
    pub url: String,
    pub sha256: String,
    pub exe_sha256: String,
    pub bytes: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Release {
    pub schema_version: u32,
    pub id: String,
    pub channel: String,
    pub version: String,
    pub commit: String,
    pub archive: Archive,
    pub python: String,
    pub uv: UvAsset,
    pub environment_recipe: String,
    pub profile_schema_version: u32,
    pub data_contract: String,
    pub required_files: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalog {
    pub schema_version: u32,
    pub releases: Vec<Release>,
}

fn schema(version: u32, kind: &str) -> Result<()> {
    if version != SCHEMA_VERSION {
        bail!("{kind} schema {version} 不受支持；保留原文件并拒绝变更");
    }
    Ok(())
}
fn hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
/// 同时按 Windows 规则校验，即使单元测试运行于其他操作系统。
pub fn validate_component(value: &str) -> Result<()> {
    if value.is_empty()
        || value == "."
        || value == ".."
        || value.len() > 180
        || value
            .chars()
            .any(|c| c <= '\u{1f}' || "<>:\"/\\|?*".contains(c))
        || value.ends_with('.')
        || value.ends_with(' ')
    {
        bail!("非法路径名称：{value:?}");
    }
    let stem = value
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    if matches!(
        stem.as_str(),
        "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$"
    ) || ["COM", "LPT"].iter().any(|prefix| {
        stem.strip_prefix(prefix).is_some_and(|tail| {
            matches!(
                tail,
                "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
            )
        })
    }) {
        bail!("Windows 保留路径名称：{value}");
    }
    Ok(())
}
fn validate_relative(value: &str) -> Result<()> {
    let path = Path::new(value);
    if path.is_absolute() || value.contains('\\') || value.contains(':') {
        bail!("非法相对路径");
    }
    for part in value.split('/') {
        validate_component(part)?;
    }
    Ok(())
}
pub fn validate_release_id(value: &str) -> Result<()> {
    validate_component(value)?;
    let (channel, commit) = value.split_once('-').context("版本 ID 缺少分支与提交")?;
    if !matches!(channel, "main" | "dev") || !hex(commit, 40) {
        bail!("版本 ID 必须为 main/dev 加完整提交");
    }
    Ok(())
}

pub(crate) fn legacy_storage_version(value: &u32) -> bool {
    *value == 0
}

pub(crate) fn validate_environment_storage(instance_id: &str, storage_version: u32) -> Result<()> {
    validate_component(instance_id)?;
    match storage_version {
        0 if instance_id.len() <= 96 => Ok(()),
        1 if instance_id
            .strip_prefix('g')
            .is_some_and(|suffix| hex(suffix, 16)) =>
        {
            Ok(())
        }
        _ => bail!("环境存储版本或实例 ID 不受支持，拒绝重新解释原路径"),
    }
}

/// 存储版本只选择固定命名空间，不接受记录中指定任意相对路径。
pub(crate) fn environment_path(
    root: &Path,
    release_id: &str,
    instance_id: &str,
    storage_version: u32,
) -> Result<PathBuf> {
    validate_release_id(release_id)?;
    validate_environment_storage(instance_id, storage_version)?;
    let path = match storage_version {
        0 => root
            .join("environments")
            .join(release_id)
            .join("instances")
            .join(instance_id)
            .join("gui"),
        1 => root.join("e").join(instance_id),
        _ => unreachable!("存储版本已经校验"),
    };
    check_chain(&path)?;
    Ok(path)
}

impl Release {
    pub fn validate(&self) -> Result<()> {
        schema(self.schema_version, "release")?;
        schema(self.profile_schema_version, "profile")?;
        validate_release_id(&self.id)?;
        if self.id != format!("{}-{}", self.channel, self.commit)
            || !hex(&self.commit, 40)
            || self.version.trim().is_empty()
            || !hex(&self.archive.sha256, 64)
            || !hex(&self.uv.sha256, 64)
            || !hex(&self.uv.exe_sha256, 64)
            || self.archive.bytes == 0
            || self.archive.bytes > MAX_DOWNLOAD_BYTES
            || self.archive.unpacked_bytes == 0
            || self.archive.unpacked_bytes > MAX_EXTRACT_BYTES
            || self.uv.bytes == 0
            || self.uv.bytes > MAX_DOWNLOAD_BYTES
        {
            bail!("版本元数据不完整或身份不一致");
        }
        if self.archive.url
            != format!(
                "https://codeload.github.com/wochenlong/lora-scripts-next/zip/{}",
                self.commit
            )
        {
            bail!("源码 URL 与固定提交不一致");
        }
        if self.uv.url != format!("https://github.com/astral-sh/uv/releases/download/{}/uv-x86_64-pc-windows-msvc.zip", self.uv.version) {
            bail!("uv URL 与固定版本不一致");
        }
        validate_component(&self.python)?;
        validate_component(&self.environment_recipe)?;
        if !matches!(self.data_contract.as_str(), "native-v1" | "legacy-view-v1") {
            bail!("未知数据合同，拒绝启动或迁移");
        }
        if self.required_files.is_empty() {
            bail!("缺少必须文件清单");
        }
        for file in &self.required_files {
            validate_relative(file)?;
        }
        Ok(())
    }
}
impl Catalog {
    pub fn embedded() -> Result<Self> {
        let catalog: Self = serde_json::from_str(include_str!("../../catalog/releases.json"))?;
        catalog.validate()?;
        Ok(catalog)
    }
    pub fn validate(&self) -> Result<()> {
        schema(self.schema_version, "catalog")?;
        let mut ids = BTreeSet::new();
        for release in &self.releases {
            release.validate()?;
            if !ids.insert(&release.id) {
                bail!("目录包含重复版本 ID");
            }
        }
        if ids.is_empty() {
            bail!("版本目录为空");
        }
        Ok(())
    }
    pub fn release(&self, id: &str) -> Result<&Release> {
        validate_release_id(id)?;
        self.releases
            .iter()
            .find(|release| release.id == id)
            .context("版本不在嵌入目录中")
    }
    pub fn releases(&self) -> &[Release] {
        &self.releases
    }
}

fn check_chain(path: &Path) -> Result<()> {
    let mut current = PathBuf::new();
    for component in path.components() {
        if matches!(component, Component::ParentDir | Component::CurDir) {
            bail!("路径包含不允许的跳转");
        }
        if let Component::Normal(name) = component {
            validate_component(&name.to_string_lossy())?;
        }
        current.push(component.as_os_str());
        match fs::symlink_metadata(&current) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() {
                    bail!("路径包含符号链接：{}", current.display());
                }
                #[cfg(windows)]
                {
                    use std::os::windows::fs::MetadataExt;
                    if metadata.file_attributes() & 0x400 != 0 {
                        bail!("路径包含重解析目录或文件，拒绝修改：{}", current.display());
                    }
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

#[derive(Clone, Debug)]
pub struct Layout {
    pub root: PathBuf,
    pub release_dir: PathBuf,
    pub app: PathBuf,
    pub environment: PathBuf,
    pub profile: PathBuf,
    pub staging: PathBuf,
    pub run: PathBuf,
}

/// 一次变更的完整工作区租约。构造时校验布局并持锁，子步骤只借用它，
/// 避免安装/修复之间释放锁，也避免内部重复获取同一文件锁。
pub struct WorkspaceMutation {
    layout: Layout,
    _lease: File,
}
impl WorkspaceMutation {
    pub fn acquire(root: &Path, release_id: &str) -> Result<Self> {
        let layout = Layout::new(root, release_id)?;
        let lease = layout.prepare_workspace()?;
        Ok(Self {
            layout,
            _lease: lease,
        })
    }

    pub fn layout(&self) -> &Layout {
        &self.layout
    }
}

impl Layout {
    pub fn new(root: &Path, release_id: &str) -> Result<Self> {
        validate_release_id(release_id)?;
        if !root.is_absolute() || root.parent().is_none() {
            bail!("工作区必须为独立绝对目录");
        }
        check_chain(root)?;
        let release_dir = root.join("releases").join(release_id);
        let registry = Registry::load(root)?;
        let environment = match registry.gui_binding(release_id) {
            Some(binding) => environment_path(
                root,
                release_id,
                &binding.instance_id,
                binding.storage_version,
            )?,
            None => root.join("environments").join(release_id).join("gui"),
        };
        Ok(Self {
            root: root.to_path_buf(),
            app: release_dir.join("app"),
            release_dir,
            environment,
            profile: root.join("profiles/default"),
            staging: root.join("staging").join(release_id),
            run: root.join("run").join(release_id),
        })
    }
    pub fn guard_path(&self, path: &Path) -> Result<()> {
        if !path.starts_with(&self.root) {
            bail!("目标位于工作区外");
        }
        check_chain(path)
    }
    pub fn ensure_dir(&self, path: &Path) -> Result<()> {
        self.guard_path(path)?;
        fs::create_dir_all(path)?;
        self.guard_path(path)?;
        if !path.is_dir() {
            bail!("目标不是目录");
        }
        Ok(())
    }
    /// 第一次只接受空目录；拒绝旧样包、未知标记和未知 schema。
    pub fn prepare_workspace(&self) -> Result<File> {
        self.guard_path(&self.root)?;
        let marker = self.root.join(MARKER_FILE);
        self.guard_path(&marker)?;
        if self.root.exists() && !marker.is_file() && fs::read_dir(&self.root)?.next().is_some() {
            bail!("请选择空目录或本启动器正式工作区；现有文件未修改");
        }
        if marker.exists() && fs::read_to_string(&marker)? != WORKSPACE_MARKER {
            bail!("工作区标记不支持；不会自动迁移或覆盖");
        }
        // 先验证现有状态，不因损坏 registry 在其他目录写入。
        let _ = Registry::load(&self.root)?;
        let _ = Journal::load_all(&self.root)?;
        let profile_file = self.profile.join("profile.json");
        if profile_file.exists() {
            Profile::load(&profile_file)?;
        }
        fs::create_dir_all(&self.root)?;
        let lock_path = self.root.join(".launcher-lock");
        self.guard_path(&lock_path)?;
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(lock_path)?;
        lock.try_lock_exclusive()
            .context("工作区正由另一个启动器或受管进程使用")?;
        // 锁内重新读取，防止另一实例先完成变更。
        let _ = Registry::load(&self.root)?;
        let _ = Journal::load_all(&self.root)?;
        if marker.exists() {
            if fs::read_to_string(&marker)? != WORKSPACE_MARKER {
                bail!("工作区标记发生改变");
            }
        } else {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(marker)?
                .write_all(WORKSPACE_MARKER.as_bytes())?;
        }
        for name in [
            "state",
            "releases",
            "environments",
            "e",
            "profiles",
            "tools",
            "python",
            "cache",
            "staging",
            "backups",
            "run",
        ] {
            self.ensure_dir(&self.root.join(name))?;
        }
        self.ensure_dir(&self.profile)?;
        if profile_file.exists() {
            Profile::load(&profile_file)?;
        } else {
            write_json_atomic(&profile_file, &Profile::default())?;
        }
        for name in PROFILE_DIRECTORIES {
            self.ensure_dir(&self.profile.join(name))?;
        }
        Ok(lock)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    pub schema_version: u32,
    pub id: String,
}
impl Default for Profile {
    fn default() -> Self {
        Self {
            schema_version: PROFILE_SCHEMA_VERSION,
            id: "default".into(),
        }
    }
}
impl Profile {
    pub fn load(path: &Path) -> Result<Self> {
        check_chain(path)?;
        let profile: Self = read_json(path)?;
        schema(profile.schema_version, "profile")?;
        if profile.id != "default" {
            bail!("仅支持 default profile");
        }
        Ok(profile)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EnvironmentBinding {
    pub instance_id: String,
    #[serde(default, skip_serializing_if = "legacy_storage_version")]
    pub storage_version: u32,
    pub recipe_id: String,
    pub recipe_sha256: String,
    pub generation: u64,
}
impl EnvironmentBinding {
    pub fn validate(&self) -> Result<()> {
        validate_environment_storage(&self.instance_id, self.storage_version)?;
        validate_component(&self.recipe_id)?;
        if self.instance_id.len() > 96 || !hex(&self.recipe_sha256, 64) || self.generation == 0 {
            bail!("环境绑定身份、配方或generation无效");
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Installed {
    pub release_id: String,
    pub healthy_at: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gui: Option<EnvironmentBinding>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Registry {
    pub schema_version: u32,
    pub profile_schema_version: u32,
    pub current: Option<String>,
    pub previous_known_good: Option<String>,
    pub installed: Vec<Installed>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub base_python_pending: Option<String>,
}
impl Default for Registry {
    fn default() -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            profile_schema_version: PROFILE_SCHEMA_VERSION,
            current: None,
            previous_known_good: None,
            installed: Vec::new(),
            base_python_pending: None,
        }
    }
}
impl Registry {
    pub fn assert_base_python_ready(&self) -> Result<()> {
        if let Some(transaction) = &self.base_python_pending {
            bail!("基础Python引用闭包待恢复（{transaction}），禁止启动或修改相关组件");
        }
        Ok(())
    }
    pub fn load(root: &Path) -> Result<Self> {
        let path = root.join("state/registry.json");
        check_chain(&path)?;
        let registry = if path.exists() {
            read_json(&path).context("版本登记损坏，拒绝覆盖；请保留文件诊断")?
        } else {
            Self::default()
        };
        registry.validate()?;
        Ok(registry)
    }
    pub fn validate(&self) -> Result<()> {
        if !matches!(self.schema_version, 1..=3) {
            bail!(
                "registry schema {} 不受支持；保留原文件并拒绝变更",
                self.schema_version
            );
        }
        schema(self.profile_schema_version, "profile")?;
        if let Some(transaction) = &self.base_python_pending {
            validate_component(transaction)?;
            if self.schema_version != 3 || !transaction.starts_with("base-python-") {
                bail!("基础Python事务gate身份无效");
            }
        }
        let mut ids = BTreeSet::new();
        let mut environment_ids = BTreeSet::new();
        for installed in &self.installed {
            validate_release_id(&installed.release_id)?;
            if !ids.insert(&installed.release_id) {
                bail!("重复 installed 记录");
            }
            if let Some(binding) = &installed.gui {
                if self.schema_version < 2 {
                    bail!("schema 1 不接受环境实例绑定");
                }
                binding.validate()?;
                if binding.storage_version == 1 && !environment_ids.insert(&binding.instance_id) {
                    bail!("同一环境实例不可绑定到多个发布，拒绝跨版本复用");
                }
            }
        }
        for pointer in [&self.current, &self.previous_known_good]
            .into_iter()
            .flatten()
        {
            validate_release_id(pointer)?;
            if !ids.contains(pointer) {
                bail!("版本指针缺少 installed 记录");
            }
        }
        if let Some(previous) = &self.previous_known_good {
            if !self
                .installed
                .iter()
                .any(|i| i.release_id == *previous && i.healthy_at.is_some())
            {
                bail!("回退目标没有健康验证记录");
            }
        }
        Ok(())
    }
    pub fn store(&self, root: &Path) -> Result<()> {
        self.validate()?;
        // 未知/损坏的磁盘状态禁止用当前内存对象覆盖。
        let current = Self::load(root)?;
        if self.schema_version < current.schema_version {
            bail!("拒绝降级覆盖版本登记协议；原文件保留");
        }
        write_json_atomic(&root.join("state/registry.json"), self)
    }
    /// Base-Python state writes keep unpublished temporary files inside the exact
    /// durable transaction namespace, outside the reviewed state protection tree.
    pub(crate) fn store_for_base(&self, root: &Path, transaction: &str) -> Result<()> {
        self.validate()?;
        let current = Self::load(root)?;
        if self.schema_version < current.schema_version {
            bail!("拒绝降级覆盖版本登记协议");
        }
        write_base_json_atomic(root, transaction, &root.join("state/registry.json"), self)
    }
    pub fn record_installed(&mut self, release: &Release) -> Result<()> {
        release.validate()?;
        if release.profile_schema_version != self.profile_schema_version {
            bail!("profile schema 不兼容");
        }
        if !self.installed.iter().any(|i| i.release_id == release.id) {
            self.installed.push(Installed {
                release_id: release.id.clone(),
                healthy_at: None,
                gui: None,
            });
        }
        Ok(())
    }
    pub fn gui_binding(&self, id: &str) -> Option<&EnvironmentBinding> {
        self.installed
            .iter()
            .find(|record| record.release_id == id)
            .and_then(|record| record.gui.as_ref())
    }

    /// 显式升级写协议；原v1字节先独立备份，旧启动器会因schema2拒绝写入。
    pub fn upgrade_for_instances(&mut self, mutation: &WorkspaceMutation) -> Result<()> {
        self.validate()?;
        let layout = mutation.layout();
        if Self::load(&layout.root)? != *self {
            bail!("版本登记已变化，请重新读取后规划");
        }
        if self.schema_version >= 2 {
            return Ok(());
        }
        let path = layout.root.join("state/registry.json");
        layout.guard_path(&path)?;
        if path.exists() {
            let backup = layout.root.join("backups").join(format!(
                "registry-v1-{}-{}.json",
                now(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            layout.guard_path(&backup)?;
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&backup)?;
            file.write_all(&fs::read(&path)?)?;
            file.sync_all()?;
        }
        let mut upgraded = self.clone();
        upgraded.schema_version = 2;
        upgraded.store(&layout.root)?;
        *self = upgraded;
        Ok(())
    }

    /// 调用方须先按同generation验证实例；绑定切换不继承旧环境的健康结论。
    pub fn bind_gui(&mut self, id: &str, binding: EnvironmentBinding) -> Result<()> {
        if self.schema_version < 2 {
            bail!("需先显式升级版本登记协议");
        }
        binding.validate()?;
        let record = self
            .installed
            .iter_mut()
            .find(|record| record.release_id == id)
            .context("只能绑定已登记版本")?;
        record.gui = Some(binding);
        record.healthy_at = None;
        if self.previous_known_good.as_deref() == Some(id) {
            self.previous_known_good = None;
        }
        Ok(())
    }
    pub fn activate(&mut self, id: &str) -> Result<()> {
        self.assert_base_python_ready()?;
        self.validate()?;
        if !self.installed.iter().any(|i| i.release_id == id) {
            bail!("只能激活已提交的版本");
        }
        if self.current.as_deref() == Some(id) {
            return Ok(());
        }
        if let Some(current) = &self.current {
            if self
                .installed
                .iter()
                .any(|i| i.release_id == *current && i.healthy_at.is_some())
            {
                self.previous_known_good = Some(current.clone());
            }
        }
        self.current = Some(id.into());
        Ok(())
    }
    pub fn mark_healthy(&mut self, id: &str) -> Result<()> {
        self.assert_base_python_ready()?;
        if self.current.as_deref() != Some(id) {
            bail!("仅可标记本次激活并实际启动的版本");
        }
        let record = self
            .installed
            .iter_mut()
            .find(|i| i.release_id == id)
            .context("版本尚未安装登记")?;
        record.healthy_at = Some(now());
        Ok(())
    }
    pub fn rollback(&mut self, catalog: &Catalog) -> Result<String> {
        self.validate()?;
        let target = self
            .previous_known_good
            .clone()
            .context("尚无以前启动成功的可回退版本")?;
        let release = catalog.release(&target)?;
        if release.profile_schema_version != self.profile_schema_version {
            bail!("回退版本 profile schema 不兼容");
        }
        if self.current.as_deref() == Some(&target) {
            bail!("当前已是回退目标");
        }
        self.activate(&target)?;
        Ok(target)
    }
    /// 仅补回已经完整提交、带可信 receipt 的版本，不改变活动指针或健康记录。
    pub fn reconcile(&mut self, root: &Path, catalog: &Catalog) -> Result<Vec<String>> {
        self.validate()?;
        let dir = root.join("releases");
        check_chain(&dir)?;
        let mut recovered = Vec::new();
        if !dir.exists() {
            return Ok(recovered);
        }
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let id = entry.file_name().to_string_lossy().into_owned();
            if self
                .installed
                .iter()
                .any(|installed| installed.release_id == id)
            {
                // 已登记版本的真实健康状态由 core 独立探测；一版损坏不阻断其他版恢复。
                continue;
            }
            let Ok(expected) = catalog.release(&id) else {
                continue;
            };
            let candidate = (|| -> Result<()> {
                let layout = Layout::new(root, &id)?;
                layout.guard_path(&entry.path())?;
                if !entry.file_type()?.is_dir() {
                    bail!("版本路径不是普通目录");
                }
                let receipt = ReleaseReceipt::load(&entry.path())?;
                if receipt.release != *expected {
                    bail!("磁盘 receipt 与嵌入目录不一致");
                }
                for required in &expected.required_files {
                    let file = layout.app.join(required);
                    layout.guard_path(&file)?;
                    if !file.is_file() {
                        bail!("已提交版本缺少必须文件");
                    }
                }
                Ok(())
            })();
            if candidate.is_err() {
                // 损坏/未知 receipt 保持原样，不信任、不补登记，不影响其他候选。
                continue;
            }
            self.record_installed(expected)?;
            recovered.push(id);
        }
        Ok(recovered)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReleaseReceipt {
    pub schema_version: u32,
    pub release: Release,
    pub installed_at: u64,
}
impl ReleaseReceipt {
    pub fn new(release: &Release) -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            release: release.clone(),
            installed_at: now(),
        }
    }
    pub fn load(directory: &Path) -> Result<Self> {
        let path = directory.join(RECEIPT);
        check_chain(&path)?;
        let receipt: Self = read_json(&path)?;
        schema(receipt.schema_version, "receipt")?;
        receipt.release.validate()?;
        Ok(receipt)
    }
    pub fn store(&self, directory: &Path) -> Result<()> {
        schema(self.schema_version, "receipt")?;
        self.release.validate()?;
        if directory.join(RECEIPT).exists() {
            let _ = Self::load(directory)?;
        }
        write_json_atomic(&directory.join(RECEIPT), self)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Preparing,
    Verified,
    Committing,
    Committed,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Journal {
    pub schema_version: u32,
    pub release_id: String,
    pub phase: Phase,
    pub updated_at: u64,
}
impl Journal {
    pub fn new(id: &str) -> Result<Self> {
        validate_release_id(id)?;
        Ok(Self {
            schema_version: SCHEMA_VERSION,
            release_id: id.into(),
            phase: Phase::Preparing,
            updated_at: now(),
        })
    }
    pub fn store(&self, root: &Path) -> Result<()> {
        schema(self.schema_version, "journal")?;
        validate_release_id(&self.release_id)?;
        let _ = Self::load_all(root)?;
        write_json_atomic(
            &root
                .join("state")
                .join(format!("journal-{}.json", self.release_id)),
            self,
        )
    }
    pub fn load_all(root: &Path) -> Result<Vec<Self>> {
        let state = root.join("state");
        check_chain(&state)?;
        let mut journals = Vec::new();
        if !state.exists() {
            return Ok(journals);
        }
        for entry in fs::read_dir(state)? {
            let path = entry?.path();
            if path
                .file_name()
                .is_some_and(|n| n.to_string_lossy().starts_with("journal-"))
                && path.extension().is_some_and(|e| e == "json")
            {
                check_chain(&path)?;
                let journal: Self = read_json(&path)?;
                schema(journal.schema_version, "journal")?;
                validate_release_id(&journal.release_id)?;
                journals.push(journal);
            }
        }
        Ok(journals)
    }
}

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    serde_json::from_slice(&fs::read(path).with_context(|| format!("读取 {}", path.display()))?)
        .with_context(|| format!("解析 {}", path.display()))
}
/// 写入同目录临时文件并 sync，Windows MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)。
/// 失败保留旧文件；不执行 remove-old 再 rename 的非原子替换。
pub fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    if !path.is_absolute() {
        bail!("状态文件必须使用绝对路径");
    }
    check_chain(path)?;
    let parent = path.parent().context("状态文件缺少父目录")?;
    fs::create_dir_all(parent)?;
    check_chain(parent)?;
    let suffix = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(
        ".state-{}-{}-{suffix}.tmp",
        std::process::id(),
        now()
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)?;
    let data = serde_json::to_vec_pretty(value)?;
    file.write_all(&data)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    drop(file);
    let result = replace_atomic(&temp, path);
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}
pub(crate) fn write_base_json_atomic<T: Serialize>(
    root: &Path,
    transaction: &str,
    path: &Path,
    value: &T,
) -> Result<()> {
    validate_component(transaction)?;
    if !transaction.starts_with("base-python-")
        || transaction.len() > 96
        || !root.is_absolute()
        || !path.starts_with(root.join("state"))
    {
        bail!("基础Python原子写路径或事务身份不受支持");
    }
    check_chain(path)?;
    let temporary_root = root.join("backups").join(transaction).join("atomic-writes");
    check_chain(&temporary_root)?;
    fs::create_dir_all(&temporary_root)?;
    check_chain(&temporary_root)?;
    let temporary = temporary_root.join(format!(
        ".state-{}-{}-{}.tmp",
        std::process::id(),
        now(),
        NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    let bytes = serde_json::to_vec_pretty(value)?;
    file.write_all(&bytes)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    drop(file);
    // Both locations are under one workspace volume. Do not remove failed or
    // interrupted temporaries: they are evidence owned by this exact transaction.
    replace_atomic(&temporary, path)
}

/// GUI补登记/重建只在精确事务备份目录暂存，避免临时文件污染受保护state树。
pub(crate) fn write_gui_transaction_bytes(
    root: &Path,
    transaction: &str,
    path: &Path,
    bytes: &[u8],
) -> Result<()> {
    validate_component(transaction)?;
    if !root.is_absolute()
        || transaction.len() > 96
        || !(transaction.starts_with("gui-registration-")
            || transaction.starts_with("gui-rebuild-"))
        || bytes.len() > 32 * 1024 * 1024
    {
        bail!("GUI事务写身份或字节限额无效");
    }
    let relative = path.strip_prefix(root).context("GUI事务目标越出工作区")?;
    let parts: Vec<_> = relative
        .components()
        .map(|part| match part {
            Component::Normal(name) => name.to_str().context("事务路径不是UTF8"),
            _ => bail!("GUI事务路径包含跳转"),
        })
        .collect::<Result<_>>()?;
    let allowed = parts.as_slice() == ["state", "registry.json"]
        || (parts.len() == 3
            && parts[0] == "state"
            && matches!(
                parts[1],
                "instances" | "gui-registration" | "gui-rebuild" | "gui-binding-switch"
            )
            && parts[2].ends_with(".json"))
        || (parts.len() == 3
            && parts[0] == "releases"
            && parts[2] == "release.json"
            && validate_release_id(parts[1]).is_ok())
        || (parts.len() == 3 && parts[0] == "backups" && parts[1] == transaction);
    if !allowed {
        bail!("GUI事务写目标不在限定state/receipt/备份命名空间");
    }
    check_chain(path)?;
    let parent = path.parent().context("事务目标缺少父目录")?;
    fs::create_dir_all(parent)?;
    check_chain(parent)?;
    let temporary_root = root.join("backups").join(transaction).join("atomic-writes");
    check_chain(&temporary_root)?;
    fs::create_dir_all(&temporary_root)?;
    check_chain(&temporary_root)?;
    let temporary = temporary_root.join(format!(
        ".state-{}-{}-{}.tmp",
        std::process::id(),
        now(),
        NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    replace_atomic(&temporary, path)
}

pub(crate) fn write_gui_transaction_json<T: Serialize>(
    root: &Path,
    transaction: &str,
    path: &Path,
    value: &T,
) -> Result<()> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    write_gui_transaction_bytes(root, transaction, path, &bytes)
}
#[cfg(windows)]
fn replace_atomic(temp: &Path, target: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, new: *const u16, flags: u32) -> i32;
    }
    let temp: Vec<u16> = temp.as_os_str().encode_wide().chain(Some(0)).collect();
    let target: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    if unsafe { MoveFileExW(temp.as_ptr(), target.as_ptr(), 0x1 | 0x8) } == 0 {
        return Err(std::io::Error::last_os_error()).context("状态原子替换失败，原状态已保留");
    }
    Ok(())
}
#[cfg(not(windows))]
fn replace_atomic(temp: &Path, target: &Path) -> Result<()> {
    fs::rename(temp, target)?;
    File::open(target.parent().context("状态缺少父目录")?)?.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let id = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "next-trainer-model-{}-{}-{id}",
                std::process::id(),
                now()
            ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            // 删除前证明目标是本测试独立创建、位于系统临时目录下的绝对目录。
            if self.0.is_absolute()
                && self.0.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .0
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("next-trainer-model-")
            {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
    }
    #[test]
    fn explicit_instance_upgrade_preserves_v1_bytes_and_legacy_environment_path() {
        let temp = Temp::new();
        let release = Catalog::embedded().unwrap().releases[0].clone();
        let mutation = WorkspaceMutation::acquire(&temp.0, &release.id).unwrap();
        let legacy_path = mutation.layout().environment.clone();
        let mut registry = Registry::default();
        registry.record_installed(&release).unwrap();
        registry.store(&temp.0).unwrap();
        let original = fs::read(temp.0.join("state/registry.json")).unwrap();
        assert!(!String::from_utf8_lossy(&original).contains("\"gui\""));
        registry.upgrade_for_instances(&mutation).unwrap();
        assert_eq!(Registry::load(&temp.0).unwrap().schema_version, 2);
        assert_eq!(
            Layout::new(&temp.0, &release.id).unwrap().environment,
            legacy_path
        );
        let backup = fs::read_dir(temp.0.join("backups"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        assert_eq!(fs::read(backup).unwrap(), original);
        let binding = EnvironmentBinding {
            instance_id: "gui-verified-1".into(),
            storage_version: 0,
            recipe_id: "gui-cp310-win-x64-v1".into(),
            recipe_sha256: "a".repeat(64),
            generation: 1,
        };
        registry.bind_gui(&release.id, binding).unwrap();
        registry.store(&temp.0).unwrap();
        assert_eq!(
            Layout::new(&temp.0, &release.id).unwrap().environment,
            temp.0
                .join("environments")
                .join(&release.id)
                .join("instances/gui-verified-1/gui")
        );
        assert!(Registry::load(&temp.0).unwrap().installed[0]
            .healthy_at
            .is_none());
        let newer = fs::read(temp.0.join("state/registry.json")).unwrap();
        assert!(Registry::default().store(&temp.0).is_err());
        assert_eq!(fs::read(temp.0.join("state/registry.json")).unwrap(), newer);
    }

    #[test]
    fn readonly_registry_load_does_not_upgrade_or_accept_v1_instance_fields() {
        let temp = Temp::new();
        let release = Catalog::embedded().unwrap().releases[0].clone();
        let mutation = WorkspaceMutation::acquire(&temp.0, &release.id).unwrap();
        let mut registry = Registry::default();
        registry.record_installed(&release).unwrap();
        registry.store(&temp.0).unwrap();
        let path = temp.0.join("state/registry.json");
        let original = fs::read(&path).unwrap();
        assert_eq!(Registry::load(&temp.0).unwrap().schema_version, 1);
        assert_eq!(fs::read(&path).unwrap(), original);
        registry.installed[0].gui = Some(EnvironmentBinding {
            instance_id: "gui-invalid".into(),
            storage_version: 0,
            recipe_id: "gui-cp310-win-x64-v1".into(),
            recipe_sha256: "b".repeat(64),
            generation: 1,
        });
        assert!(registry.store(&temp.0).is_err());
        assert!(registry.upgrade_for_instances(&mutation).is_err());
        assert_eq!(fs::read(&path).unwrap(), original);
    }

    #[test]
    fn storage_version_preserves_legacy_binding_bytes_and_uses_explicit_short_paths() {
        let temp = Temp::new();
        let release = Catalog::embedded().unwrap().releases[0].clone();
        let _mutation = WorkspaceMutation::acquire(&temp.0, &release.id).unwrap();
        let legacy = serde_json::json!({
            "instance_id": "gui-old-one", "recipe_id": "gui-cp310-win-x64-v1",
            "recipe_sha256": "a".repeat(64), "generation": 1
        });
        let legacy_binding: EnvironmentBinding = serde_json::from_value(legacy.clone()).unwrap();
        assert_eq!(legacy_binding.storage_version, 0);
        assert_eq!(serde_json::to_value(&legacy_binding).unwrap(), legacy);
        let mut registry = Registry {
            schema_version: 2,
            ..Registry::default()
        };
        registry.record_installed(&release).unwrap();
        registry.bind_gui(&release.id, legacy_binding).unwrap();
        registry.store(&temp.0).unwrap();
        assert_eq!(
            Layout::new(&temp.0, &release.id).unwrap().environment,
            temp.0
                .join("environments")
                .join(&release.id)
                .join("instances/gui-old-one/gui")
        );
        let binding = EnvironmentBinding {
            instance_id: "g0123456789abcdef".into(),
            storage_version: 1,
            recipe_id: "gui-cp310-win-x64-v1".into(),
            recipe_sha256: "a".repeat(64),
            generation: 1,
        };
        registry.bind_gui(&release.id, binding.clone()).unwrap();
        registry.store(&temp.0).unwrap();
        assert_eq!(
            Layout::new(&temp.0, &release.id).unwrap().environment,
            temp.0.join("e/g0123456789abcdef")
        );
        let mut invalid = binding.clone();
        invalid.storage_version = 2;
        assert!(invalid.validate().is_err());
        invalid.storage_version = 1;
        invalid.instance_id = "gui-old-one".into();
        assert!(invalid.validate().is_err());
        invalid.instance_id = "g0123456789abcdeF".into();
        assert!(invalid.validate().is_err());
        let other = Catalog::embedded().unwrap().releases[1].clone();
        registry.record_installed(&other).unwrap();
        registry
            .installed
            .iter_mut()
            .find(|record| record.release_id == other.id)
            .unwrap()
            .gui = Some(binding);
        assert!(registry.validate().is_err());
    }

    #[test]
    fn embedded_catalog_has_real_distinct_main_and_dev() {
        let catalog = Catalog::embedded().unwrap();
        assert!(catalog.releases.len() >= 2);
        assert_ne!(catalog.releases[0].commit, catalog.releases[1].commit);
        assert!(catalog.release("../../outside").is_err());
    }
    #[test]
    fn unknown_catalog_and_release_schema_are_rejected() {
        let baseline = Catalog::embedded().unwrap();
        let mut catalog = baseline.clone();
        catalog.schema_version = 2;
        assert!(catalog.validate().is_err());
        let mut release = baseline.releases[0].clone();
        release.schema_version = 2;
        assert!(release.validate().is_err());
        let mut release = baseline.releases[0].clone();
        release.profile_schema_version = 2;
        assert!(release.validate().is_err());
    }
    #[test]
    fn malformed_download_and_binary_hashes_are_rejected() {
        let baseline = Catalog::embedded().unwrap().releases[0].clone();
        for invalid in [
            String::new(),
            "a".repeat(63),
            "z".repeat(64),
            "A".repeat(64),
        ] {
            for field in ["archive", "uv", "uv_exe"] {
                let mut release = baseline.clone();
                match field {
                    "archive" => release.archive.sha256 = invalid.clone(),
                    "uv" => release.uv.sha256 = invalid.clone(),
                    "uv_exe" => release.uv.exe_sha256 = invalid.clone(),
                    _ => unreachable!(),
                }
                assert!(
                    release.validate().is_err(),
                    "非法 {field} SHA256 被接受：{invalid:?}"
                );
            }
        }
    }
    #[test]
    fn release_manifest_respects_download_and_unpack_budgets() {
        let baseline = Catalog::embedded().unwrap().releases[0].clone();
        for (field, maximum) in [
            ("archive", 200_000_000),
            ("uv", 200_000_000),
            ("unpacked", 2_000_000_000),
        ] {
            let mut release = baseline.clone();
            match field {
                "archive" => release.archive.bytes = maximum,
                "uv" => release.uv.bytes = maximum,
                "unpacked" => release.archive.unpacked_bytes = maximum,
                _ => unreachable!(),
            }
            assert!(release.validate().is_ok(), "边界值应被接受：{field}");
            match field {
                "archive" => release.archive.bytes += 1,
                "uv" => release.uv.bytes += 1,
                "unpacked" => release.archive.unpacked_bytes += 1,
                _ => unreachable!(),
            }
            assert!(
                release.validate().is_err(),
                "超预算 manifest 被接受：{field}"
            );
        }
    }
    #[test]
    fn corrupt_or_unknown_registry_is_never_silently_replaced() {
        let temp = Temp::new();
        fs::create_dir(temp.0.join("state")).unwrap();
        let path = temp.0.join("state/registry.json");
        fs::write(&path, b"{broken").unwrap();
        assert!(Registry::load(&temp.0).is_err());
        assert!(Registry::default().store(&temp.0).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"{broken");
        let unknown = Registry {
            schema_version: 999,
            ..Registry::default()
        };
        fs::write(&path, serde_json::to_vec(&unknown).unwrap()).unwrap();
        assert!(Registry::load(&temp.0).is_err());
    }
    #[test]
    fn paths_reject_escape_and_windows_reserved_names() {
        let catalog = Catalog::embedded().unwrap();
        let id = &catalog.releases[0].id;
        let temp = Temp::new();
        let layout = Layout::new(&temp.0, id).unwrap();
        assert!(layout.guard_path(&temp.0.join("../escape")).is_err());
        assert!(layout.guard_path(&temp.0.join("NUL.txt")).is_err());
        assert!(layout.guard_path(&temp.0.join("COM1")).is_err());
        assert!(layout.guard_path(&temp.0.join("stream:ads")).is_err());
        assert!(Layout::new(&temp.0, "dev-../escape").is_err());
    }
    #[test]
    fn existing_reparse_directory_is_rejected() {
        let temp = Temp::new();
        let outside = Temp::new();
        let catalog = Catalog::embedded().unwrap();
        let layout = Layout::new(&temp.0, &catalog.releases[0].id).unwrap();
        let link = temp.0.join("cache");
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let status = std::process::Command::new("cmd.exe")
                .args(["/c", "mklink", "/J"])
                .arg(&link)
                .arg(&outside.0)
                .creation_flags(0x08000000)
                .status()
                .unwrap();
            assert!(status.success(), "创建无管理员要求的本地junction测试夹具");
        }
        #[cfg(unix)]
        std::os::unix::fs::symlink(&outside.0, &link).unwrap();
        assert!(layout.guard_path(&link.join("asset.zip")).is_err());
        assert!(layout.ensure_dir(&link.join("writes")).is_err());
        assert!(!outside.0.join("writes").exists());
        #[cfg(windows)]
        fs::remove_dir(&link).unwrap();
        #[cfg(unix)]
        fs::remove_file(&link).unwrap();
    }
    #[test]
    fn registry_replace_is_atomic_and_rollback_requires_healthy_compatible_target() {
        let temp = Temp::new();
        let catalog = Catalog::embedded().unwrap();
        let first = &catalog.releases[0];
        let second = &catalog.releases[1];
        let layout = Layout::new(&temp.0, &first.id).unwrap();
        let _lock = layout.prepare_workspace().unwrap();
        let mut registry = Registry::load(&temp.0).unwrap();
        registry.record_installed(first).unwrap();
        registry.record_installed(second).unwrap();
        registry.activate(&first.id).unwrap();
        assert!(registry.rollback(&catalog).is_err());
        registry.mark_healthy(&first.id).unwrap();
        registry.store(&temp.0).unwrap();
        registry.activate(&second.id).unwrap();
        registry.store(&temp.0).unwrap();
        assert_eq!(
            Registry::load(&temp.0).unwrap().current.as_deref(),
            Some(second.id.as_str())
        );
        assert_eq!(registry.rollback(&catalog).unwrap(), first.id);
        registry.store(&temp.0).unwrap();
        let mut bad = catalog.clone();
        bad.releases[0].profile_schema_version = 2;
        registry.activate(&second.id).unwrap();
        assert!(registry.rollback(&bad).is_err());
        assert!(fs::read_dir(temp.0.join("state")).unwrap().all(|e| !e
            .unwrap()
            .file_name()
            .to_string_lossy()
            .ends_with(".tmp")));
    }
    #[test]
    fn missing_registry_reconciles_receipt_without_activating() {
        let temp = Temp::new();
        let catalog = Catalog::embedded().unwrap();
        let release = &catalog.releases[0];
        let layout = Layout::new(&temp.0, &release.id).unwrap();
        let _lock = layout.prepare_workspace().unwrap();
        layout.ensure_dir(&layout.app).unwrap();
        for required in &release.required_files {
            let path = layout.app.join(required);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, b"test").unwrap();
        }
        ReleaseReceipt::new(release)
            .store(&layout.release_dir)
            .unwrap();
        let mut registry = Registry::load(&temp.0).unwrap();
        assert_eq!(
            registry.reconcile(&temp.0, &catalog).unwrap(),
            vec![release.id.clone()]
        );
        assert!(registry.current.is_none());
        assert!(registry.installed[0].healthy_at.is_none());
    }
    #[test]
    fn interrupted_journal_and_unknown_profile_are_visible() {
        let temp = Temp::new();
        let catalog = Catalog::embedded().unwrap();
        let layout = Layout::new(&temp.0, &catalog.releases[0].id).unwrap();
        let lock = layout.prepare_workspace().unwrap();
        Journal::new(&catalog.releases[0].id)
            .unwrap()
            .store(&temp.0)
            .unwrap();
        assert_eq!(
            Journal::load_all(&temp.0).unwrap()[0].phase,
            Phase::Preparing
        );
        drop(lock);
        fs::write(
            layout.profile.join("profile.json"),
            b"{\"schema_version\":99,\"id\":\"default\"}",
        )
        .unwrap();
        assert!(layout.prepare_workspace().is_err());
    }
}
