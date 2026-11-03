//! 精确legacy发布的独立离线环境事务；不改原journal、current或健康登记。
use crate::{
    gui_registration_integrity::{self, TrustedEnvironment},
    instances,
    model::{self, Layout, Release, WorkspaceMutation},
    operations::{CancelToken, OperationHandle, OperationPhase},
    query_tasks::{QueryObserver, QueryProgress, QueryStage},
    recipe::GuiRecipe,
    scan_observation,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    process::Command,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};

const RELEASE: &str = "main-0785419e7dc1a3058bd8710a9aa933fec0aabdee";
const COMMIT: &str = "0785419e7dc1a3058bd8710a9aa933fec0aabdee";
const INPUT_SHA: &str = "8dc07965d650ee22c0f4f0affa01a97f01550795f79dfed4f3bb780b9c3c3ff6";
const RESOURCE_SHA: &str = "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba";
const OWNER: &str = ".next-trainer-legacy-repair-owner.json";
const DIRECTORY: &str = "state/legacy-environment-repair";
const MAX_TREE: u64 = 1024 * 1024 * 1024;
const MAX_NODES: usize = 100_000;
const MAX_RECORD: usize = 32 * 1024 * 1024;
const MAX_INTENT: usize = 1024 * 1024;
// 固定recipe中的tool_uv.bytes是下载ZIP长度；已核固定uv.exe的展开长度另行约束。
// 长度只限制读取资源，信任仍由同一内置exe_sha256授予。
const TRUSTED_UV_EXE_BYTES: u64 = 67_598_848;
const TIMEOUT: Duration = Duration::from_secs(360);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Identity {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Tree {
    nodes: BTreeMap<PathBuf, Option<Identity>>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct LegacyEnvironmentRepairPlan {
    schema_version: u32,
    root: PathBuf,
    release_id: String,
    pub journal_sha256: String,
    resource_recipe_sha256: String,
    requirements_sha256: String,
    protections_sha256: String,
    original_tree_sha256: String,
    resources_sha256: String,
    pub plan_sha256: String,
    pub ready: bool,
    pub blockers: Vec<String>,
    operation: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Owner {
    schema_version: u32,
    root: PathBuf,
    release_id: String,
    transaction: String,
    plan_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Worker {
    job_name: String,
    session_id: u32,
    status: String,
    pid: Option<u32>,
}
type Host = super::ControlledHostIdentity;
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    root: PathBuf,
    release_id: String,
    transaction: String,
    status: String,
    plan: LegacyEnvironmentRepairPlan,
    owner: Owner,
    workers: Vec<Worker>,
    proof: Option<TrustedEnvironment>,
    completed_tree_sha256: Option<String>,
    failure: Option<String>,
    host: Host,
    restart_required: bool,
}
#[derive(Serialize)]
struct Protection {
    controls: Vec<u8>,
    engines: String,
    profiles: instances::ProfilesSummary,
    other_controls: BTreeMap<PathBuf, ControlRecord>,
}
#[derive(Serialize)]
struct ControlRecord {
    kind: &'static str,
    bytes: Option<Vec<u8>>,
}

#[derive(Serialize)]
struct ProtectionV2 {
    schema_version: u32,
    controls:
        BTreeMap<PathBuf, Option<super::legacy_install_recovery::EnvironmentRepairControlIdentity>>,
    engines: String,
    profiles: instances::ProfilesSummary,
    other_controls: BTreeMap<PathBuf, ControlIdentityRecord>,
}
#[derive(Serialize)]
struct ControlIdentityRecord {
    kind: &'static str,
    identity: Option<Identity>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct EngineSnapshotEntry {
    area: String,
    path: String,
    existed: bool,
    #[serde(default)]
    bytes: Option<u64>,
    #[serde(default)]
    sha256: Option<String>,
}

fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn sha_valid(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn check(cancel: &CancelToken) -> Result<()> {
    cancel.check()?;
    scan_observation::check()
}
fn read(layout: &Layout, path: &Path, limit: usize, cancel: &CancelToken) -> Result<Vec<u8>> {
    check(cancel)?;
    layout.guard_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() || before.len() > limit as u64 {
        bail!("旧环境修复记录不是受限普通文件：{}", path.display());
    }
    let mut file = File::open(path)?;
    let mut data = Vec::new();
    let mut block = [0; 65_536];
    loop {
        check(cancel)?;
        let n = file.read(&mut block)?;
        if n == 0 {
            break;
        }
        if data.len().saturating_add(n) > limit {
            bail!("旧环境修复读取超限");
        }
        data.extend_from_slice(&block[..n]);
        scan_observation::checkpoint(QueryStage::Environment, 0, n as u64)?;
    }
    check(cancel)?;
    layout.guard_path(path)?;
    if data.len() as u64 != before.len() || fs::symlink_metadata(path)?.len() != before.len() {
        bail!("读取期间文件长度变化");
    }
    Ok(data)
}
fn digest(layout: &Layout, path: &Path, maximum: u64, cancel: &CancelToken) -> Result<Identity> {
    check(cancel)?;
    layout.guard_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() || before.len() > maximum {
        bail!("旧环境修复文件类型或长度不受支持：{}", path.display());
    }
    let mut file = File::open(path)?;
    let opened = file.metadata()?;
    let mut sha = Sha256::new();
    let mut bytes = 0u64;
    let mut block = [0; 65_536];
    loop {
        check(cancel)?;
        let n = file.read(&mut block)?;
        if n == 0 {
            break;
        }
        bytes = bytes.checked_add(n as u64).context("文件长度溢出")?;
        if bytes > maximum {
            bail!("文件读取期间超限");
        }
        sha.update(&block[..n]);
        scan_observation::checkpoint(QueryStage::Environment, 0, n as u64)?;
    }
    check(cancel)?;
    layout.guard_path(path)?;
    let after = fs::symlink_metadata(path)?;
    if bytes != before.len()
        || bytes != after.len()
        || bytes != opened.len()
        || before.modified().ok() != after.modified().ok()
    {
        bail!("文件读取期间发生变化");
    }
    Ok(Identity {
        bytes,
        sha256: format!("{:x}", sha.finalize()),
    })
}
fn verify_uv_identity(
    layout: &Layout,
    expected_sha: &str,
    cancel: &CancelToken,
) -> Result<Identity> {
    let identity = digest(
        layout,
        &super::uv(&layout.root),
        TRUSTED_UV_EXE_BYTES,
        cancel,
    )?;
    if identity.bytes != TRUSTED_UV_EXE_BYTES || identity.sha256 != expected_sha {
        bail!("受管uv长度或摘要不符");
    }
    Ok(identity)
}
fn exists(layout: &Layout, path: &Path) -> Result<bool> {
    layout.guard_path(path)?;
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e.into()),
    }
}
fn tree(layout: &Layout, base: &Path, cancel: &CancelToken) -> Result<Tree> {
    #[derive(Default)]
    struct WalkState {
        usage: u64,
        nodes: BTreeMap<PathBuf, Option<Identity>>,
        aliases: BTreeSet<String>,
    }
    fn walk(
        layout: &Layout,
        base: &Path,
        path: &Path,
        depth: usize,
        state: &mut WalkState,
        cancel: &CancelToken,
    ) -> Result<()> {
        check(cancel)?;
        layout.guard_path(path)?;
        if depth > 64 || state.nodes.len() >= MAX_NODES {
            bail!("旧环境树深度或节点超限");
        }
        let relative = path.strip_prefix(base)?.to_owned();
        if !state
            .aliases
            .insert(relative.to_string_lossy().replace('\\', "/").to_lowercase())
        {
            bail!("旧环境树含大小写别名");
        }
        let meta = fs::symlink_metadata(path)?;
        if meta.is_dir() {
            state.nodes.insert(relative, None);
            let mut children = Vec::new();
            for entry in fs::read_dir(path)? {
                check(cancel)?;
                if children.len() >= MAX_NODES {
                    bail!("环境目录条目超限");
                }
                children.push(entry?.path());
            }
            children.sort();
            for child in children {
                walk(layout, base, &child, depth + 1, state, cancel)?;
            }
        } else {
            let id = digest(layout, path, MAX_TREE, cancel)?;
            state.usage = state.usage.checked_add(id.bytes).context("环境长度溢出")?;
            if state.usage > MAX_TREE {
                bail!("环境树超过1GiB修复界限");
            }
            state.nodes.insert(relative, Some(id));
        }
        Ok(())
    }
    let mut state = WalkState::default();
    if exists(layout, base)? {
        walk(layout, base, base, 0, &mut state, cancel)?;
    }
    Ok(Tree { nodes: state.nodes })
}
fn relative(s: &str) -> Result<PathBuf> {
    if s.is_empty() || s.contains('\\') || s.len() > 4096 {
        bail!("资源路径格式无效");
    }
    let p = Path::new(s);
    for part in p.components() {
        match part {
            Component::Normal(s) => {
                model::validate_component(s.to_str().context("资源路径非UTF8")?)?
            }
            _ => bail!("资源路径逃逸"),
        }
    }
    Ok(p.to_owned())
}
fn supported(release: &Release) -> Result<()> {
    release.validate()?;
    if release.id != RELEASE
        || release.commit != COMMIT
        || model::Catalog::embedded()?.release(RELEASE)? != release
    {
        bail!("仅支持精确内置legacy main环境修复");
    }
    Ok(())
}
// 不修改v1编码或拒绝规则；已持久的schema1事务依赖其精确摘要。
fn protection_v1(
    layout: &Layout,
    release: &Release,
    sha: &str,
    own: Option<&str>,
    cancel: &CancelToken,
) -> Result<Vec<u8>> {
    let controls = super::legacy_install_recovery::capture_for_environment_repair(
        layout, release, sha, own, cancel,
    )?;
    let mut other_controls = BTreeMap::new();
    // 只扫描小型权威控制命名空间；路径集合纳入摘要，新增记录不能漏过。
    let mut usage = 0u64;
    fn collect(
        layout: &Layout,
        path: &Path,
        depth: usize,
        usage: &mut u64,
        records: &mut BTreeMap<PathBuf, ControlRecord>,
        cancel: &CancelToken,
    ) -> Result<()> {
        check(cancel)?;
        layout.guard_path(path)?;
        if depth > 16 || records.len() >= 256 {
            bail!("保护控制目录深度或记录数量超限");
        }
        let key = path.strip_prefix(&layout.root)?.to_owned();
        if !exists(layout, path)? {
            records.insert(
                key,
                ControlRecord {
                    kind: "missing",
                    bytes: None,
                },
            );
            return Ok(());
        }
        let meta = fs::symlink_metadata(path)?;
        if meta.is_dir() {
            records.insert(
                key,
                ControlRecord {
                    kind: "directory",
                    bytes: None,
                },
            );
            let mut entries = Vec::new();
            for entry in fs::read_dir(path)? {
                check(cancel)?;
                if entries.len() >= 256 {
                    bail!("保护控制目录条目超限");
                }
                entries.push(entry?.path());
            }
            entries.sort();
            for entry in entries {
                collect(layout, &entry, depth + 1, usage, records, cancel)?;
            }
        } else {
            if path.extension().is_none_or(|s| s != "json") {
                bail!("权威控制目录含未知非JSON文件");
            }
            *usage = usage.checked_add(meta.len()).context("保护控制长度溢出")?;
            if *usage > 64 * 1024 * 1024 {
                bail!("保护控制原文总长度超限");
            }
            let raw = read(layout, path, MAX_RECORD, cancel)?;
            let value: serde_json::Value = serde_json::from_slice(&raw)?;
            if !value.is_object() {
                bail!("保护控制JSON不是对象");
            }
            records.insert(
                key,
                ControlRecord {
                    kind: "file",
                    bytes: Some(raw),
                },
            );
        }
        Ok(())
    }
    for name in ["state/instances", "state/engines", "state/gui-instances"] {
        let base = layout.root.join(name);
        collect(layout, &base, 0, &mut usage, &mut other_controls, cancel)?;
    }
    check(cancel)?;
    let engines = instances::engine_control_digest(layout)?;
    check(cancel)?;
    let bytes = serde_json::to_vec(&Protection {
        controls,
        engines,
        profiles: instances::summarize_profiles(layout, cancel)?,
        other_controls,
    })?;
    if bytes.len() > MAX_RECORD {
        bail!("保护快照序列化超过32MiB上限");
    }
    Ok(bytes)
}

fn hex_id(value: &str, prefix: &str, digits: usize) -> bool {
    value.strip_prefix(prefix).is_some_and(|tail| {
        tail.len() == digits
            && tail
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

fn control_parts(path: &Path) -> Result<Vec<&str>> {
    path.components()
        .map(|part| match part {
            Component::Normal(name) => {
                let name = name.to_str().context("保护控制路径不是UTF8")?;
                model::validate_component(name)?;
                Ok(name)
            }
            _ => bail!("保护控制路径含跳转或盘符"),
        })
        .collect()
}

fn snapshot_relative(value: &str) -> Result<PathBuf> {
    if value.is_empty() || value.contains(['\\', ':']) {
        bail!("引擎快照相对路径不支持");
    }
    for part in value.split('/') {
        model::validate_component(part)?;
    }
    Ok(PathBuf::from(value))
}

#[derive(Clone, Copy)]
enum ProtectedFile {
    Object,
    Snapshot,
    Opaque,
}

#[derive(Default)]
struct ControlCollectorV2 {
    usage: u64,
    records: BTreeMap<PathBuf, ControlIdentityRecord>,
    manifests: BTreeSet<PathBuf>,
    payloads: BTreeMap<PathBuf, Identity>,
}

impl ControlCollectorV2 {
    /// 固定控制位置继续要求JSON对象；只有产品快照清单允许数组。
    /// 日志和快照原件以精确位置识别，不全局放宽扩展名。
    fn classify(&self, key: &Path, directory: bool) -> Result<ProtectedFile> {
        let p = control_parts(key)?;
        let is_json_component = |name: &str| {
            name.strip_suffix(".json")
                .is_some_and(|id| model::validate_component(id).is_ok())
        };
        if matches!(p.as_slice(), ["state", "instances" | "gui-instances"]) && directory {
            return Ok(ProtectedFile::Object);
        }
        if matches!(p.as_slice(), ["state", "instances" | "gui-instances", name] if is_json_component(name))
            && !directory
        {
            return Ok(ProtectedFile::Object);
        }
        if p.len() < 2 || p[0] != "state" || p[1] != "engines" {
            bail!("未知保护控制位置：{}", key.display());
        }
        if p.len() == 2 && directory {
            return Ok(ProtectedFile::Object);
        }
        if p.len() < 3 {
            bail!("引擎保护控制必须为目录");
        }
        model::validate_release_id(p[2])?;
        if p.len() == 3 && directory {
            return Ok(ProtectedFile::Object);
        }
        if p.len() < 4 || !matches!(p[3], "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth") {
            bail!("未知引擎保护控制命名空间");
        }
        let rest = &p[4..];
        let valid = match rest {
            [] => directory,
            ["state.json"] => !directory,
            ["instances" | "operations" | "probes"] => directory,
            ["instances", id] => directory && hex_id(id, "t", 15),
            ["instances", id, generation] => {
                !directory
                    && hex_id(id, "t", 15)
                    && generation.strip_suffix(".json").is_some_and(|value| {
                        value
                            .parse::<u64>()
                            .is_ok_and(|n| n > 0 && n.to_string() == value)
                    })
            }
            ["operations", id] => directory && hex_id(id, "op-", 32),
            ["probes", id] => directory && hex_id(id, "", 32),
            ["operations", id, name] if hex_id(id, "op-", 32) => {
                if !directory {
                    match *name {
                        "snapshot.json" => return Ok(ProtectedFile::Snapshot),
                        "commands.jsonl" | "stdout.log" | "stderr.log" => {
                            return Ok(ProtectedFile::Opaque);
                        }
                        "plan.json" | "result.json" | "old-binding.json" | "baseline.json"
                        | "recovery.json" => true,
                        _ => false,
                    }
                } else {
                    *name == "snapshot"
                        && self
                            .manifests
                            .contains(&key.with_file_name("snapshot.json"))
                }
            }
            ["probes", id, name] if hex_id(id, "", 32) && !directory => match *name {
                "result.json" => true,
                "commands.jsonl" | "stdout.log" | "stderr.log" => {
                    return Ok(ProtectedFile::Opaque);
                }
                _ => false,
            },
            ["operations", id, "snapshot", ..] if hex_id(id, "op-", 32) => {
                if directory {
                    self.payloads
                        .keys()
                        .any(|path| path.starts_with(key) && path != key)
                } else if self.payloads.contains_key(key) {
                    return Ok(ProtectedFile::Opaque);
                } else {
                    false
                }
            }
            _ => false,
        };
        if !valid {
            bail!("未知保护控制文件或目录：{}", key.display());
        }
        Ok(ProtectedFile::Object)
    }

    fn manifest(&mut self, key: &Path, raw: &[u8], cancel: &CancelToken) -> Result<()> {
        let entries: Vec<EngineSnapshotEntry> = serde_json::from_slice(raw)?;
        if entries.len() > 256 {
            bail!("引擎快照清单条目超限");
        }
        let root = key.parent().context("快照清单无父目录")?.join("snapshot");
        let mut aliases = BTreeSet::new();
        for item in entries {
            check(cancel)?;
            if !matches!(item.area.as_str(), "environment" | "source") {
                bail!("引擎快照区域不支持");
            }
            let path = root.join(&item.area).join(snapshot_relative(&item.path)?);
            if !aliases.insert(path.to_string_lossy().to_lowercase()) {
                bail!("引擎快照清单含重复或别名路径");
            }
            match (item.existed, item.bytes, item.sha256) {
                (true, Some(bytes), Some(sha256))
                    if bytes <= MAX_RECORD as u64 && sha_valid(&sha256) =>
                {
                    self.payloads.insert(path, Identity { bytes, sha256 });
                }
                (false, None, None) => {}
                _ => bail!("引擎快照条目长度或摘要不支持"),
            }
        }
        self.manifests.insert(key.to_owned());
        Ok(())
    }

    fn collect(
        &mut self,
        layout: &Layout,
        path: &Path,
        depth: usize,
        cancel: &CancelToken,
    ) -> Result<()> {
        check(cancel)?;
        layout.guard_path(path)?;
        if depth > 16 || self.records.len() >= 256 {
            bail!("保护控制目录深度或记录数量超限");
        }
        let key = path.strip_prefix(&layout.root)?.to_owned();
        if !exists(layout, path)? {
            self.classify(&key, true)?;
            self.records.insert(
                key,
                ControlIdentityRecord {
                    kind: "missing",
                    identity: None,
                },
            );
            return Ok(());
        }
        let meta = fs::symlink_metadata(path)?;
        let class = self.classify(&key, meta.is_dir())?;
        if meta.is_dir() {
            self.records.insert(
                key,
                ControlIdentityRecord {
                    kind: "directory",
                    identity: None,
                },
            );
            let mut entries = Vec::new();
            for entry in fs::read_dir(path)? {
                check(cancel)?;
                if entries.len() >= 256 {
                    bail!("保护控制目录条目超限");
                }
                entries.push(entry?.path());
            }
            // 先验证manifest，后扫描它声明的原始payload，避免依赖目录枚举顺序。
            entries.sort_by(|a, b| {
                (a.file_name().is_none_or(|name| name != "snapshot.json"), a)
                    .cmp(&(b.file_name().is_none_or(|name| name != "snapshot.json"), b))
            });
            for entry in entries {
                self.collect(layout, &entry, depth + 1, cancel)?;
            }
        } else {
            let remaining = (64 * 1024 * 1024u64).saturating_sub(self.usage);
            let raw = read(layout, path, MAX_RECORD.min(remaining as usize), cancel)?;
            self.usage = self
                .usage
                .checked_add(raw.len() as u64)
                .context("保护控制长度溢出")?;
            match class {
                ProtectedFile::Object => {
                    if !serde_json::from_slice::<serde_json::Value>(&raw)?.is_object() {
                        bail!("保护控制JSON不是对象");
                    }
                }
                ProtectedFile::Snapshot => self.manifest(&key, &raw, cancel)?,
                ProtectedFile::Opaque => {}
            }
            let identity = Identity {
                bytes: raw.len() as u64,
                sha256: hash(&raw),
            };
            if self
                .payloads
                .get(&key)
                .is_some_and(|expected| expected != &identity)
            {
                bail!("引擎快照原件长度或摘要不符");
            }
            self.records.insert(
                key,
                ControlIdentityRecord {
                    kind: "file",
                    identity: Some(identity),
                },
            );
        }
        Ok(())
    }

    fn capture(
        layout: &Layout,
        cancel: &CancelToken,
    ) -> Result<BTreeMap<PathBuf, ControlIdentityRecord>> {
        let mut value = Self::default();
        for name in ["state/instances", "state/engines", "state/gui-instances"] {
            value.collect(layout, &layout.root.join(name), 0, cancel)?;
        }
        for (path, expected) in &value.payloads {
            check(cancel)?;
            if value
                .records
                .get(path)
                .and_then(|record| record.identity.as_ref())
                != Some(expected)
            {
                bail!("引擎快照清单原件缺失或不符");
            }
        }
        Ok(value.records)
    }
}

fn protection(
    layout: &Layout,
    release: &Release,
    sha: &str,
    own: Option<&str>,
    version: u32,
    cancel: &CancelToken,
) -> Result<Vec<u8>> {
    match version {
        1 => protection_v1(layout, release, sha, own, cancel),
        2 => {
            let controls =
                super::legacy_install_recovery::capture_identities_for_environment_repair(
                    layout, release, sha, own, cancel,
                )?;
            let other_controls = ControlCollectorV2::capture(layout, cancel)?;
            check(cancel)?;
            let engines = instances::engine_control_digest(layout)?;
            check(cancel)?;
            let profiles = instances::summarize_profiles(layout, cancel)?;
            let raw = serde_json::to_vec(&ProtectionV2 {
                schema_version: 2,
                controls,
                engines,
                profiles,
                other_controls,
            })?;
            if raw.len() > MAX_RECORD {
                bail!("保护快照序列化超过32MiB上限");
            }
            check(cancel)?;
            Ok(raw)
        }
        _ => bail!("独立修复保护格式版本不支持"),
    }
}
fn notify(observer: Option<&QueryObserver>, stage: QueryStage, message: &str) -> Result<()> {
    if let Some(o) = observer {
        o.check()?;
        o.progress(
            stage,
            QueryProgress {
                message: message.into(),
                ..Default::default()
            },
        )?;
    }
    Ok(())
}
fn resources(
    layout: &Layout,
    release: &Release,
    cancel: &CancelToken,
    observer: Option<&QueryObserver>,
) -> Result<String> {
    supported(release)?;
    let recipe = GuiRecipe::embedded()?;
    if recipe.requirements.input_sha256 != INPUT_SHA
        || recipe.requirements.input_bytes != 1609
        || hash(include_bytes!("../../catalog/gui-cp310-win-x64-v1.json")) != RESOURCE_SHA
    {
        bail!("离线原始资源输入身份不符");
    }
    notify(
        observer,
        QueryStage::Source,
        "正在核验旧版本固定源码归档与依赖输入",
    )?;
    let archive = layout
        .root
        .join("cache")
        .join(format!("{}.zip", release.archive.sha256));
    let archive_id = digest(layout, &archive, release.archive.bytes, cancel)?;
    if archive_id.bytes != release.archive.bytes || archive_id.sha256 != release.archive.sha256 {
        bail!("legacy固定源码归档缺失或摘要错误");
    }
    let mut zip = zip::ZipArchive::new(File::open(&archive)?)?;
    if zip.len() > MAX_NODES {
        bail!("源码归档条目超限");
    }
    let expected = format!("lora-scripts-next-{COMMIT}/requirements.txt");
    let mut matches = 0;
    for index in 0..zip.len() {
        check(cancel)?;
        let mut entry = zip.by_index(index)?;
        if entry.name() == expected {
            matches += 1;
            if entry.size() != 1609 || entry.is_dir() {
                bail!("旧requirements归档身份无效");
            }
            let mut bytes = Vec::new();
            entry.by_ref().take(1610).read_to_end(&mut bytes)?;
            if bytes.len() != 1609
                || hash(&bytes) != INPUT_SHA
                || bytes != read(layout, &layout.app.join("requirements.txt"), 1609, cancel)?
            {
                bail!("旧requirements与可信归档输入不一致");
            }
        }
    }
    if matches != 1 {
        bail!("旧requirements归档条目缺失或重复");
    }
    notify(observer, QueryStage::Python, "正在核验完整受管Python")?;
    let python = crate::python_integrity::verify_controlled(layout, cancel)?;
    let python_id = digest(layout, &python, MAX_TREE, cancel)?;
    let uv_id = verify_uv_identity(layout, &recipe.tool_uv.exe_sha256, cancel)?;
    if uv_id.sha256 != release.uv.exe_sha256 {
        bail!("受管uv摘要不符");
    }
    let mut identities = Vec::new();
    let mut unpacked = 0u64;
    let mut entries = 0usize;
    notify(
        observer,
        QueryStage::Environment,
        "正在核验81份离线原始依赖与解压上界",
    )?;
    for asset in &recipe.wheels {
        check(cancel)?;
        let path = layout.root.join("cache/wheelhouse").join(&asset.filename);
        let id = digest(layout, &path, 512 * 1024 * 1024, cancel)?;
        if id.bytes != asset.bytes || id.sha256 != asset.sha256 {
            bail!("离线原始wheel缺失或摘要不符：{}", asset.filename);
        }
        let mut wheel = zip::ZipArchive::new(File::open(&path)?)?;
        let mut aliases = BTreeSet::new();
        for i in 0..wheel.len() {
            check(cancel)?;
            let entry = wheel.by_index(i)?;
            let path = relative(entry.name().trim_end_matches('/'))?;
            if !aliases.insert(path.to_string_lossy().to_lowercase()) {
                bail!("wheel含重复路径");
            }
            if entry.unix_mode().is_some_and(|m| m & 0o170000 == 0o120000) {
                bail!("wheel含符号链接");
            }
            unpacked = unpacked
                .checked_add(entry.size())
                .context("wheel解压长度溢出")?;
            entries = entries.checked_add(1).context("wheel节点溢出")?;
            if unpacked > MAX_TREE || entries > MAX_NODES {
                bail!("离线依赖解压闭包超限");
            }
        }
        identities.push((asset.filename.clone(), id));
    }
    let upper = gui_registration_integrity::legacy_resource_upper_bound(&layout.environment)?;
    // 固定安装索引逐项展开originals、uv/解释器模板、入口、精确RECORD路径及受限元数据。
    // wheel原始ZIP自身也独立受解压界限约束，不把压缩378MB当作环境长度。
    if upper.bytes > MAX_TREE || upper.nodes > MAX_NODES {
        bail!("可信离线资源与受限生成文件上界超过环境修复界限");
    }
    Ok(hash(&serde_json::to_vec(&(
        archive_id,
        python_id,
        uv_id,
        identities,
        unpacked,
        entries,
        upper,
        hash(recipe.lock().as_bytes()),
    ))?))
}
fn make_plan(
    layout: &Layout,
    release: &Release,
    sha: &str,
    own: Option<&str>,
    cancel: &CancelToken,
    observer: Option<&QueryObserver>,
) -> Result<LegacyEnvironmentRepairPlan> {
    supported(release)?;
    if !sha_valid(sha) {
        bail!("原安装事务摘要无效");
    }
    let protections = protection(layout, release, sha, own, 2, cancel)?;
    super::verify_source_controlled(layout, release, cancel)?;
    let original = tree(layout, &layout.environment, cancel)?;
    if original.nodes.is_empty() {
        bail!("原legacy环境缺失，拒绝把修复当首次安装");
    }
    let mut plan = LegacyEnvironmentRepairPlan {
        schema_version: 2,
        root: layout.root.clone(),
        release_id: release.id.clone(),
        journal_sha256: sha.into(),
        resource_recipe_sha256: RESOURCE_SHA.into(),
        requirements_sha256: INPUT_SHA.into(),
        protections_sha256: hash(&protections),
        original_tree_sha256: hash(&serde_json::to_vec(&original)?),
        resources_sha256: resources(layout, release, cancel, observer)?,
        plan_sha256: String::new(),
        ready: true,
        blockers: vec![],
        operation: "independent_legacy_environment_repair".into(),
    };
    plan.plan_sha256 = hash(&serde_json::to_vec(&plan)?);
    check(cancel)?;
    Ok(plan)
}
pub(crate) fn plan_controlled(
    root: &Path,
    release: &Release,
    journal_sha: &str,
    cancel: &CancelToken,
    observer: Option<&QueryObserver>,
) -> Result<LegacyEnvironmentRepairPlan> {
    let layout = Layout::new(root, &release.id)?;
    make_plan(&layout, release, journal_sha, None, cancel, observer)
}
fn transaction_path(layout: &Layout, transaction: &str) -> Result<PathBuf> {
    model::validate_component(transaction)?;
    Ok(layout
        .root
        .join(DIRECTORY)
        .join(format!("{transaction}.json")))
}
fn backup(layout: &Layout, transaction: &str) -> Result<PathBuf> {
    model::validate_component(transaction)?;
    Ok(layout
        .root
        .join("backups/legacy-environment-repair")
        .join(transaction))
}
fn write_new(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    if bytes.len() > MAX_RECORD {
        bail!("修复备份记录超过32MiB上限");
    }
    layout.guard_path(path)?;
    let mut f = OpenOptions::new().write(true).create_new(true).open(path)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    Ok(())
}
fn store(layout: &Layout, intent: &Intent) -> Result<()> {
    // model::write_json_atomic使用pretty JSON并追加换行；按实际落盘编码限长。
    let raw = serde_json::to_vec_pretty(intent)?;
    if raw
        .len()
        .checked_add(1)
        .is_none_or(|bytes| bytes > MAX_INTENT)
    {
        bail!("独立修复intent超限");
    }
    let path = transaction_path(layout, &intent.transaction)?;
    layout.guard_path(&path)?;
    model::write_json_atomic(&path, intent)
}
fn terminal(status: &str) -> bool {
    matches!(status, "succeeded" | "rolled_back" | "aborted")
}
fn validate_intent(layout: &Layout, intent: &Intent) -> Result<()> {
    let mut plan = intent.plan.clone();
    let plan_sha = std::mem::take(&mut plan.plan_sha256);
    if intent.schema_version != 1
        || !matches!(plan.schema_version, 1 | 2)
        || intent.root != layout.root
        || intent.release_id != RELEASE
        || plan.root != layout.root
        || plan.release_id != RELEASE
        || !plan.ready
        || !plan.blockers.is_empty()
        || plan.resource_recipe_sha256 != RESOURCE_SHA
        || plan.requirements_sha256 != INPUT_SHA
        || plan.operation != "independent_legacy_environment_repair"
        || [
            &plan.journal_sha256,
            &plan.protections_sha256,
            &plan.original_tree_sha256,
            &plan.resources_sha256,
        ]
        .iter()
        .any(|s| !sha_valid(s))
        || plan_sha != hash(&serde_json::to_vec(&plan)?)
        || intent.owner.schema_version != 1
        || intent.owner.root != layout.root
        || intent.owner.release_id != RELEASE
        || intent.owner.transaction != intent.transaction
        || intent.owner.plan_sha256 != plan_sha
        || intent.workers.len() > 8
        || intent.host.pid == 0
        || intent.host.creation_time == 0
        || !matches!(
            intent.status.as_str(),
            "prepared"
                | "saving_original"
                | "original_saved"
                | "reserving_target"
                | "building"
                | "verifying"
                | "committing"
                | "restoring"
                | "needs_attention"
                | "succeeded"
                | "rolled_back"
                | "aborted"
        )
    {
        bail!("独立旧环境修复事务身份不符");
    }
    model::validate_component(&intent.transaction)?;
    if intent
        .transaction
        .strip_prefix("legacy-")
        .is_none_or(|s| !sha_valid(s))
    {
        bail!("修复事务随机身份无效");
    }
    let mut names = BTreeSet::new();
    for worker in &intent.workers {
        super::Job::validate_legacy_repair_name(&worker.job_name)?;
        if !matches!(worker.status.as_str(), "launching" | "attached" | "reaped")
            || (worker.status != "launching" && worker.pid.is_none_or(|p| p == 0))
            || !names.insert(&worker.job_name)
        {
            bail!("修复worker回执无效");
        }
    }
    if intent.status == "succeeded" {
        let proof = intent.proof.as_ref().context("成功修复缺少可信验证证明")?;
        if proof.environment != layout.environment
            || proof.recipe_sha256 != RESOURCE_SHA
            || proof.trusted_index_sha256 != gui_registration_integrity::trusted_index_sha256()
            || intent
                .completed_tree_sha256
                .as_deref()
                .is_none_or(|s| !sha_valid(s))
            || intent.workers.iter().any(|w| w.status != "reaped")
        {
            bail!("成功修复的静态验证或worker证明不符");
        }
    }
    Ok(())
}
fn load(layout: &Layout, transaction: &str, cancel: &CancelToken) -> Result<Intent> {
    let value: Intent = serde_json::from_slice(&read(
        layout,
        &transaction_path(layout, transaction)?,
        MAX_INTENT,
        cancel,
    )?)?;
    validate_intent(layout, &value)?;
    if value.transaction != transaction {
        bail!("修复事务文件名不符");
    }
    Ok(value)
}
pub(crate) fn assert_ready(root: &Path, cancel: Option<&CancelToken>) -> Result<()> {
    assert_ready_except(root, None, cancel)
}
pub(crate) fn assert_ready_except(
    root: &Path,
    own: Option<&str>,
    cancel: Option<&CancelToken>,
) -> Result<()> {
    let token = CancelToken::new();
    let cancel = cancel.unwrap_or(&token);
    let layout = Layout::new(root, RELEASE)?;
    let path = root.join(DIRECTORY);
    if !exists(&layout, &path)? {
        if own.is_some() {
            bail!("本修复事务不存在");
        }
        return Ok(());
    }
    let mut count = 0;
    let mut own_found = false;
    for entry in fs::read_dir(path)? {
        check(cancel)?;
        count += 1;
        if count > 128 {
            bail!("独立旧环境修复记录过多");
        }
        let p = entry?.path();
        layout.guard_path(&p)?;
        let transaction = p
            .file_stem()
            .and_then(|s| s.to_str())
            .context("修复事务文件名无效")?;
        if p.extension().is_none_or(|s| s != "json") {
            bail!("修复事务目录含未知条目");
        }
        let intent = load(&layout, transaction, cancel)?;
        if Some(transaction) == own {
            own_found = true;
            continue;
        }
        if !terminal(&intent.status) {
            bail!("旧版本环境修复未完成，请先恢复该修复：{transaction}");
        }
    }
    if own.is_some() && !own_found {
        bail!("本修复事务身份未找到");
    }
    Ok(())
}
/// UI只读恢复入口；坏记录、未知文件和多个pending都拒绝，不吞成“没有问题”。
pub(crate) fn pending_transaction(root: &Path, release: &Release) -> Result<Option<String>> {
    if release.id != RELEASE {
        return Ok(None);
    }
    supported(release)?;
    let layout = Layout::new(root, &release.id)?;
    let cancel = CancelToken::new();
    let path = root.join(DIRECTORY);
    if !exists(&layout, &path)? {
        return Ok(None);
    }
    let mut pending = None;
    let mut count = 0;
    for entry in fs::read_dir(path)? {
        check(&cancel)?;
        count += 1;
        if count > 128 {
            bail!("独立修复记录超过上限");
        }
        let p = entry?.path();
        layout.guard_path(&p)?;
        if p.extension().is_none_or(|s| s != "json") {
            bail!("独立修复目录含未知记录");
        }
        let tx = p
            .file_stem()
            .and_then(|s| s.to_str())
            .context("独立修复记录名无效")?;
        let intent = load(&layout, tx, &cancel)?;
        if !terminal(&intent.status) && pending.replace(tx.to_owned()).is_some() {
            bail!("有多个待恢复旧环境修复事务");
        }
    }
    Ok(pending)
}
fn service_lease(layout: &Layout) -> Result<File> {
    let path = layout.root.join(".launcher-service-lock");
    layout.guard_path(&path)?;
    let f = OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)
        .context("修复需要既有服务租约文件")?;
    fs2::FileExt::try_lock_exclusive(&f).context("训练器服务仍在运行，不能重建其运行环境")?;
    Ok(f)
}
fn move_exact(layout: &Layout, from: &Path, to: &Path) -> Result<()> {
    layout.guard_path(from)?;
    layout.guard_path(to)?;
    if exists(layout, to)? {
        bail!("修复目标已被其他文件占用：{}", to.display());
    }
    fs::rename(from, to)?;
    layout.guard_path(to)?;
    Ok(())
}
fn owner_bytes(intent: &Intent) -> Result<Vec<u8>> {
    Ok(serde_json::to_vec(&intent.owner)?)
}
fn owns(layout: &Layout, path: &Path, intent: &Intent, cancel: &CancelToken) -> Result<()> {
    if read(layout, &path.join(OWNER), 4096, cancel)? != owner_bytes(intent)? {
        bail!("新环境不属于当前修复事务，拒绝移动");
    }
    Ok(())
}
fn progress(
    ctx: &WorkspaceMutation,
    operation: &OperationHandle,
    phase: OperationPhase,
    msg: &str,
) -> Result<()> {
    operation.cancel_token().check()?;
    operation.publish(phase, msg)?;
    operation.persist(ctx)
}
fn protection_unchanged(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    cancel: &CancelToken,
) -> Result<()> {
    if hash(&protection(
        layout,
        release,
        &intent.plan.journal_sha256,
        Some(&intent.transaction),
        intent.plan.schema_version,
        cancel,
    )?) != intent.plan.protections_sha256
    {
        bail!("原安装事务、资料或其他控制记录已变化，拒绝修复收尾");
    }
    super::verify_source_controlled(layout, release, cancel)?;
    Ok(())
}
fn reap_workers(layout: &Layout, intent: &mut Intent) -> Result<()> {
    // attached是spawn前已经持久的保守屏障。即使reader失败后的restart_required写失败，
    // 同代宿主也不能凭Job active0把未join reader当作已排空。
    if intent.restart_required
        || intent
            .workers
            .iter()
            .any(|worker| worker.status != "reaped")
    {
        super::assert_controlled_host_exited(&intent.host)?;
    }
    for index in 0..intent.workers.len() {
        let worker = &intent.workers[index];
        if worker.status == "reaped" {
            continue;
        }
        super::Job::reap_named_attached(
            &worker.job_name,
            worker.session_id,
            worker.status == "attached",
        )?;
        // 只在attached已持久且同session时，命名Job的精确notfound代表对象已销毁。
        intent.workers[index].status = "reaped".into();
        store(layout, intent)?;
    }
    Ok(())
}
fn run(
    layout: &Layout,
    intent: &mut Intent,
    command: Command,
    log: &super::Logger,
    cancel: &CancelToken,
) -> Result<()> {
    check(cancel)?;
    let program = Path::new(command.get_program());
    if program != super::uv(&layout.root)
        && program != layout.environment.join("Scripts/python.exe")
    {
        bail!("独立环境事务拒绝未授权执行程序");
    }
    let recipe = GuiRecipe::embedded()?;
    verify_uv_identity(layout, &recipe.tool_uv.exe_sha256, cancel)
        .context("启动worker前受管uv身份漂移")?;
    if program == layout.environment.join("Scripts/python.exe") && intent.proof.is_none() {
        bail!("新环境未完成可信静态认证，拒绝执行解释器");
    }
    if intent.workers.len() >= 8 {
        bail!("修复worker数量超限");
    }
    let name = super::Job::generate_legacy_repair_name()?;
    let job = super::Job::create_named(&name)?;
    intent.workers.push(Worker {
        job_name: name,
        session_id: super::Job::current_session_id()?,
        status: "launching".into(),
        pid: None,
    });
    store(layout, intent)?;
    let index = intent.workers.len() - 1;
    let result = super::execute_controlled_in_job(command, log, cancel, &job, |pid| {
        intent.workers[index].pid = Some(pid);
        intent.workers[index].status = "attached".into();
        store(layout, intent)
    });
    if let Some(failed) = result
        .as_ref()
        .err()
        .and_then(|e| e.downcast_ref::<super::ControlledProcessReapFailed>())
    {
        intent.status = "needs_attention".into();
        intent.failure = Some("自有Job或reader排空未证，未移动环境".into());
        intent.restart_required |= failed.requires_new_host;
        return result.map_err(|error| persist_attention_failure(layout, intent, error));
    }
    // 持有本次句柄重新核active0；不能把reader结束或child PID消失当排空。
    job.terminate_and_wait()?;
    intent.workers[index].status = "reaped".into();
    if intent.workers[index].pid.is_none() {
        // spawn前拒绝未产生worker；记录保守launching，不冒称附加或可跨重启恢复。
        intent.workers.pop();
    }
    store(layout, intent)?;
    result
}
struct Deadline {
    finished: Arc<AtomicBool>,
    timed_out: Arc<AtomicBool>,
    worker: Option<thread::JoinHandle<()>>,
}
impl Deadline {
    fn start(cancel: CancelToken) -> Result<Self> {
        let finished = Arc::new(AtomicBool::new(false));
        let timed_out = Arc::new(AtomicBool::new(false));
        let done = finished.clone();
        let expired = timed_out.clone();
        let deadline = Instant::now() + TIMEOUT;
        let worker = thread::Builder::new()
            .name("legacy-environment-deadline".into())
            .spawn(move || {
                while !done.load(Ordering::Acquire) {
                    if Instant::now() >= deadline {
                        if cancel.request() == crate::operations::CancelReceipt::Accepted {
                            expired.store(true, Ordering::Release);
                        }
                        break;
                    }
                    thread::park_timeout(deadline.saturating_duration_since(Instant::now()));
                }
            })?;
        Ok(Self {
            finished,
            timed_out,
            worker: Some(worker),
        })
    }
    fn finish(&mut self) {
        self.finished.store(true, Ordering::Release);
        if let Some(w) = self.worker.take() {
            w.thread().unpark();
            let _ = w.join();
        }
    }
}
impl Drop for Deadline {
    fn drop(&mut self) {
        self.finish();
    }
}

fn rollback(layout: &Layout, release: &Release, intent: &mut Intent) -> Result<()> {
    let cancel = CancelToken::new();
    reap_workers(layout, intent)?;
    protection_unchanged(layout, release, intent, &cancel)?;
    restore_original(layout, intent, &cancel)?;
    protection_unchanged(layout, release, intent, &cancel)?;
    intent.status = "rolled_back".into();
    store(layout, intent)
}
/// 只移动本事务精确原件与带精确marker的新目标；与生产恢复共用的原子窗口实现。
fn restore_original(layout: &Layout, intent: &mut Intent, cancel: &CancelToken) -> Result<()> {
    let base = backup(layout, &intent.transaction)?;
    let protected = read(
        layout,
        &base.join("protected-controls.json"),
        MAX_RECORD,
        cancel,
    )?;
    if hash(&protected) != intent.plan.protections_sha256 {
        bail!("保护记录原文备份摘要不符");
    }
    let journal = read(layout, &base.join("original-journal.json"), 65_536, cancel)?;
    if hash(&journal) != intent.plan.journal_sha256 {
        bail!("原journal原文备份摘要不符");
    }
    let raw = read(layout, &base.join("original-tree.json"), MAX_RECORD, cancel)?;
    if hash(&raw) != intent.plan.original_tree_sha256 {
        bail!("旧环境原件清单摘要不符");
    }
    let original: Tree = serde_json::from_slice(&raw)?;
    let saved = base.join("original-env");
    let current = tree(layout, &layout.environment, cancel)?;
    if !exists(layout, &saved)? {
        if current != original {
            bail!("旧环境备份不存在且原位不匹配，拒绝推测恢复");
        }
        return Ok(());
    }
    if tree(layout, &saved, cancel)? != original {
        bail!("旧环境备份原件变化");
    }
    intent.status = "restoring".into();
    store(layout, intent)?;
    if !current.nodes.is_empty() {
        owns(layout, &layout.environment, intent, cancel)?;
        move_exact(layout, &layout.environment, &base.join("failed-new-env"))?;
    }
    move_exact(layout, &saved, &layout.environment)?;
    if tree(layout, &layout.environment, cancel)? != original {
        bail!("原位恢复后旧环境闭包不匹配");
    }
    Ok(())
}
fn rollback_allowed(status: &str, commit_started: bool) -> bool {
    !commit_started && !matches!(status, "committing" | "succeeded" | "needs_attention")
}
fn persist_attention_failure(
    layout: &Layout,
    intent: &Intent,
    failure: anyhow::Error,
) -> anyhow::Error {
    match store(layout, intent) {
        Ok(()) => failure,
        Err(persist) => failure.context(format!(
            "恢复屏障更新未完成，已有launching/attached侧录与环境现场保持：{persist:#}"
        )),
    }
}
fn retain_failed_recovery(
    layout: &Layout,
    intent: &mut Intent,
    original: Option<anyhow::Error>,
    recovery: anyhow::Error,
) -> anyhow::Error {
    let message = match &original {
        Some(error) => {
            format!("独立环境修复失败且恢复未完成；原件保持。原错误：{error:#}；恢复：{recovery:#}")
        }
        None => format!("独立环境恢复未完成；原件保持：{recovery:#}"),
    };
    let recovery_reap = recovery.downcast_ref::<super::ControlledProcessReapFailed>();
    let original_reap = original
        .as_ref()
        .and_then(|error| error.downcast_ref::<super::ControlledProcessReapFailed>());
    intent.restart_required |= [recovery_reap, original_reap]
        .into_iter()
        .flatten()
        .any(|failure| failure.requires_new_host);
    // 回收错误作为错误根保留类型；原Cancelled只能进入消息，不能伪装成干净取消。
    let failure = if recovery_reap.is_some() {
        recovery.context(message.clone())
    } else if original_reap.is_some() {
        original.unwrap().context(message.clone())
    } else {
        anyhow::anyhow!(message.clone())
    };
    intent.status = "needs_attention".into();
    intent.failure = Some(message);
    persist_attention_failure(layout, intent, failure)
}
fn rollback_after_failure(
    layout: &Layout,
    release: &Release,
    intent: &mut Intent,
    error: anyhow::Error,
) -> anyhow::Error {
    intent.failure = Some(format!("{error:#}"));
    match rollback(layout, release, intent) {
        Ok(()) => error,
        Err(recovery) => retain_failed_recovery(layout, intent, Some(error), recovery),
    }
}
fn finish_execute_result(
    ctx: &WorkspaceMutation,
    operation: &OperationHandle,
    result: Result<()>,
    timed_out: bool,
) -> Result<()> {
    let result = match result {
        Err(error)
            if timed_out
                && error
                    .downcast_ref::<super::ControlledProcessReapFailed>()
                    .is_none() =>
        {
            Err(anyhow::anyhow!(
                "旧环境修复超过360秒，独立事务已保留或安全恢复；原安装记录未改"
            ))
        }
        result => result,
    };
    super::finish_gui_lifecycle_result(ctx, operation, result)
}
fn verify_tree_upper_bound(
    layout: &Layout,
    environment: &Path,
    cancel: &CancelToken,
) -> Result<Tree> {
    let upper = gui_registration_integrity::legacy_resource_upper_bound(environment)?;
    let actual = tree(layout, environment, cancel)?;
    assert_tree_upper_bound(&actual, &upper)?;
    Ok(actual)
}
fn assert_tree_upper_bound(
    actual: &Tree,
    upper: &gui_registration_integrity::LegacyResourceUpperBound,
) -> Result<()> {
    let bytes = actual.nodes.values().flatten().try_fold(0u64, |n, v| {
        n.checked_add(v.bytes).context("新环境实际字节溢出")
    })?;
    let files = actual.nodes.values().filter(|v| v.is_some()).count();
    if bytes > upper.bytes
        || bytes > MAX_TREE
        || actual.nodes.len() > upper.nodes
        || files > upper.files
    {
        bail!("新环境实际展开超过固定原始资源与受限生成文件上界");
    }
    Ok(())
}
fn commit_repair(
    intent: &mut Intent,
    cancel: &CancelToken,
    started: &mut bool,
    mut persist: impl FnMut(&Intent) -> Result<()>,
) -> Result<()> {
    // 重操作及proof在调用前完成。此处只参与取消CAS并写两份小intent。
    cancel.enter_commit()?;
    *started = true;
    intent.status = "committing".into();
    persist(intent)?;
    intent.status = "succeeded".into();
    persist(intent)
}
pub(crate) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    journal_sha: &str,
    plan_sha: &str,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    // 第二锁失败必须连本操作记录也零写；持有到finish持久收口后才释放。
    let _service = service_lease(layout)?;
    let cancel = operation.cancel_token();
    let mut deadline = Deadline::start(cancel.clone())?;
    let result = (|| {
        let plan = make_plan(layout, release, journal_sha, None, &cancel, None)?;
        if plan.plan_sha256 != plan_sha {
            bail!("修复计划已变化，请重新检查并确认");
        }
        check(&cancel)?;
        let tx = format!(
            "legacy-{}",
            super::Job::generate_legacy_repair_name()?
                .rsplit('-')
                .next()
                .context("修复事务随机身份缺失")?
        );
        let base = backup(layout, &tx)?;
        layout.ensure_dir(&layout.root.join(DIRECTORY))?;
        layout.ensure_dir(&layout.root.join("backups/legacy-environment-repair"))?;
        layout.guard_path(&base)?;
        fs::create_dir(&base)?;
        let original = tree(layout, &layout.environment, &cancel)?;
        let original_raw = serde_json::to_vec(&original)?;
        if hash(&original_raw) != plan.original_tree_sha256 {
            bail!("备份前原环境变化");
        }
        write_new(layout, &base.join("original-tree.json"), &original_raw)?;
        let controls = protection(
            layout,
            release,
            journal_sha,
            None,
            plan.schema_version,
            &cancel,
        )?;
        if hash(&controls) != plan.protections_sha256 {
            bail!("备份前保护记录变化");
        }
        write_new(layout, &base.join("protected-controls.json"), &controls)?;
        write_new(
            layout,
            &base.join("original-journal.json"),
            &read(
                layout,
                &layout
                    .root
                    .join("state")
                    .join(format!("journal-{}.json", release.id)),
                65_536,
                &cancel,
            )?,
        )?;
        write_new(
            layout,
            &base.join("resources.lock"),
            GuiRecipe::embedded()?.lock().as_bytes(),
        )?;
        let owner = Owner {
            schema_version: 1,
            root: layout.root.clone(),
            release_id: release.id.clone(),
            transaction: tx.clone(),
            plan_sha256: plan_sha.into(),
        };
        let mut intent = Intent {
            schema_version: 1,
            root: layout.root.clone(),
            release_id: release.id.clone(),
            transaction: tx,
            status: "prepared".into(),
            plan,
            owner,
            workers: vec![],
            proof: None,
            completed_tree_sha256: None,
            failure: None,
            host: super::current_controlled_host_identity()?,
            restart_required: false,
        };
        write_new(
            layout,
            &transaction_path(layout, &intent.transaction)?,
            &serde_json::to_vec(&intent)?,
        )?;
        let mut commit_started = false;
        let result = (|| {
            protection_unchanged(layout, release, &intent, &cancel)?;
            progress(
                ctx,
                operation,
                OperationPhase::Executing,
                "正在备份原运行环境；原安装记录保持不变",
            )?;
            intent.status = "saving_original".into();
            store(layout, &intent)?;
            move_exact(layout, &layout.environment, &base.join("original-env"))?;
            if tree(layout, &base.join("original-env"), &cancel)? != original {
                bail!("旧环境原件备份校验失败");
            }
            intent.status = "original_saved".into();
            store(layout, &intent)?;
            // 先准备带完整所有权标记的空目录，再原子移到最终路径；此时尚无venv。
            let reserved = base.join("reserved-target");
            fs::create_dir(&reserved)?;
            write_new(layout, &reserved.join(OWNER), &owner_bytes(&intent)?)?;
            intent.status = "reserving_target".into();
            store(layout, &intent)?;
            move_exact(layout, &reserved, &layout.environment)?;
            intent.status = "building".into();
            store(layout, &intent)?;
            let recipe = GuiRecipe::embedded()?;
            let python = crate::python_integrity::verify_controlled(layout, &cancel)?;
            let mut venv = super::gui_install::command(&layout.root, &recipe);
            venv.env("UV_CACHE_DIR", base.join("uv-cache"))
                .args(["venv", "--allow-existing", "--python"])
                .arg(&python)
                .arg(&layout.environment);
            run(layout, &mut intent, venv, log, &cancel)?;
            owns(layout, &layout.environment, &intent, &cancel)?;
            let mut sync = super::gui_install::command(&layout.root, &recipe);
            sync.env("UV_CACHE_DIR", base.join("uv-cache"))
                .args(["pip", "sync", "--python"])
                .arg(layout.environment.join("Scripts/python.exe"))
                .args(["--no-index", "--find-links"])
                .arg(layout.root.join("cache/wheelhouse"))
                .args([
                    "--only-binary",
                    ":all:",
                    "--require-hashes",
                    "--link-mode",
                    "copy",
                    "--strict",
                ])
                .arg(base.join("resources.lock"));
            run(layout, &mut intent, sync, log, &cancel)?;
            intent.status = "verifying".into();
            store(layout, &intent)?;
            progress(
                ctx,
                operation,
                OperationPhase::Verifying,
                "正在校验新环境全部可信文件与实际依赖导入",
            )?;
            let proof = gui_registration_integrity::verify_legacy_offline_resources(
                layout,
                release,
                &layout.environment,
                &owner_bytes(&intent)?,
                &cancel,
            )?;
            verify_tree_upper_bound(layout, &layout.environment, &cancel)?;
            intent.proof = Some(proof.clone());
            store(layout, &intent)?;
            super::gui_install::validate_environment_runtime_with_runner(
                layout,
                &recipe,
                &layout.environment,
                log,
                &cancel,
                &mut |command| run(layout, &mut intent, command, log, &cancel),
            )?;
            // 实际运行后再核静态闭包和全树；导入不授权新增pyc/控制或修改原文件。
            let after = gui_registration_integrity::verify_legacy_offline_resources(
                layout,
                release,
                &layout.environment,
                &owner_bytes(&intent)?,
                &cancel,
            )?;
            if proof.closure_sha256 != after.closure_sha256 {
                bail!("运行验证改变新环境可信闭包");
            }
            intent.completed_tree_sha256 = Some(hash(&serde_json::to_vec(
                &verify_tree_upper_bound(layout, &layout.environment, &cancel)?,
            )?));
            intent.proof = Some(after);
            protection_unchanged(layout, release, &intent, &cancel)?;
            if tree(layout, &base.join("original-env"), &cancel)? != original {
                bail!("提交前原环境备份变化");
            }
            // proof先在可取消阶段持久；committing只会在取消提交CAS已胜出之后出现。
            store(layout, &intent)?;
            commit_repair(&mut intent, &cancel, &mut commit_started, |value| {
                store(layout, value)
            })?;
            log("旧版本环境已独立修复；请继续验证并完成原安装事务".into());
            Ok(())
        })();
        if let Err(error) = result {
            // 原子终态写可能已替换成功后才报错。短提交门一旦进入，绝不据内存错误回滚新环境。
            // 原intent保持committing/succeeded供显式复核；操作记录失败也不能撤销已提交事实。
            if !rollback_allowed(&intent.status, commit_started) {
                return Err(error
                    .context("独立修复已进入提交或需人工恢复；保留新环境与原件，须核对持久终态"));
            }
            return Err(rollback_after_failure(layout, release, &mut intent, error));
        }
        Ok(())
    })();
    deadline.finish();
    finish_execute_result(
        ctx,
        operation,
        result,
        deadline.timed_out.load(Ordering::Acquire),
    )
}
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    transaction: &str,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    let _service = service_lease(layout)?;
    let cancel = operation.cancel_token();
    let result = (|| {
        supported(release)?;
        let mut intent = load(layout, transaction, &cancel)?;
        if terminal(&intent.status) {
            protection_unchanged(layout, release, &intent, &cancel)?;
            let current = tree(layout, &layout.environment, &cancel)?;
            let expected = if intent.status == "succeeded" {
                intent
                    .completed_tree_sha256
                    .as_ref()
                    .context("成功修复全树证明缺失")?
            } else {
                &intent.plan.original_tree_sha256
            };
            if hash(&serde_json::to_vec(&current)?) != *expected {
                bail!("已结束修复的环境身份发生变化");
            }
            cancel.enter_commit()?;
            return Ok(());
        }
        if intent.status == "committing" {
            // 该阶段只在enter_commit成功后持久，不能把尾部写失败改成回滚成功。
            reap_workers(layout, &mut intent)?;
            protection_unchanged(layout, release, &intent, &cancel)?;
            let proof = gui_registration_integrity::verify_legacy_offline_resources(
                layout,
                release,
                &layout.environment,
                &owner_bytes(&intent)?,
                &cancel,
            )?;
            if intent.proof.as_ref().is_none_or(|saved| saved != &proof)
                || intent.completed_tree_sha256.as_deref()
                    != Some(
                        hash(&serde_json::to_vec(&tree(
                            layout,
                            &layout.environment,
                            &cancel,
                        )?)?)
                        .as_str(),
                    )
            {
                bail!("提交中环境不匹配已持久证明；保留新旧环境待处理");
            }
            let original = read(
                layout,
                &backup(layout, transaction)?.join("original-tree.json"),
                MAX_RECORD,
                &cancel,
            )?;
            if hash(&original) != intent.plan.original_tree_sha256
                || hash(&serde_json::to_vec(&tree(
                    layout,
                    &backup(layout, transaction)?.join("original-env"),
                    &cancel,
                )?)?)
                    != intent.plan.original_tree_sha256
            {
                bail!("提交中旧环境原件不匹配；保留现场");
            }
            cancel.enter_commit()?;
            intent.status = "succeeded".into();
            store(layout, &intent)?;
            log("独立修复提交已核实；原安装事务仍需独立继续验证".into());
            return Ok(());
        }
        progress(
            ctx,
            operation,
            OperationPhase::Recovering,
            "正在排空原修复任务并恢复原运行环境",
        )?;
        if let Err(error) = rollback(layout, release, &mut intent) {
            return Err(retain_failed_recovery(layout, &mut intent, None, error));
        }
        cancel.enter_commit()?;
        log("独立环境修复已回滚；原安装事务仍保持原状态".into());
        Ok(())
    })();
    super::finish_gui_lifecycle_result(ctx, operation, result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU64;
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture {
        layout: Layout,
        intent: Intent,
        original: Tree,
        journal: Vec<u8>,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-lr-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            assert!(!root.exists());
            fs::create_dir(&root).unwrap();
            fs::write(root.join("test-owner"), b"owned").unwrap();
            let layout = Layout::new(&root, RELEASE).unwrap();
            fs::create_dir_all(layout.environment.join("Lib/site-packages")).unwrap();
            fs::write(
                layout.environment.join("pyvenv.cfg"),
                b"original-broken-venv",
            )
            .unwrap();
            fs::write(
                layout.environment.join("Lib/site-packages/original.txt"),
                b"preserve-original",
            )
            .unwrap();
            fs::create_dir_all(root.join(DIRECTORY)).unwrap();
            let journal = b"{\"original\":\"pending\"}\n".to_vec();
            fs::write(
                root.join("state").join(format!("journal-{RELEASE}.json")),
                &journal,
            )
            .unwrap();
            let tx = format!("legacy-{}", "a".repeat(64));
            let original = tree(&layout, &layout.environment, &CancelToken::new()).unwrap();
            let mut plan = LegacyEnvironmentRepairPlan {
                schema_version: 1,
                root: root.clone(),
                release_id: RELEASE.into(),
                journal_sha256: hash(&journal),
                resource_recipe_sha256: RESOURCE_SHA.into(),
                requirements_sha256: INPUT_SHA.into(),
                protections_sha256: hash(b"controls-original"),
                original_tree_sha256: hash(&serde_json::to_vec(&original).unwrap()),
                resources_sha256: "b".repeat(64),
                plan_sha256: String::new(),
                ready: true,
                blockers: vec![],
                operation: "independent_legacy_environment_repair".into(),
            };
            plan.plan_sha256 = hash(&serde_json::to_vec(&plan).unwrap());
            let owner = Owner {
                schema_version: 1,
                root: root.clone(),
                release_id: RELEASE.into(),
                transaction: tx.clone(),
                plan_sha256: plan.plan_sha256.clone(),
            };
            let intent = Intent {
                schema_version: 1,
                root,
                release_id: RELEASE.into(),
                transaction: tx,
                status: "prepared".into(),
                plan,
                owner,
                workers: vec![],
                proof: None,
                completed_tree_sha256: None,
                failure: None,
                host: Host {
                    pid: 1,
                    creation_time: 1,
                },
                restart_required: false,
            };
            let base = backup(&layout, &intent.transaction).unwrap();
            fs::create_dir_all(&base).unwrap();
            fs::write(
                base.join("original-tree.json"),
                serde_json::to_vec(&original).unwrap(),
            )
            .unwrap();
            fs::write(base.join("original-journal.json"), &journal).unwrap();
            fs::write(base.join("protected-controls.json"), b"controls-original").unwrap();
            store(&layout, &intent).unwrap();
            Self {
                layout,
                intent,
                original,
                journal,
            }
        }
        fn base(&self) -> PathBuf {
            backup(&self.layout, &self.intent.transaction).unwrap()
        }
        fn save_original(&mut self) {
            self.intent.status = "saving_original".into();
            store(&self.layout, &self.intent).unwrap();
            move_exact(
                &self.layout,
                &self.layout.environment,
                &self.base().join("original-env"),
            )
            .unwrap();
        }
        fn publish_target(&mut self) {
            let reserve = self.base().join("reserved-target");
            fs::create_dir(&reserve).unwrap();
            write_new(
                &self.layout,
                &reserve.join(OWNER),
                &owner_bytes(&self.intent).unwrap(),
            )
            .unwrap();
            self.intent.status = "reserving_target".into();
            store(&self.layout, &self.intent).unwrap();
            move_exact(&self.layout, &reserve, &self.layout.environment).unwrap();
        }
        fn assert_original(&self) {
            assert_eq!(
                tree(&self.layout, &self.layout.environment, &CancelToken::new()).unwrap(),
                self.original
            );
            assert_eq!(
                fs::read(
                    self.layout
                        .root
                        .join("state")
                        .join(format!("journal-{RELEASE}.json"))
                )
                .unwrap(),
                self.journal
            );
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            if fs::read(self.layout.root.join("test-owner"))
                .ok()
                .as_deref()
                == Some(b"owned")
            {
                let _ = fs::remove_dir_all(&self.layout.root);
            }
        }
    }
    fn control_file(f: &Fixture, relative: &str, raw: &[u8]) -> PathBuf {
        let path = f.layout.root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, raw).unwrap();
        path
    }

    #[test]
    fn control_identity_accepts_product_logs_and_manifest_bound_snapshot_bytes() {
        let f = Fixture::new();
        let owner = format!("state/engines/dev-{}/kohya", "a".repeat(40));
        let operation = format!("{owner}/operations/op-{}", "b".repeat(32));
        let probe = format!("{owner}/probes/{}", "c".repeat(32));
        for base in [&operation, &probe] {
            for name in ["commands.jsonl", "stdout.log", "stderr.log"] {
                control_file(&f, &format!("{base}/{name}"), b"opaque\0bytes\n");
            }
        }
        let payload = b"preserved source\n";
        let snapshot = serde_json::json!([
            {"area":"source","path":"nested/a.py","existed":true,"bytes":payload.len(),"sha256":hash(payload)},
            {"area":"environment","path":"missing.py","existed":false}
        ]);
        control_file(
            &f,
            &format!("{operation}/snapshot.json"),
            &serde_json::to_vec(&snapshot).unwrap(),
        );
        let payload_path = format!("{operation}/snapshot/source/nested/a.py");
        let payload_absolute = control_file(&f, &payload_path, payload);
        let capture = || ControlCollectorV2::capture(&f.layout, &CancelToken::new()).unwrap();
        let original = capture();
        assert_eq!(
            original[Path::new(&payload_path)]
                .identity
                .as_ref()
                .unwrap()
                .sha256,
            hash(payload)
        );
        let log_path = format!("{operation}/commands.jsonl");
        control_file(&f, &log_path, b"OPAQUE\0bytes\n");
        let changed = capture();
        assert_ne!(
            serde_json::to_vec(&original).unwrap(),
            serde_json::to_vec(&changed).unwrap()
        );
        assert_eq!(
            original[Path::new(&log_path)]
                .identity
                .as_ref()
                .unwrap()
                .bytes,
            changed[Path::new(&log_path)]
                .identity
                .as_ref()
                .unwrap()
                .bytes
        );
        fs::write(payload_absolute, b"PRESERVED source\n").unwrap();
        assert!(ControlCollectorV2::capture(&f.layout, &CancelToken::new()).is_err());
    }

    #[test]
    fn control_identity_rejects_unknown_positions_types_and_bad_snapshot_manifests() {
        for relative in [
            "state/instances/commands.jsonl".to_owned(),
            format!("state/engines/dev-{}/kohya/commands.jsonl", "a".repeat(40)),
            format!(
                "state/engines/dev-{}/kohya/operations/op-bad/stdout.log",
                "a".repeat(40)
            ),
            format!(
                "state/engines/dev-{}/kohya/operations/op-{}/unknown.json",
                "a".repeat(40),
                "b".repeat(32)
            ),
            format!(
                "state/engines/dev-{}/kohya/probes/{}/snapshot.json",
                "a".repeat(40),
                "c".repeat(32)
            ),
        ] {
            let f = Fixture::new();
            control_file(&f, &relative, b"{}");
            assert!(
                ControlCollectorV2::capture(&f.layout, &CancelToken::new()).is_err(),
                "{relative}"
            );
        }
        for manifest in [
            serde_json::json!({}),
            serde_json::json!([{"area":"source","path":"../a.py","existed":false}]),
            serde_json::json!([{"area":"other","path":"a.py","existed":false}]),
            serde_json::json!([{"area":"source","path":"a.py","existed":true}]),
            serde_json::json!([{"area":"source","path":"a.py","existed":true,"bytes":1,"sha256":"a".repeat(64)}]),
            serde_json::json!([{"area":"source","path":"a.py","existed":false,"bytes":0}]),
            serde_json::json!([{"area":"source","path":"a.py","existed":false},{"area":"source","path":"A.py","existed":false}]),
        ] {
            let f = Fixture::new();
            let path = format!(
                "state/engines/dev-{}/kohya/operations/op-{}/snapshot.json",
                "a".repeat(40),
                "b".repeat(32)
            );
            control_file(&f, &path, &serde_json::to_vec(&manifest).unwrap());
            assert!(
                ControlCollectorV2::capture(&f.layout, &CancelToken::new()).is_err(),
                "{manifest}"
            );
        }
        let f = Fixture::new();
        control_file(&f, "state/instances/gui.json", b"[]");
        assert!(ControlCollectorV2::capture(&f.layout, &CancelToken::new()).is_err());
    }

    #[test]
    fn control_identity_preserves_path_sets_and_cancellation_and_compacts_48mib() {
        let f = Fixture::new();
        let mut raw = vec![b' '; 24 * 1024 * 1024];
        raw[..2].copy_from_slice(b"{}");
        control_file(&f, "state/instances/gui-a.json", &raw);
        control_file(&f, "state/instances/gui-b.json", &raw);
        drop(raw);
        let original = ControlCollectorV2::capture(&f.layout, &CancelToken::new()).unwrap();
        assert!(serde_json::to_vec(&original).unwrap().len() < 4096);
        fs::rename(
            f.layout.root.join("state/instances/gui-b.json"),
            f.layout.root.join("state/instances/gui-c.json"),
        )
        .unwrap();
        let changed = ControlCollectorV2::capture(&f.layout, &CancelToken::new()).unwrap();
        assert_ne!(
            serde_json::to_vec(&original).unwrap(),
            serde_json::to_vec(&changed).unwrap()
        );
        let cancel = CancelToken::new();
        cancel.request();
        assert!(ControlCollectorV2::capture(&f.layout, &cancel).is_err());
    }

    #[test]
    fn control_identity_plan_versions_bind_their_hash_and_reject_unknown_formats() {
        for version in [0, 1, 2, 3] {
            let mut f = Fixture::new();
            f.intent.plan.schema_version = version;
            f.intent.plan.plan_sha256.clear();
            f.intent.plan.plan_sha256 = hash(&serde_json::to_vec(&f.intent.plan).unwrap());
            f.intent.owner.plan_sha256 = f.intent.plan.plan_sha256.clone();
            store(&f.layout, &f.intent).unwrap();
            assert_eq!(
                load(&f.layout, &f.intent.transaction, &CancelToken::new()).is_ok(),
                matches!(version, 1 | 2)
            );
        }
        // schema1的控制原文仍采用原有数字数组编码，不能用v2身份冒充旧hash。
        let old = ControlRecord {
            kind: "file",
            bytes: Some(b"{}".to_vec()),
        };
        assert_eq!(
            serde_json::to_vec(&old).unwrap(),
            br#"{"kind":"file","bytes":[123,125]}"#
        );
        let new = ControlIdentityRecord {
            kind: "file",
            identity: Some(Identity {
                bytes: 2,
                sha256: hash(b"{}"),
            }),
        };
        assert_ne!(
            hash(&serde_json::to_vec(&old).unwrap()),
            hash(&serde_json::to_vec(&new).unwrap())
        );
    }

    #[test]
    fn control_identity_v1_and_v2_capture_keep_distinct_persistent_algorithms() {
        let mut f = Fixture::new();
        let catalog = model::Catalog::embedded().unwrap();
        let release = catalog.release(RELEASE).unwrap();
        fs::write(
            f.layout.root.join(".launcher-workspace"),
            model::WORKSPACE_MARKER,
        )
        .unwrap();
        let mut registry = model::Registry::default();
        registry.record_installed(release).unwrap();
        registry.store(&f.layout.root).unwrap();
        fs::create_dir_all(&f.layout.release_dir).unwrap();
        model::ReleaseReceipt::new(release)
            .store(&f.layout.release_dir)
            .unwrap();
        f.journal = serde_json::to_vec(&model::Journal::new(RELEASE).unwrap()).unwrap();
        fs::write(
            f.layout
                .root
                .join("state")
                .join(format!("journal-{RELEASE}.json")),
            &f.journal,
        )
        .unwrap();
        f.intent.plan.journal_sha256 = hash(&f.journal);
        f.intent.plan.plan_sha256.clear();
        f.intent.plan.plan_sha256 = hash(&serde_json::to_vec(&f.intent.plan).unwrap());
        f.intent.owner.plan_sha256 = f.intent.plan.plan_sha256.clone();
        store(&f.layout, &f.intent).unwrap();
        let control = control_file(&f, "state/instances/gui.json", b"{}");
        let cancel = CancelToken::new();
        let legacy = protection_v1(
            &f.layout,
            release,
            &hash(&f.journal),
            Some(&f.intent.transaction),
            &cancel,
        )
        .unwrap();
        let capture = |version| {
            protection(
                &f.layout,
                release,
                &hash(&f.journal),
                Some(&f.intent.transaction),
                version,
                &cancel,
            )
            .unwrap()
        };
        assert_eq!(capture(1), legacy);
        let compact = capture(2);
        assert_ne!(hash(&legacy), hash(&compact));
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&compact).unwrap()["schema_version"],
            2
        );
        fs::write(control, b"{ }").unwrap();
        assert_ne!(hash(&capture(1)), hash(&legacy));
        assert_ne!(hash(&capture(2)), hash(&compact));
        assert!(protection(
            &f.layout,
            release,
            &hash(&f.journal),
            Some(&f.intent.transaction),
            3,
            &cancel
        )
        .is_err());
    }

    #[test]
    fn control_identity_keeps_record_depth_and_raw_read_budgets() {
        let f = Fixture::new();
        let mut collector = ControlCollectorV2::default();
        assert!(collector
            .collect(
                &f.layout,
                &f.layout.root.join("state/instances"),
                17,
                &CancelToken::new()
            )
            .is_err());
        for n in 0..256 {
            collector.records.insert(
                PathBuf::from(format!("{n}")),
                ControlIdentityRecord {
                    kind: "missing",
                    identity: None,
                },
            );
        }
        assert!(collector
            .collect(
                &f.layout,
                &f.layout.root.join("state/instances"),
                0,
                &CancelToken::new()
            )
            .is_err());
        let path = control_file(&f, "state/instances/gui.json", b"{}");
        let mut collector = ControlCollectorV2 {
            usage: 64 * 1024 * 1024 - 1,
            ..ControlCollectorV2::default()
        };
        assert!(collector
            .collect(&f.layout, &path, 0, &CancelToken::new())
            .is_err());
        let file = OpenOptions::new().write(true).open(&path).unwrap();
        file.set_len(MAX_RECORD as u64 + 1).unwrap();
        assert!(ControlCollectorV2::capture(&f.layout, &CancelToken::new()).is_err());
    }

    #[test]
    fn production_resources_missing_archive_refuses_without_new_writes() {
        let f = Fixture::new();
        let catalog = model::Catalog::embedded().unwrap();
        let release = catalog.release(RELEASE).unwrap();
        let cancel = CancelToken::new();
        let before = tree(&f.layout, &f.layout.root, &cancel).unwrap();
        let error = resources(&f.layout, release, &cancel, None).unwrap_err();
        assert!(error.chain().any(|cause| {
            cause
                .downcast_ref::<std::io::Error>()
                .is_some_and(|e| e.kind() == std::io::ErrorKind::NotFound)
        }));
        assert_eq!(tree(&f.layout, &f.layout.root, &cancel).unwrap(), before);
        f.assert_original();
    }
    #[test]
    fn production_resources_equal_length_wrong_archive_sha_refuses_without_new_writes() {
        let f = Fixture::new();
        let catalog = model::Catalog::embedded().unwrap();
        let release = catalog.release(RELEASE).unwrap();
        let cache = f.layout.root.join("cache");
        fs::create_dir(&cache).unwrap();
        let archive = cache.join(format!("{}.zip", release.archive.sha256));
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&archive)
            .unwrap();
        // 等长真实文件确保走完整摘要比较，而非长度拒绝或ZIP解析错误。
        file.set_len(release.archive.bytes).unwrap();
        drop(file);
        let cancel = CancelToken::new();
        let before = tree(&f.layout, &f.layout.root, &cancel).unwrap();
        let error = resources(&f.layout, release, &cancel, None).unwrap_err();
        assert_eq!(error.to_string(), "legacy固定源码归档缺失或摘要错误");
        assert_eq!(tree(&f.layout, &f.layout.root, &cancel).unwrap(), before);
        f.assert_original();
    }
    #[test]
    fn production_uv_identity_reads_fixed_executable_over_32_mib_and_keeps_sha_gate() {
        // 此固定全零文件摘要独立计算；不把受测digest输出作为期望值。
        const ZERO_UV_SHA: &str =
            "87e325fe46aeb2fb686d9eca05cb2eae97fa6ca23f55701bc0456fbe51f6b2b5";
        assert_eq!(TRUSTED_UV_EXE_BYTES, 67_598_848);
        let f = Fixture::new();
        fs::create_dir(f.layout.root.join("tools")).unwrap();
        let path = super::super::uv(&f.layout.root);
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        file.set_len(TRUSTED_UV_EXE_BYTES).unwrap();
        drop(file);
        let cancel = CancelToken::new();
        let before = tree(&f.layout, &f.layout.root, &cancel).unwrap();
        let identity = verify_uv_identity(&f.layout, ZERO_UV_SHA, &cancel).unwrap();
        assert_eq!(identity.bytes, TRUSTED_UV_EXE_BYTES);
        assert!(identity.bytes > 32 * 1024 * 1024);
        assert_eq!(identity.sha256, ZERO_UV_SHA);
        let embedded = GuiRecipe::embedded().unwrap();
        assert!(verify_uv_identity(&f.layout, &embedded.tool_uv.exe_sha256, &cancel).is_err());
        assert_eq!(tree(&f.layout, &f.layout.root, &cancel).unwrap(), before);
        // 超过固定展开长度的文件仍须在读取前拒绝。
        OpenOptions::new()
            .write(true)
            .open(&path)
            .unwrap()
            .set_len(TRUSTED_UV_EXE_BYTES + 1)
            .unwrap();
        assert!(verify_uv_identity(&f.layout, ZERO_UV_SHA, &cancel).is_err());
        f.assert_original();
    }
    #[test]
    fn exact_legacy_identity_does_not_alias_modern_recipe() {
        let catalog = model::Catalog::embedded().unwrap();
        let release = catalog.release(RELEASE).unwrap();
        supported(release).unwrap();
        assert!(!GuiRecipe::embedded()
            .unwrap()
            .matches_environment_recipe(&release.environment_recipe));
        assert_eq!(
            GuiRecipe::embedded().unwrap().requirements.input_sha256,
            INPUT_SHA
        );
        let mut changed = release.clone();
        changed.commit = "0".repeat(40);
        assert!(supported(&changed).is_err());
    }
    #[test]
    fn pending_terminal_vocabulary_is_closed() {
        for s in [
            "prepared",
            "building",
            "verifying",
            "committing",
            "restoring",
            "needs_attention",
            "committed",
            "unknown",
        ] {
            assert!(!terminal(s));
        }
        for s in ["succeeded", "rolled_back", "aborted"] {
            assert!(terminal(s));
        }
    }
    #[test]
    fn relative_assets_reject_escape_and_platform_alias_inputs() {
        for s in ["../x", "/x", "a\\b", "C:/x", ""] {
            assert!(relative(s).is_err(), "{s}");
        }
        assert_eq!(relative("pkg/file.py").unwrap(), Path::new("pkg/file.py"));
    }
    #[test]
    fn all_atomic_directory_windows_restore_exact_original_and_are_idempotent() {
        // 每例使用真实目录rename；代表原件保存、marker预留、目标发布、隔离、原位恢复的前后窗口。
        for window in 0..8 {
            let mut f = Fixture::new();
            if window >= 1 {
                f.save_original();
            }
            if window == 2 {
                fs::create_dir(f.base().join("reserved-target")).unwrap();
            }
            if window == 3 {
                fs::create_dir(f.base().join("reserved-target")).unwrap();
                fs::write(
                    f.base().join("reserved-target").join(OWNER),
                    owner_bytes(&f.intent).unwrap(),
                )
                .unwrap();
            }
            if window >= 4 {
                f.publish_target();
            }
            if window >= 5 {
                fs::write(f.layout.environment.join("partial-wheel.txt"), b"partial").unwrap();
            }
            if window >= 6 {
                move_exact(
                    &f.layout,
                    &f.layout.environment,
                    &f.base().join("failed-new-env"),
                )
                .unwrap();
            }
            if window >= 7 {
                move_exact(
                    &f.layout,
                    &f.base().join("original-env"),
                    &f.layout.environment,
                )
                .unwrap();
            }
            restore_original(&f.layout, &mut f.intent, &CancelToken::new()).unwrap();
            f.assert_original();
            restore_original(&f.layout, &mut f.intent, &CancelToken::new()).unwrap();
            f.assert_original();
        }
    }
    #[test]
    fn unknown_target_and_quarantine_collision_never_overwrite_original_or_foreign_files() {
        for collision in [false, true] {
            let mut f = Fixture::new();
            f.save_original();
            if collision {
                f.publish_target();
                fs::create_dir(f.base().join("failed-new-env")).unwrap();
                fs::write(f.base().join("failed-new-env/foreign"), b"keep").unwrap();
            } else {
                fs::create_dir(&f.layout.environment).unwrap();
                fs::write(f.layout.environment.join("foreign"), b"keep").unwrap();
            }
            assert!(restore_original(&f.layout, &mut f.intent, &CancelToken::new()).is_err());
            assert_eq!(
                tree(
                    &f.layout,
                    &f.base().join("original-env"),
                    &CancelToken::new()
                )
                .unwrap(),
                f.original
            );
            let foreign = if collision {
                f.base().join("failed-new-env/foreign")
            } else {
                f.layout.environment.join("foreign")
            };
            assert_eq!(fs::read(foreign).unwrap(), b"keep");
        }
    }
    #[test]
    fn original_and_control_backup_tampering_refuse_before_any_rename() {
        for which in [
            "original-tree.json",
            "protected-controls.json",
            "original-journal.json",
        ] {
            let mut f = Fixture::new();
            f.save_original();
            f.publish_target();
            fs::write(f.base().join(which), b"tampered").unwrap();
            assert!(restore_original(&f.layout, &mut f.intent, &CancelToken::new()).is_err());
            assert!(f.base().join("original-env").is_dir());
            assert!(f.layout.environment.join(OWNER).is_file());
            assert!(!f.base().join("failed-new-env").exists());
        }
    }
    #[test]
    fn own_transaction_capability_does_not_skip_other_pending_or_bad_records() {
        let f = Fixture::new();
        assert!(assert_ready(&f.layout.root, None).is_err());
        assert_ready_except(&f.layout.root, Some(&f.intent.transaction), None).unwrap();
        assert!(assert_ready_except(&f.layout.root, Some("nonexistent"), None).is_err());
        let mut second = f.intent.clone();
        second.transaction = format!("legacy-{}", "c".repeat(64));
        second.owner.transaction = second.transaction.clone();
        store(&f.layout, &second).unwrap();
        assert!(assert_ready_except(&f.layout.root, Some(&f.intent.transaction), None).is_err());
        assert!(pending_transaction(
            &f.layout.root,
            model::Catalog::embedded()
                .unwrap()
                .release(RELEASE)
                .unwrap()
        )
        .is_err());
    }
    #[test]
    fn original_journal_is_never_replaced_on_restore_failure_or_replay() {
        let mut f = Fixture::new();
        f.save_original();
        f.publish_target();
        let before = fs::read(
            f.layout
                .root
                .join("state")
                .join(format!("journal-{RELEASE}.json")),
        )
        .unwrap();
        restore_original(&f.layout, &mut f.intent, &CancelToken::new()).unwrap();
        restore_original(&f.layout, &mut f.intent, &CancelToken::new()).unwrap();
        assert_eq!(
            fs::read(
                f.layout
                    .root
                    .join("state")
                    .join(format!("journal-{RELEASE}.json"))
            )
            .unwrap(),
            before
        );
    }
    #[test]
    fn commit_atomic_replace_then_error_cannot_trigger_rollback() {
        let mut f = Fixture::new();
        let cancel = CancelToken::new();
        let mut started = false;
        let result = commit_repair(&mut f.intent, &cancel, &mut started, |intent| {
            store(&f.layout, intent)?;
            if intent.status == "succeeded" {
                bail!("injected error after successful atomic replacement");
            }
            Ok(())
        });
        assert!(result.is_err());
        assert!(started);
        assert!(!rollback_allowed(&f.intent.status, started));
        let raw: serde_json::Value = serde_json::from_slice(
            &fs::read(transaction_path(&f.layout, &f.intent.transaction).unwrap()).unwrap(),
        )
        .unwrap();
        assert_eq!(raw["status"], "succeeded");
        f.assert_original();
    }
    #[test]
    fn accepted_cancel_prevents_both_commit_records_and_retains_original() {
        let mut f = Fixture::new();
        let cancel = CancelToken::new();
        cancel.request();
        let mut started = false;
        let mut writes = 0;
        assert!(commit_repair(&mut f.intent, &cancel, &mut started, |_| {
            writes += 1;
            Ok(())
        })
        .is_err());
        assert!(!started);
        assert_eq!(writes, 0);
        assert!(rollback_allowed(&f.intent.status, started));
        f.assert_original();
    }
    #[test]
    fn cancelled_read_and_second_service_lease_leave_no_new_intent_or_environment_writes() {
        let f = Fixture::new();
        let cancel = CancelToken::new();
        cancel.request();
        assert!(tree(&f.layout, &f.layout.environment, &cancel).is_err());
        fs::write(f.layout.root.join(".launcher-service-lock"), b"").unwrap();
        let first = service_lease(&f.layout).unwrap();
        assert!(service_lease(&f.layout).is_err());
        drop(first);
        f.assert_original();
        assert_eq!(
            fs::read_dir(f.layout.root.join(DIRECTORY)).unwrap().count(),
            1
        );
    }
    #[cfg(windows)]
    #[test]
    fn attached_receipt_blocks_same_host_even_when_restart_barrier_persistence_failed() {
        let mut f = Fixture::new();
        f.intent.host = super::super::current_controlled_host_identity().unwrap();
        f.intent.workers.push(Worker {
            job_name: format!("Local\\NextTrainerLegacyRepair-{}", "d".repeat(64)),
            session_id: super::super::Job::current_session_id().unwrap(),
            status: "attached".into(),
            pid: Some(42),
        });
        store(&f.layout, &f.intent).unwrap();
        let path = transaction_path(&f.layout, &f.intent.transaction).unwrap();
        let original_bytes = fs::read(&path).unwrap();
        let mut failed_update = f.intent.clone();
        failed_update.restart_required = true;
        // create_new冲突模拟屏障写未替换任何旧原文；恢复必须读到原attached/false仍拒绝。
        assert!(write_new(
            &f.layout,
            &path,
            &serde_json::to_vec(&failed_update).unwrap()
        )
        .is_err());
        let mut persisted = load(&f.layout, &f.intent.transaction, &CancelToken::new()).unwrap();
        assert!(!persisted.restart_required);
        assert!(reap_workers(&f.layout, &mut persisted).is_err());
        assert_eq!(fs::read(&path).unwrap(), original_bytes);
        f.assert_original();
        persisted.workers[0].status = "reaped".into();
        reap_workers(&f.layout, &mut persisted).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn production_rollback_deadline_finalize_preserves_reap_type_and_durable_barrier() {
        use crate::operations::{
            CancelReceipt, Cancelled, OperationKind, OperationManager, OperationStatus,
        };
        for timed_out in [false, true] {
            let mut f = Fixture::new();
            // 将合成根准备为正式操作记录可落盘的工作区；仍不运行任何环境解释器。
            fs::write(
                f.layout.root.join(".launcher-workspace"),
                model::WORKSPACE_MARKER,
            )
            .unwrap();
            f.journal = serde_json::to_vec(&model::Journal::new(RELEASE).unwrap()).unwrap();
            fs::write(
                f.layout
                    .root
                    .join("state")
                    .join(format!("journal-{RELEASE}.json")),
                &f.journal,
            )
            .unwrap();
            f.intent.plan.journal_sha256 = hash(&f.journal);
            f.intent.plan.plan_sha256.clear();
            f.intent.plan.plan_sha256 = hash(&serde_json::to_vec(&f.intent.plan).unwrap());
            f.intent.owner.plan_sha256 = f.intent.plan.plan_sha256.clone();
            fs::write(f.base().join("original-journal.json"), &f.journal).unwrap();
            let ctx = WorkspaceMutation::acquire(&f.layout.root, RELEASE).unwrap();
            f.save_original();
            f.publish_target();
            f.intent.host = super::super::current_controlled_host_identity().unwrap();
            f.intent.status = "building".into();
            f.intent.workers.push(Worker {
                job_name: format!("Local\\NextTrainerLegacyRepair-{}", "e".repeat(64)),
                session_id: super::super::Job::current_session_id().unwrap(),
                status: "attached".into(),
                pid: Some(42),
            });
            store(&f.layout, &f.intent).unwrap();
            let before = tree(&f.layout, &f.layout.environment, &CancelToken::new()).unwrap();
            let manager = OperationManager::default();
            let operation = manager
                .start("legacy-rollback-reap", OperationKind::Repair)
                .unwrap();
            assert_eq!(
                manager.cancel("legacy-rollback-reap").unwrap(),
                CancelReceipt::Accepted
            );
            // 走真实rollback与真实宿主代次门；同宿主拒绝发生在任何环境rename之前。
            let error = rollback_after_failure(
                &f.layout,
                model::Catalog::embedded()
                    .unwrap()
                    .release(RELEASE)
                    .unwrap(),
                &mut f.intent,
                Cancelled.into(),
            );
            assert!(
                error
                    .downcast_ref::<super::super::ControlledProcessReapFailed>()
                    .unwrap()
                    .requires_new_host
            );
            assert!(error.downcast_ref::<Cancelled>().is_none());
            let error = finish_execute_result(&ctx, &operation, Err(error), timed_out).unwrap_err();
            assert!(
                error
                    .downcast_ref::<super::super::ControlledProcessReapFailed>()
                    .unwrap()
                    .requires_new_host
            );
            let persisted = load(&f.layout, &f.intent.transaction, &CancelToken::new()).unwrap();
            assert_eq!(persisted.status, "needs_attention");
            assert!(persisted.restart_required);
            assert_eq!(persisted.workers[0].status, "attached");
            assert!(assert_ready(&f.layout.root, None).is_err());
            assert_eq!(
                tree(&f.layout, &f.layout.environment, &CancelToken::new()).unwrap(),
                before
            );
            assert_eq!(
                tree(
                    &f.layout,
                    &f.base().join("original-env"),
                    &CancelToken::new()
                )
                .unwrap(),
                f.original
            );
            assert_eq!(
                fs::read(
                    f.layout
                        .root
                        .join("state")
                        .join(format!("journal-{RELEASE}.json"))
                )
                .unwrap(),
                f.journal
            );
            let snapshots = crate::operations::load_snapshots(ctx.layout()).unwrap();
            let saved = snapshots
                .iter()
                .find(|value| value.id == "legacy-rollback-reap")
                .unwrap();
            let mut live = manager.snapshot("legacy-rollback-reap").unwrap();
            live.event_seq = 0; // 历史视图没有旧进程事件游标。
            assert_eq!(*saved, live);
            assert_eq!(saved.status, OperationStatus::Failed);
            assert_eq!(saved.error.as_ref().unwrap().code, "worker_reap_failed");
        }
    }
    #[test]
    fn production_deadline_finalize_keeps_cancel_timeout_and_success_semantics() {
        use crate::operations::{Cancelled, OperationKind, OperationManager, OperationStatus};
        for (case, timed_out) in [("cancel", false), ("timeout", true), ("success", true)] {
            let f = Fixture::new();
            let operation_root = f.layout.root.join("operation-contract");
            let ctx = WorkspaceMutation::acquire(&operation_root, RELEASE).unwrap();
            let manager = OperationManager::default();
            let operation = manager.start(case, OperationKind::Repair).unwrap();
            let result = if case == "success" {
                Ok(())
            } else {
                Err(Cancelled.into())
            };
            let result = finish_execute_result(&ctx, &operation, result, timed_out);
            let snapshots = crate::operations::load_snapshots(ctx.layout()).unwrap();
            let saved = snapshots.iter().find(|value| value.id == case).unwrap();
            match case {
                "cancel" => {
                    assert!(result.unwrap_err().downcast_ref::<Cancelled>().is_some());
                    assert_eq!(saved.status, OperationStatus::Cancelled);
                }
                "timeout" => {
                    let error = result.unwrap_err();
                    assert!(error.downcast_ref::<Cancelled>().is_none());
                    assert!(error.to_string().contains("超过360秒"));
                    assert_eq!(saved.status, OperationStatus::Failed);
                    assert_eq!(saved.error.as_ref().unwrap().code, "gui_lifecycle_failed");
                }
                _ => {
                    result.unwrap();
                    assert_eq!(saved.status, OperationStatus::Succeeded);
                }
            }
            f.assert_original();
        }
    }
    #[cfg(windows)]
    #[test]
    fn production_attention_persist_failure_keeps_reap_type_and_attached_barrier() {
        use std::os::windows::fs::OpenOptionsExt;
        let mut f = Fixture::new();
        f.intent.host = super::super::current_controlled_host_identity().unwrap();
        f.intent.workers.push(Worker {
            job_name: format!("Local\\NextTrainerLegacyRepair-{}", "f".repeat(64)),
            session_id: super::super::Job::current_session_id().unwrap(),
            status: "attached".into(),
            pid: Some(42),
        });
        store(&f.layout, &f.intent).unwrap();
        let path = transaction_path(&f.layout, &f.intent.transaction).unwrap();
        let before = fs::read(&path).unwrap();
        let held = OpenOptions::new()
            .read(true)
            .share_mode(0)
            .open(&path)
            .unwrap();
        f.intent.status = "needs_attention".into();
        f.intent.restart_required = true;
        let mut failure = super::super::ControlledProcessReapFailed::new(
            "synthetic unjoined reader".into(),
            true,
        );
        failure.requires_new_host = true;
        let error = persist_attention_failure(&f.layout, &f.intent, failure.into());
        assert!(
            error
                .downcast_ref::<super::super::ControlledProcessReapFailed>()
                .unwrap()
                .requires_new_host
        );
        assert!(error.to_string().contains("恢复屏障更新未完成"));
        drop(held);
        assert_eq!(fs::read(path).unwrap(), before);
        let mut persisted = load(&f.layout, &f.intent.transaction, &CancelToken::new()).unwrap();
        assert!(!persisted.restart_required);
        assert_eq!(persisted.workers[0].status, "attached");
        assert!(reap_workers(&f.layout, &mut persisted).is_err());
        f.assert_original();
    }
    #[test]
    fn actual_tree_upper_rejects_bytes_and_nodes_without_large_file_fixture() {
        let upper = gui_registration_integrity::LegacyResourceUpperBound {
            bytes: 4,
            nodes: 2,
            files: 1,
            trusted_index_sha256: String::new(),
        };
        let mut actual = Tree {
            nodes: BTreeMap::from([
                (PathBuf::new(), None),
                (
                    PathBuf::from("a"),
                    Some(Identity {
                        bytes: 4,
                        sha256: String::new(),
                    }),
                ),
            ]),
        };
        assert_tree_upper_bound(&actual, &upper).unwrap();
        actual
            .nodes
            .get_mut(Path::new("a"))
            .unwrap()
            .as_mut()
            .unwrap()
            .bytes = 5;
        assert!(assert_tree_upper_bound(&actual, &upper).is_err());
        actual
            .nodes
            .get_mut(Path::new("a"))
            .unwrap()
            .as_mut()
            .unwrap()
            .bytes = 4;
        actual.nodes.insert(PathBuf::from("b"), None);
        assert!(assert_tree_upper_bound(&actual, &upper).is_err());
    }
}
