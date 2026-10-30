//! Shared base-Python repair. Rust-only planning; an explicit cohort gate spans every commit.
use crate::{
    instances,
    model::{self, Catalog, EnvironmentBinding, Layout, Registry, Release, WorkspaceMutation},
    operations::{
        CancelToken, Cancelled, OperationError, OperationHandle, OperationPhase, OperationStatus,
    },
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

const COMPONENT: &str = "cpython-3.10.19-20260211-windows-x86_64-none";
const TARGET: &str = "python/3.10.19";
const PATCH: &str = "cpython-3.10.19-windows-x86_64-none";
const ALIAS: &str = "cpython-3.10-windows-x86_64-none";
const RECORD: &str = "state/base-python-repair.json";
const MAX_RECORD: u64 = 256 * 1024;
const MAX_DETAIL: u64 = 32 * 1024 * 1024;
const MAX_FILE: u64 = 1024 * 1024 * 1024;
const MAX_TREE: u64 = 8 * 1024 * 1024 * 1024;
static SERIAL: AtomicU64 = AtomicU64::new(0);

type Validator<'a> = dyn FnMut(&Layout, &Release, &Path, &CancelToken) -> Result<()> + 'a;
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Tree {
    exists: bool,
    bytes: u64,
    files: u64,
    sha256: String,
    minor_alias: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Reference {
    release_id: String,
    instance_id: String,
    storage_version: u32,
    environment: PathBuf,
    generation: u64,
    initial_dirty: bool,
    state_sha256: String,
    binding: Option<EnvironmentBinding>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Protection {
    roots: BTreeMap<PathBuf, Tree>,
    profiles: instances::ProfilesSummary,
    other_states: BTreeMap<PathBuf, String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    component_id: String,
    root: PathBuf,
    target: PathBuf,
    replacement_scope: String,
    expected_files: Vec<String>,
    integrity_error: Option<String>,
    references: Vec<Reference>,
    blockers: Vec<String>,
    before: Option<Tree>,
    protection: Option<Protection>,
    registry_sha256: String,
    pending_transaction: Option<String>,
    repair_available: bool,
    recovery_available: bool,
    recovery_error: Option<String>,
    plan_sha256: String,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Prepared,
    Quarantined,
    Snapshotted,
    Publishing,
    Published,
    Validated,
    Committing,
    Committed,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    component_id: String,
    root: PathBuf,
    transaction: String,
    phase: Phase,
    details: PathBuf,
    details_sha256: String,
    staging: PathBuf,
    backup: PathBuf,
    previous: PathBuf,
    before: Tree,
    staged: Tree,
    candidates: BTreeMap<String, String>,
    snapshot_complete: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Details {
    schema_version: u32,
    transaction: String,
    plan: Plan,
    registry_before: Registry,
    registry_disabled: Registry,
    original_states: BTreeMap<String, String>,
    original_registry_sha256: Option<String>,
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn read_small(layout: &Layout, path: &Path, limit: u64) -> Result<Vec<u8>> {
    layout.guard_path(path)?;
    let mut input = File::open(path)?;
    if input.metadata()?.len() > limit {
        bail!("修复状态或控制文件过大");
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut input)
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        bail!("修复控制文件读取超限");
    }
    Ok(bytes)
}
fn write_new(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    layout.guard_path(path)?;
    layout.ensure_dir(path.parent().context("修复文件缺少父目录")?)?;
    let mut output = OpenOptions::new().write(true).create_new(true).open(path)?;
    output.write_all(bytes)?;
    output.sync_all()?;
    Ok(())
}
fn key(path: &Path) -> String {
    path.to_string_lossy()
        .trim_start_matches(r"\\?\")
        .replace('/', "\\")
        .to_ascii_lowercase()
}
fn alias_at(path: &Path, root: &Path) -> bool {
    path == root.join(ALIAS)
}
/// Read the reparse record itself. junction::exists follows the target first and
/// reports false for the exact dangling alias created by our rename window.
#[cfg(windows)]
fn junction_target(path: &Path) -> Result<Option<PathBuf>> {
    use std::{
        ffi::OsString,
        os::windows::{
            ffi::OsStringExt,
            fs::{MetadataExt, OpenOptionsExt},
            io::AsRawHandle,
        },
        ptr,
    };
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    if metadata.file_attributes() & 0x400 == 0 {
        return Ok(None);
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn DeviceIoControl(
            handle: *mut std::ffi::c_void,
            code: u32,
            input: *mut std::ffi::c_void,
            input_bytes: u32,
            output: *mut std::ffi::c_void,
            output_bytes: u32,
            returned: *mut u32,
            overlapped: *mut std::ffi::c_void,
        ) -> i32;
    }
    let input = OpenOptions::new()
        .access_mode(0x8000_0000)
        .share_mode(0x7)
        .custom_flags(0x0020_0000 | 0x0200_0000)
        .open(path)?;
    let mut bytes = [0u8; 16_384];
    let mut returned = 0u32;
    // SAFETY: input is a live no-follow file handle; output is a bounded writable
    // buffer and the remaining pointers are either valid scalars or null.
    if unsafe {
        DeviceIoControl(
            input.as_raw_handle(),
            0x0009_00a8,
            ptr::null_mut(),
            0,
            bytes.as_mut_ptr().cast(),
            bytes.len() as u32,
            &mut returned,
            ptr::null_mut(),
        )
    } == 0
    {
        return Err(std::io::Error::last_os_error()).context("读取基础Python别名重解析数据失败");
    }
    let returned = returned as usize;
    if returned < 16
        || returned > bytes.len()
        || u32::from_le_bytes(bytes[..4].try_into()?) != 0xa000_0003
    {
        bail!("基础Python别名必须是NTFS mount-point junction");
    }
    let data_bytes = u16::from_le_bytes(bytes[4..6].try_into()?) as usize;
    let offset = u16::from_le_bytes(bytes[8..10].try_into()?) as usize;
    let length = u16::from_le_bytes(bytes[10..12].try_into()?) as usize;
    let start = 16usize.checked_add(offset).context("别名偏移溢出")?;
    let end = start.checked_add(length).context("别名长度溢出")?;
    if !offset.is_multiple_of(2)
        || length == 0
        || !length.is_multiple_of(2)
        || end > returned
        || end > 8 + data_bytes
    {
        bail!("基础Python别名重解析数据长度不合法");
    }
    let target = bytes[start..end]
        .chunks_exact(2)
        .map(|chunk| u16::from_le_bytes([chunk[0], chunk[1]]))
        .collect::<Vec<_>>();
    if target.contains(&0) {
        bail!("基础Python别名目标含NUL");
    }
    let target = OsString::from_wide(&target);
    let target = PathBuf::from(target);
    let text = target.to_str().context("基础Python别名目标不是UTF-8")?;
    let text = text
        .strip_prefix(r"\??\")
        .context("基础Python别名不是绝对NT目标")?;
    let target = PathBuf::from(text);
    if !target.is_absolute() {
        bail!("基础Python别名目标不是绝对路径");
    }
    Ok(Some(target))
}
fn allowed_alias(
    layout: &Layout,
    path: &Path,
    version_root: &Path,
    alias_roots: &[PathBuf],
) -> Result<bool> {
    if !alias_at(path, version_root) {
        return Ok(false);
    }
    layout.guard_path(version_root)?;
    #[cfg(windows)]
    {
        if let Some(target) = junction_target(path)? {
            if key(&target) != key(&version_root.join(PATCH))
                && !alias_roots
                    .iter()
                    .any(|root| key(&target) == key(&root.join(PATCH)))
            {
                bail!("基础Python minor别名不是事务中已知的固定patch");
            }
            return Ok(true);
        }
    }
    Ok(false)
}
fn tree(
    layout: &Layout,
    root: &Path,
    version_root: Option<&Path>,
    cancel: &CancelToken,
) -> Result<Tree> {
    tree_with_aliases(layout, root, version_root, &[], cancel)
}
fn tree_with_aliases(
    layout: &Layout,
    root: &Path,
    version_root: Option<&Path>,
    alias_roots: &[PathBuf],
    cancel: &CancelToken,
) -> Result<Tree> {
    #[allow(clippy::too_many_arguments)]
    fn walk(
        layout: &Layout,
        root: &Path,
        path: &Path,
        version: Option<&Path>,
        cancel: &CancelToken,
        hash: &mut Sha256,
        files: &mut u64,
        bytes: &mut u64,
        nodes: &mut u64,
        depth: usize,
        aliases: &[PathBuf],
        minor_alias: &mut bool,
    ) -> Result<()> {
        cancel.check()?;
        *nodes += 1;
        if *nodes > 200_000 || depth > 128 {
            bail!("修复保护树节点或深度超限");
        }
        let relative = path
            .strip_prefix(root)?
            .to_string_lossy()
            .replace('\\', "/");
        if let Some(version) = version {
            if allowed_alias(layout, path, version, aliases)? {
                *minor_alias = true;
                return Ok(());
            }
            if !aliases.is_empty() && alias_at(path, version) {
                layout.guard_path(path)?;
                if path.is_dir() && fs::read_dir(path)?.next().is_none() {
                    return Ok(());
                }
            }
        }
        hash.update((relative.len() as u64).to_le_bytes());
        hash.update(relative.as_bytes());
        layout.guard_path(path)?;
        let metadata = fs::symlink_metadata(path)?;
        if metadata.is_dir() {
            hash.update(b"directory\0");
            let mut children = fs::read_dir(path)?.collect::<std::io::Result<Vec<_>>>()?;
            if children.len() > 50_000 {
                bail!("修复目录项目过多");
            }
            children.sort_by_key(|entry| entry.file_name());
            let mut names = BTreeSet::new();
            for child in children {
                let name = child.file_name().to_string_lossy().into_owned();
                model::validate_component(&name)?;
                if !names.insert(name.to_ascii_lowercase()) {
                    bail!("修复保护树含大小写别名");
                }
                walk(
                    layout,
                    root,
                    &child.path(),
                    version,
                    cancel,
                    hash,
                    files,
                    bytes,
                    nodes,
                    depth + 1,
                    aliases,
                    minor_alias,
                )?;
            }
        } else {
            if !metadata.is_file() || metadata.len() > MAX_FILE {
                bail!("修复仅接受受限普通文件");
            }
            let mut input = File::open(path)?;
            let mut file_hash = Sha256::new();
            let mut total = 0u64;
            let mut buffer = [0; 65536];
            loop {
                cancel.check()?;
                let count = input.read(&mut buffer)?;
                if count == 0 {
                    break;
                }
                total += count as u64;
                if total > MAX_FILE {
                    bail!("修复文件读取超限");
                }
                file_hash.update(&buffer[..count]);
            }
            if total != metadata.len() {
                bail!("修复扫描期间文件长度变化");
            }
            *bytes = bytes.checked_add(total).context("修复扫描字节溢出")?;
            if *bytes > MAX_TREE {
                bail!("修复保护树超过8GiB，未授权变更");
            }
            *files += 1;
            hash.update(b"file\0");
            hash.update(total.to_le_bytes());
            hash.update(file_hash.finalize());
        }
        Ok(())
    }
    layout.guard_path(root)?;
    if !root.exists() {
        return Ok(Tree {
            exists: false,
            bytes: 0,
            files: 0,
            sha256: sha(b"absent"),
            minor_alias: false,
        });
    }
    let mut hash = Sha256::new();
    let mut bytes = 0;
    let mut files = 0;
    let mut minor_alias = false;
    walk(
        layout,
        root,
        root,
        version_root,
        cancel,
        &mut hash,
        &mut files,
        &mut bytes,
        &mut 0,
        0,
        alias_roots,
        &mut minor_alias,
    )?;
    Ok(Tree {
        exists: true,
        bytes,
        files,
        sha256: format!("{:x}", hash.finalize()),
        minor_alias,
    })
}
fn capture(layout: &Layout, references: &[Reference], cancel: &CancelToken) -> Result<Protection> {
    let mut roots = BTreeMap::new();
    for name in ["environments", "e", "releases", "tools", "config"] {
        roots.insert(
            PathBuf::from(name),
            tree(layout, &layout.root.join(name), None, cancel)?,
        );
    }
    let python = layout.root.join("python");
    layout.guard_path(&python)?;
    if python.exists() {
        for entry in fs::read_dir(&python)? {
            let entry = entry?;
            if entry.file_name() != "3.10.19" {
                let relative = entry.path().strip_prefix(&layout.root)?.to_path_buf();
                roots.insert(relative, tree(layout, &entry.path(), None, cancel)?);
            }
        }
    }
    let directory = layout.root.join("state/instances");
    layout.guard_path(&directory)?;
    let ids: BTreeSet<_> = references
        .iter()
        .map(|reference| reference.instance_id.as_str())
        .collect();
    let mut other_states = BTreeMap::new();
    if directory.exists() {
        for entry in fs::read_dir(&directory)? {
            let path = entry?.path();
            let id = path
                .file_stem()
                .and_then(|value| value.to_str())
                .context("实例记录名称无效")?;
            if !ids.contains(id) {
                other_states.insert(
                    path.strip_prefix(&layout.root)?.into(),
                    sha(&read_small(layout, &path, MAX_DETAIL)?),
                );
            }
        }
    }
    let state_root = layout.root.join("state");
    if state_root.exists() {
        for entry in fs::read_dir(&state_root)? {
            let entry = entry?;
            if !matches!(
                entry.file_name().to_str(),
                Some(
                    "instances"
                        | "operations"
                        | "registry.json"
                        | "base-python-repair.json"
                        | "download-budget.json"
                        | "download-budget-enrollment.json"
                        | "download-receipts"
                )
            ) {
                roots.insert(
                    entry.path().strip_prefix(&layout.root)?.into(),
                    tree(layout, &entry.path(), None, cancel)?,
                );
            }
        }
    }
    Ok(Protection {
        roots,
        profiles: instances::summarize_profiles(layout, cancel)?,
        other_states,
    })
}
fn pyvenv_reference(layout: &Layout, environment: &Path) -> Result<bool> {
    let path = environment.join("pyvenv.cfg");
    let bytes = read_small(layout, &path, 64 * 1024)?;
    let text = std::str::from_utf8(&bytes).context("pyvenv.cfg不是UTF-8")?;
    let mut homes = Vec::new();
    for line in text.lines() {
        if let Some((name, value)) = line.split_once('=') {
            if matches!(
                name.trim().to_ascii_lowercase().as_str(),
                "home" | "base-prefix" | "base-executable"
            ) {
                homes.push(PathBuf::from(value.trim()));
            }
        }
    }
    if homes.is_empty() {
        bail!("pyvenv.cfg缺少基础Python归属");
    }
    let expected = key(&layout.root.join(TARGET));
    let matches = homes
        .iter()
        .map(|home| {
            let value = key(home);
            value == expected || value.starts_with(&(expected.clone() + "\\"))
        })
        .collect::<Vec<_>>();
    if matches.iter().any(|value| *value) && matches.iter().any(|value| !value) {
        bail!("pyvenv.cfg包含混合基础Python归属");
    }
    Ok(matches.iter().all(|value| *value))
}
fn discover(
    layout: &Layout,
    catalog: &Catalog,
    registry: &Registry,
) -> Result<(Vec<Reference>, Vec<String>)> {
    let mut references = Vec::new();
    let mut blockers = Vec::new();
    let mut known = BTreeSet::new();
    let directory = layout.root.join("state/instances");
    layout.guard_path(&directory)?;
    if directory.exists() {
        let entries = fs::read_dir(&directory)?.collect::<std::io::Result<Vec<_>>>()?;
        if entries.len() > 500 {
            bail!("受管实例记录超过500项");
        }
        for entry in entries {
            let path = entry.path();
            let outcome = (|| -> Result<Option<Reference>> {
                let id = path
                    .file_stem()
                    .and_then(|value| value.to_str())
                    .context("实例名称无效")?;
                if path.extension().is_none_or(|ext| ext != "json") {
                    bail!("实例目录存在未知文件");
                }
                let bytes = read_small(layout, &path, MAX_DETAIL)?;
                let value: serde_json::Value = serde_json::from_slice(&bytes)?;
                let owner = value
                    .get("release_id")
                    .and_then(|value| value.as_str())
                    .context("实例缺release身份")?;
                let release = catalog.release(owner)?;
                let owner_layout = Layout::new(&layout.root, owner)?;
                let state = instances::load(&owner_layout, id)?;
                let environment = instances::path(&state)?;
                known.insert(key(&environment));
                if release.python != "3.10.19" {
                    if environment.join("pyvenv.cfg").exists()
                        && pyvenv_reference(layout, &environment)?
                    {
                        bail!("实例基础Python实际引用与release声明不符");
                    }
                    return Ok(None);
                }
                if release.environment_recipe != "gui-cp310-win-x64-v1" {
                    bail!("引用没有支持的固定GUI验证器");
                }
                let recipe_sha = sha(include_bytes!("../../catalog/gui-cp310-win-x64-v1.json"));
                if state.recipe_id() != "gui-cp310-win-x64-v1"
                    || state.recipe_sha256() != recipe_sha
                {
                    bail!("引用实例不是当前完整固定GUI配方身份");
                }
                let initial_dirty = instances::base_reference_initial_dirty(&state)?;
                instances::base_reference_validate_before(&owner_layout, &state)?;
                // New install orphans can fail before a venv exists; they still reference the recipe base.
                if environment.join("pyvenv.cfg").exists() {
                    if !pyvenv_reference(layout, &environment)? {
                        bail!("实例pyvenv归属与固定配方不符");
                    }
                } else if !initial_dirty {
                    bail!("clean引用缺pyvenv.cfg");
                }
                let binding = registry
                    .gui_binding(owner)
                    .filter(|binding| binding.instance_id == id)
                    .cloned();
                if let Some(binding) = &binding {
                    if binding.generation != state.generation()
                        || binding.storage_version != state.storage_version()
                        || binding.recipe_id != state.recipe_id()
                        || binding.recipe_sha256 != state.recipe_sha256()
                    {
                        bail!("引用binding与持久实例不一致");
                    }
                }
                Ok(Some(Reference {
                    release_id: owner.into(),
                    instance_id: id.into(),
                    storage_version: state.storage_version(),
                    environment: environment.strip_prefix(&layout.root)?.into(),
                    generation: state.generation(),
                    initial_dirty,
                    state_sha256: instances::base_reference_sha(&state)?,
                    binding,
                }))
            })();
            match outcome {
                Ok(Some(reference)) => references.push(reference),
                Ok(None) => {}
                Err(error) => blockers.push(format!(
                    "实例 {}: {error:#}",
                    path.file_name().unwrap_or_default().to_string_lossy()
                )),
            }
        }
    }
    for installed in &registry.installed {
        let release = match catalog.release(&installed.release_id) {
            Ok(release) => release,
            Err(error) => {
                blockers.push(format!(
                    "登记版本 {} 无法归属可信目录: {error:#}",
                    installed.release_id
                ));
                continue;
            }
        };
        if release.python == "3.10.19" {
            if let Some(binding) = &installed.gui {
                if !references.iter().any(|reference| {
                    reference.instance_id == binding.instance_id
                        && reference.release_id == installed.release_id
                }) {
                    blockers.push(format!(
                        "已绑定引用 {} 未通过完整发现",
                        installed.release_id
                    ));
                }
            } else {
                let environment = layout
                    .root
                    .join("environments")
                    .join(&installed.release_id)
                    .join("gui");
                if environment.exists() {
                    blockers.push(format!(
                        "旧无实例协议环境 {} 需要独立验证器，当前不接管",
                        installed.release_id
                    ));
                }
            }
        }
    }
    // Scan only managed namespaces. Any unregistered venv that references this base blocks repair.
    fn scan_venvs(
        layout: &Layout,
        path: &Path,
        known: &BTreeSet<String>,
        blockers: &mut Vec<String>,
        nodes: &mut usize,
        depth: usize,
    ) -> Result<()> {
        *nodes += 1;
        if *nodes > 50_000 || depth > 16 {
            bail!("受管引用发现超限");
        }
        layout.guard_path(path)?;
        if !path.exists() {
            return Ok(());
        }
        if !path.is_dir() {
            return Ok(());
        }
        if path.join("pyvenv.cfg").exists() {
            if !known.contains(&key(path)) && pyvenv_reference(layout, path)? {
                blockers.push(format!(
                    "未登记受管环境引用基础Python: {}",
                    path.strip_prefix(&layout.root)?.display()
                ));
            }
            return Ok(());
        }
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            layout.guard_path(&entry.path())?;
            if entry.file_type()?.is_dir() {
                scan_venvs(layout, &entry.path(), known, blockers, nodes, depth + 1)?;
            }
        }
        Ok(())
    }
    for name in ["environments", "e"] {
        if let Err(error) = scan_venvs(
            layout,
            &layout.root.join(name),
            &known,
            &mut blockers,
            &mut 0,
            0,
        ) {
            blockers.push(format!("受管命名空间 {name} 引用发现未完成: {error:#}"));
        }
    }
    references.sort_by(|a, b| a.instance_id.cmp(&b.instance_id));
    blockers.sort();
    blockers.dedup();
    Ok((references, blockers))
}
fn plan(root: &Path, catalog: &Catalog, cancel: &CancelToken) -> Result<Plan> {
    let release = catalog
        .releases()
        .iter()
        .find(|release| release.environment_recipe == "gui-cp310-win-x64-v1")
        .context("无固定GUI候选")?;
    let layout = Layout::new(root, &release.id)?;
    let registry = Registry::load(root)?;
    let existing = read_intent(&layout);
    let (references, mut blockers) = match &existing {
        Ok(Some(intent)) if intent.phase != Phase::Committed => match details(&layout, intent) {
            Ok(details) => (details.plan.references, Vec::new()),
            Err(error) => (Vec::new(), vec![format!("持久引用闭包不可识别: {error:#}")]),
        },
        _ => match discover(&layout, catalog, &registry) {
            Ok(discovery) => discovery,
            Err(error) => (Vec::new(), vec![format!("引用发现未完成: {error:#}")]),
        },
    };
    let before = match tree(
        &layout,
        &root.join(TARGET),
        Some(&root.join(TARGET)),
        cancel,
    ) {
        Ok(tree) => Some(tree),
        Err(error) => {
            blockers.push(format!("基础Python现场不可安全保护: {error:#}"));
            None
        }
    };
    let protection = match capture(&layout, &references, cancel) {
        Ok(protection) => Some(protection),
        Err(error) => {
            blockers.push(format!("非目标保护不可完成: {error:#}"));
            None
        }
    };
    let integrity_error = crate::python_integrity::verify(&layout)
        .err()
        .map(|error| format!("{error:#}"));
    if registry.base_python_pending.is_some() {
        blockers.push("已有基础Python事务，请恢复既有操作".into());
    }
    let (recovery_available, recovery_error) = match existing {
        Ok(Some(intent)) if intent.phase != Phase::Committed => match details(&layout, &intent) {
            Ok(_) => (true, None),
            Err(error) => (false, Some(format!("{error:#}"))),
        },
        Ok(Some(_)) => (false, None),
        Ok(None) => (false, None),
        Err(error) => (false, Some(format!("{error:#}"))),
    };
    if recovery_available {
        blockers.push("存在未完成基础Python修复，请恢复原事务".into());
    }
    if let Some(error) = &recovery_error {
        blockers.push(format!("基础Python事务不可识别，保留现场: {error}"));
    }
    let repair_available = blockers.is_empty();
    let mut result = Plan { schema_version: 1, component_id: COMPONENT.into(), root: root.into(), target: TARGET.into(),
        replacement_scope: "仅替换固定基础Python组件；所有环境原字节保持，受影响引用停用并逐项复验；不重装wheel或venv".into(),
        expected_files: crate::python_integrity::trusted_paths()?, integrity_error, references, blockers, before, protection,
        registry_sha256: sha(&serde_json::to_vec(&registry)?), pending_transaction: registry.base_python_pending.clone(),
        repair_available, recovery_available, recovery_error, plan_sha256: String::new() };
    result.plan_sha256 = sha(&serde_json::to_vec(&result)?);
    Ok(result)
}
pub(super) fn preview(root: &Path, catalog: &Catalog) -> Result<serde_json::Value> {
    Ok(serde_json::to_value(plan(
        root,
        catalog,
        &CancelToken::new(),
    )?)?)
}
/// Lease holders and startup probes must check both durable sides of the gate.
/// An intent can precede Registry's first write, and can outlive its final write.
pub(super) fn assert_ready(root: &Path) -> Result<()> {
    Registry::load(root)?.assert_base_python_ready()?;
    let layout = Layout::new(root, &format!("dev-{}", "0".repeat(40)))?;
    if let Some(intent) = read_intent(&layout)? {
        if intent.phase != Phase::Committed {
            bail!("基础Python引用闭包事务尚未完成，请先恢复原操作");
        }
    }
    Ok(())
}

fn transaction_directory(transaction: &str) -> Result<PathBuf> {
    model::validate_component(transaction)?;
    if !transaction.starts_with("base-python-") || transaction.len() > 96 {
        bail!("基础Python事务身份无效");
    }
    Ok(PathBuf::from("backups").join(transaction))
}
fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn validate_intent(layout: &Layout, intent: &Intent) -> Result<()> {
    let directory = transaction_directory(&intent.transaction)?;
    if intent.schema_version != 1
        || intent.component_id != COMPONENT
        || intent.root != layout.root
        || intent.details != directory.join("details.json")
        || intent.backup != directory.join("base-before")
        || intent.previous != directory.join("previous-published")
        || intent.staging
            != PathBuf::from("staging")
                .join(&intent.transaction)
                .join("python")
        || !valid_sha(&intent.details_sha256)
        || !valid_sha(&intent.before.sha256)
        || !valid_sha(&intent.staged.sha256)
        || !intent.staged.exists
        || intent.candidates.len() > 500
    {
        bail!("基础Python事务schema、根路径或固定发布身份不受支持");
    }
    for (id, digest) in &intent.candidates {
        model::validate_component(id)?;
        if !valid_sha(digest) {
            bail!("引用候选摘要无效");
        }
    }
    for path in [
        &intent.details,
        &intent.backup,
        &intent.previous,
        &intent.staging,
    ] {
        layout.guard_path(&layout.root.join(path))?;
    }
    Ok(())
}
fn read_intent(layout: &Layout) -> Result<Option<Intent>> {
    let path = layout.root.join(RECORD);
    layout.guard_path(&path)?;
    if !path.exists() {
        return Ok(None);
    }
    let intent: Intent = serde_json::from_slice(&read_small(layout, &path, MAX_RECORD)?)?;
    validate_intent(layout, &intent)?;
    Ok(Some(intent))
}
fn store_intent(layout: &Layout, intent: &Intent) -> Result<()> {
    validate_intent(layout, intent)?;
    if let Some(current) = read_intent(layout)? {
        if current.transaction != intent.transaction {
            if current.phase != Phase::Committed || intent.phase != Phase::Prepared {
                bail!("未知或未完成基础Python事务禁止覆盖");
            }
        } else if current.details_sha256 != intent.details_sha256
            || current.before != intent.before
            || current.staged != intent.staged
        {
            bail!("基础Python持久事务不可变身份变化，拒绝覆盖");
        }
    }
    if serde_json::to_vec_pretty(intent)?.len() as u64 + 1 > MAX_RECORD {
        bail!("基础Python事务记录过大");
    }
    model::write_base_json_atomic(
        &layout.root,
        &intent.transaction,
        &layout.root.join(RECORD),
        intent,
    )
}
fn details(layout: &Layout, intent: &Intent) -> Result<Details> {
    let bytes = read_small(layout, &layout.root.join(&intent.details), MAX_DETAIL)?;
    if sha(&bytes) != intent.details_sha256 {
        bail!("基础Python不可变计划摘要不符");
    }
    let details: Details = serde_json::from_slice(&bytes)?;
    let mut original_plan = details.plan.clone();
    let expected = original_plan.plan_sha256.clone();
    original_plan.plan_sha256.clear();
    if details.schema_version != 1
        || details.transaction != intent.transaction
        || details.plan.root != layout.root
        || details.plan.component_id != COMPONENT
        || details.plan.target != Path::new(TARGET)
        || !details.plan.blockers.is_empty()
        || details.plan.before.as_ref() != Some(&intent.before)
        || sha(&serde_json::to_vec(&original_plan)?) != expected
        || sha(&serde_json::to_vec(&details.registry_before)?) != details.plan.registry_sha256
        || details.registry_disabled
            != disabled_registry(
                &details.registry_before,
                &details.plan.references,
                &intent.transaction,
            )?
        || details.original_states.len() != details.plan.references.len()
    {
        bail!("基础Python不可变计划身份不符");
    }
    details.registry_before.validate()?;
    details.registry_disabled.validate()?;
    for reference in &details.plan.references {
        model::validate_component(&reference.instance_id)?;
        model::validate_release_id(&reference.release_id)?;
        let expected_path = model::environment_path(
            &layout.root,
            &reference.release_id,
            &reference.instance_id,
            reference.storage_version,
        )?;
        if expected_path.strip_prefix(&layout.root)? != reference.environment
            || !valid_sha(&reference.state_sha256)
            || !details
                .original_states
                .get(&reference.instance_id)
                .is_some_and(|digest| valid_sha(digest))
        {
            bail!("基础Python引用记录路径或摘要无效");
        }
    }
    Ok(details)
}
fn disabled_registry(
    before: &Registry,
    references: &[Reference],
    transaction: &str,
) -> Result<Registry> {
    let mut result = before.clone();
    result.schema_version = 3;
    result.base_python_pending = Some(transaction.into());
    for record in &mut result.installed {
        if references
            .iter()
            .any(|reference| reference.release_id == record.release_id)
        {
            record.healthy_at = None;
            if result.previous_known_good.as_deref() == Some(&record.release_id) {
                result.previous_known_good = None;
            }
        }
    }
    result.validate()?;
    Ok(result)
}
fn completed_registry(details: &Details) -> Result<Registry> {
    let mut registry = details.registry_disabled.clone();
    for reference in &details.plan.references {
        if let Some(binding) = &reference.binding {
            let record = registry
                .installed
                .iter_mut()
                .find(|record| record.release_id == reference.release_id)
                .context("计划绑定版本消失")?;
            let mut updated = binding.clone();
            if !reference.initial_dirty {
                updated.generation = reference
                    .generation
                    .checked_add(1)
                    .context("引用generation溢出")?;
            }
            record.gui = Some(updated);
            record.healthy_at = None;
        }
    }
    registry.base_python_pending = None;
    registry.validate()?;
    Ok(registry)
}
fn assert_protection(layout: &Layout, details: &Details, cancel: &CancelToken) -> Result<()> {
    if Some(capture(layout, &details.plan.references, cancel)?) != details.plan.protection {
        bail!("环境、profiles、源码、工具或其它Python原字节变化；保留dirty与全部现场");
    }
    Ok(())
}
fn assert_originals(layout: &Layout, intent: &Intent, details: &Details) -> Result<()> {
    let directory = layout
        .root
        .join(transaction_directory(&intent.transaction)?);
    if let Some(digest) = &details.original_registry_sha256 {
        if sha(&read_small(
            layout,
            &directory.join("registry-before.json"),
            MAX_DETAIL,
        )?) != *digest
        {
            bail!("版本登记原字节独立备份损坏");
        }
    }
    for (id, digest) in &details.original_states {
        if sha(&read_small(
            layout,
            &directory.join("states-before").join(format!("{id}.json")),
            MAX_DETAIL,
        )?) != *digest
        {
            bail!("引用实例原字节独立备份损坏");
        }
    }
    Ok(())
}
fn report(
    ctx: &WorkspaceMutation,
    operation: &OperationHandle,
    phase: OperationPhase,
    message: &str,
) -> Result<()> {
    operation.cancel_token().check()?;
    operation.publish(phase, message)?;
    operation.persist(ctx)
}
fn make_alias(layout: &Layout, root: &Path, target_root: &Path) -> Result<()> {
    layout.guard_path(root)?;
    layout.guard_path(&target_root.join(PATCH))?;
    let alias = root.join(ALIAS);
    #[cfg(windows)]
    {
        if let Some(target) = junction_target(&alias)? {
            if key(&target) != key(&target_root.join(PATCH)) {
                bail!("minor别名已有未知目标，拒绝覆盖");
            }
            return Ok(());
        }
        layout.guard_path(&alias)?;
        if alias.exists() {
            if fs::read_dir(&alias)?.next().is_some() {
                bail!("minor别名路径存在未知内容");
            }
            fs::remove_dir(&alias)?;
        }
        junction::create(target_root.join(PATCH), &alias)?;
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = alias;
        bail!("基础Python组件发布仅支持Windows")
    }
}
fn remove_known_alias(layout: &Layout, root: &Path, accepted: &[PathBuf]) -> Result<()> {
    layout.guard_path(root)?;
    let alias = root.join(ALIAS);
    #[cfg(windows)]
    {
        if let Some(target) = junction_target(&alias)? {
            if !accepted
                .iter()
                .any(|value| key(&target) == key(&value.join(PATCH)))
            {
                bail!("minor别名目标未知，拒绝改动");
            }
            junction::delete(&alias)?;
            fs::remove_dir(&alias)?;
        } else {
            layout.guard_path(&alias)?;
            if alias.exists() {
                if fs::read_dir(&alias)?.next().is_some() {
                    bail!("minor别名空目录出现未知内容");
                }
                fs::remove_dir(&alias)?;
            }
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = (alias, accepted);
        Ok(())
    }
}
// Every backup is an independent copy. A killed copy can resume only when its partial
// file is an exact prefix of the still-unchanged source; foreign bytes never get erased.
fn copy_snapshot(
    layout: &Layout,
    source: &Path,
    destination: &Path,
    cancel: &CancelToken,
) -> Result<()> {
    fn copy(
        layout: &Layout,
        source_root: &Path,
        source: &Path,
        destination: &Path,
        cancel: &CancelToken,
    ) -> Result<()> {
        cancel.check()?;
        if allowed_alias(layout, source, source_root, &[])? {
            return Ok(());
        }
        layout.guard_path(source)?;
        layout.guard_path(destination)?;
        let metadata = fs::symlink_metadata(source)?;
        if metadata.is_dir() {
            layout.ensure_dir(destination)?;
            for entry in fs::read_dir(source)? {
                let entry = entry?;
                copy(
                    layout,
                    source_root,
                    &entry.path(),
                    &destination.join(entry.file_name()),
                    cancel,
                )?;
            }
        } else {
            if !metadata.is_file() || metadata.len() > MAX_FILE {
                bail!("快照来源不是受限普通文件");
            }
            if destination.exists() {
                let existing = fs::symlink_metadata(destination)?;
                if !existing.is_file() || existing.len() > metadata.len() {
                    bail!("快照出现未知文件，拒绝覆盖");
                }
                let mut a = File::open(source)?;
                let mut b = File::open(destination)?;
                let mut left = [0; 65536];
                let mut right = [0; 65536];
                loop {
                    cancel.check()?;
                    let count = b.read(&mut right)?;
                    if count == 0 {
                        break;
                    }
                    a.read_exact(&mut left[..count])?;
                    if left[..count] != right[..count] {
                        bail!("快照已写片段与原始字节不符");
                    }
                }
                if existing.len() == metadata.len() {
                    return Ok(());
                }
            }
            let mut input = File::open(source)?;
            let mut output = OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(true)
                .open(destination)?;
            let mut buffer = [0; 65536];
            let mut total = 0u64;
            loop {
                cancel.check()?;
                let count = input.read(&mut buffer)?;
                if count == 0 {
                    break;
                }
                total += count as u64;
                if total > MAX_FILE {
                    bail!("快照复制文件超限");
                }
                output.write_all(&buffer[..count])?;
            }
            output.sync_all()?;
            if total != metadata.len() {
                bail!("快照复制期间文件变化");
            }
        }
        Ok(())
    }
    if source.exists() {
        copy(layout, source, source, destination, cancel)?;
        if allowed_alias(layout, &source.join(ALIAS), source, &[])? {
            make_alias(layout, destination, destination)?;
        }
    }
    Ok(())
}
fn prepare_candidate(
    ctx: &WorkspaceMutation,
    staging: &Path,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<Tree> {
    let layout = ctx.layout();
    let recipe = GuiRecipe::embedded()?;
    layout.guard_path(&super::uv(&layout.root))?;
    if super::digest(&super::uv(&layout.root))? != recipe.tool_uv.exe_sha256 {
        bail!("基础Python修复需要身份匹配的固定uv工具；不会替换受保护工具");
    }
    report(
        ctx,
        operation,
        OperationPhase::Downloading,
        "获取固定基础Python组件归档",
    )?;
    let archive = super::gui_install::download(
        ctx,
        &recipe,
        operation,
        &recipe.python.archive.url,
        &recipe.python.archive.filename,
        &recipe.python.archive.sha256,
        recipe.python.archive.bytes,
    )?;
    let mirror = layout
        .root
        .join("cache/python-mirror")
        .join(&recipe.python.build);
    layout.ensure_dir(&mirror)?;
    let mirror_archive = mirror.join(&recipe.python.archive.filename);
    layout.guard_path(&mirror_archive)?;
    if mirror_archive.exists() {
        if super::digest(&mirror_archive)? != recipe.python.archive.sha256 {
            bail!("基础Python本地镜像摘要不符；保留原文件");
        }
    } else {
        fs::copy(archive, &mirror_archive)?;
    }
    let mirror_url =
        reqwest::Url::from_directory_path(mirror.parent().context("基础Python镜像缺父目录")?)
            .map_err(|_| anyhow::anyhow!("本地镜像URL无效"))?;
    layout.ensure_dir(staging)?;
    let mut command = super::gui_install::command(&layout.root, &recipe);
    command
        .env("UV_PYTHON_INSTALL_DIR", staging)
        .env("UV_PYTHON_DOWNLOADS", "manual")
        .args([
            "python",
            "install",
            &recipe.python.version,
            "--no-bin",
            "--no-registry",
            "--mirror",
            mirror_url.as_str(),
        ]);
    report(
        ctx,
        operation,
        OperationPhase::Executing,
        "在独立目录离线准备固定基础Python候选",
    )?;
    super::execute_controlled(command, log, &operation.cancel_token())?;
    crate::python_integrity::verify_at(layout, staging)?;
    tree(layout, staging, Some(staging), &operation.cancel_token())
}

fn same_payload(left: &Tree, right: &Tree) -> bool {
    left.exists == right.exists
        && left.bytes == right.bytes
        && left.files == right.files
        && left.sha256 == right.sha256
}
fn ensure_snapshot(layout: &Layout, intent: &mut Intent, cancel: &CancelToken) -> Result<()> {
    let target = layout.root.join(TARGET);
    let backup = layout.root.join(&intent.backup);
    if intent.snapshot_complete {
        if tree(layout, &backup, Some(&backup), cancel)? != intent.before {
            bail!("基础Python独立快照摘要不符；拒绝恢复");
        }
        return Ok(());
    }
    if tree(layout, &target, Some(&target), cancel)? != intent.before {
        bail!("独立快照完成前基础Python已变化；保留现场");
    }
    copy_snapshot(layout, &target, &backup, cancel)?;
    if tree(layout, &backup, Some(&backup), cancel)? != intent.before
        || tree(layout, &target, Some(&target), cancel)? != intent.before
    {
        bail!("基础Python独立快照复制或原始树摘要不符");
    }
    intent.snapshot_complete = true;
    store_intent(layout, intent)
}
fn publish(layout: &Layout, intent: &mut Intent, cancel: &CancelToken) -> Result<()> {
    let target = layout.root.join(TARGET);
    let staging = layout.root.join(&intent.staging);
    let previous = layout.root.join(&intent.previous);
    let backup = layout.root.join(&intent.backup);
    let aliases = vec![
        target.clone(),
        staging.clone(),
        previous.clone(),
        backup.clone(),
    ];
    if !intent.snapshot_complete || tree(layout, &backup, Some(&backup), cancel)? != intent.before {
        bail!("发布前独立快照缺失或不符");
    }
    let current = tree_with_aliases(layout, &target, Some(&target), &aliases, cancel)?;
    let previous_tree = tree_with_aliases(layout, &previous, Some(&previous), &aliases, cancel)?;
    if previous_tree.exists && previous_tree != intent.before {
        bail!("旧发布位置出现未知字节或别名；拒绝恢复");
    }
    if !same_payload(&current, &intent.staged) {
        if current.exists {
            if current != intent.before || previous_tree.exists {
                bail!("基础Python不是计划原树或可信新树；拒绝覆盖");
            }
            cancel.check()?;
            fs::rename(&target, &previous)?;
        } else if intent.before.exists && !same_payload(&previous_tree, &intent.before) {
            bail!("基础Python发布窗口缺少已知旧树");
        }
        let candidate = tree_with_aliases(layout, &staging, Some(&staging), &aliases, cancel)?;
        if candidate != intent.staged {
            bail!("基础Python候选目录缺失或摘要不符");
        }
        cancel.check()?;
        fs::rename(&staging, &target)?;
    }
    // A process can die between junction::delete and remove_dir, or after rename.
    // Only the fixed, empty alias path and the intent's exact roots are admitted.
    remove_known_alias(layout, &target, &aliases)?;
    if intent.staged.minor_alias {
        make_alias(layout, &target, &target)?;
    }
    crate::python_integrity::verify_at(layout, &target)?;
    if tree(layout, &target, Some(&target), cancel)? != intent.staged {
        bail!("同路径发布后的完整Python闭包不符");
    }
    intent.phase = Phase::Published;
    store_intent(layout, intent)
}
fn candidate_path(layout: &Layout, intent: &Intent, id: &str) -> Result<PathBuf> {
    model::validate_component(id)?;
    Ok(layout
        .root
        .join(transaction_directory(&intent.transaction)?)
        .join("candidates")
        .join(format!("{id}.json")))
}
fn save_candidate(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    layout.guard_path(path)?;
    if path.exists() {
        if read_small(layout, path, MAX_DETAIL)? != bytes {
            bail!("已持久引用候选不同；保留现场");
        }
    } else {
        let parent = path.parent().context("引用候选没有父目录")?;
        layout.ensure_dir(parent)?;
        let temporary = parent.join(format!(
            ".candidate-{}-{}-{}.tmp",
            std::process::id(),
            super::stamp(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        // A killed write leaves only this uniquely named unpublished temporary.
        // Keep such evidence; the final candidate is published only after fsync.
        write_new(layout, &temporary, bytes)?;
        if read_small(layout, &temporary, MAX_DETAIL)? != bytes {
            bail!("引用候选临时文件摘要不同；保留现场");
        }
        publish_new_file(&temporary, path)?;
    }
    Ok(())
}
#[cfg(windows)]
fn publish_new_file(temporary: &Path, target: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, new: *const u16, flags: u32) -> i32;
    }
    let temporary = temporary
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    let target = target
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    // No REPLACE_EXISTING: an unexpected destination remains untouched.
    if unsafe { MoveFileExW(temporary.as_ptr(), target.as_ptr(), 0x8) } == 0 {
        return Err(std::io::Error::last_os_error())
            .context("引用候选原子发布失败，临时文件与原目标均保留");
    }
    Ok(())
}
#[cfg(not(windows))]
fn publish_new_file(temporary: &Path, target: &Path) -> Result<()> {
    if target.exists() {
        bail!("引用候选目标已存在，拒绝覆盖");
    }
    fs::rename(temporary, target)?;
    File::open(target.parent().context("引用候选缺父目录")?)?.sync_all()?;
    Ok(())
}
fn drive(
    ctx: &WorkspaceMutation,
    catalog: &Catalog,
    intent: &mut Intent,
    operation: &OperationHandle,
    validator: &mut Validator<'_>,
) -> Result<()> {
    let layout = ctx.layout();
    let cancel = operation.cancel_token();
    let details = details(layout, intent)?;
    assert_originals(layout, intent, &details)?;
    if intent.phase == Phase::Committed {
        bail!("基础Python事务已经提交，无需再次恢复");
    }
    assert_protection(layout, &details, &cancel)?;
    if intent.phase == Phase::Prepared {
        report(
            ctx,
            operation,
            OperationPhase::Preparing,
            "停用全部基础Python引用，建立持久引用闭包",
        )?;
        let registry = Registry::load(&layout.root)?;
        if registry == details.registry_before {
            details
                .registry_disabled
                .store_for_base(&layout.root, &intent.transaction)?;
        } else if registry != details.registry_disabled {
            bail!("停用引用前版本登记变化；保留现场");
        }
        for reference in &details.plan.references {
            cancel.check()?;
            let owner = Layout::new(&layout.root, &reference.release_id)?;
            instances::quarantine_for_base(
                &owner,
                &reference.instance_id,
                &reference.state_sha256,
                &intent.transaction,
            )?;
        }
        intent.phase = Phase::Quarantined;
        store_intent(layout, intent)?;
    }
    let expected_registry = completed_registry(&details)?;
    let current_registry = Registry::load(&layout.root)?;
    if current_registry != details.registry_disabled
        && !(intent.phase == Phase::Committing && current_registry == expected_registry)
    {
        bail!("基础Python事务全局gate或版本登记不同；拒绝恢复");
    }
    if intent.phase == Phase::Quarantined {
        report(
            ctx,
            operation,
            OperationPhase::Preparing,
            "独立复制基础Python原始字节快照",
        )?;
        ensure_snapshot(layout, intent, &cancel)?;
        assert_protection(layout, &details, &cancel)?;
        intent.phase = Phase::Snapshotted;
        store_intent(layout, intent)?;
    }
    if intent.phase == Phase::Snapshotted {
        ensure_snapshot(layout, intent, &cancel)?;
        if tree(
            layout,
            &layout.root.join(TARGET),
            Some(&layout.root.join(TARGET)),
            &cancel,
        )? != intent.before
        {
            bail!("发布前原始基础Python已变化");
        }
        intent.phase = Phase::Publishing;
        store_intent(layout, intent)?;
    }
    if intent.phase == Phase::Publishing {
        report(
            ctx,
            operation,
            OperationPhase::Executing,
            "在同一绝对路径发布固定基础Python组件",
        )?;
        publish(layout, intent, &cancel)?;
    }
    if matches!(
        intent.phase,
        Phase::Published | Phase::Validated | Phase::Committing
    ) {
        ensure_snapshot(layout, intent, &cancel)?;
        crate::python_integrity::verify(layout)?;
        if tree(
            layout,
            &layout.root.join(TARGET),
            Some(&layout.root.join(TARGET)),
            &cancel,
        )? != intent.staged
        {
            bail!("待恢复基础Python不再是已发布可信树");
        }
    }
    if intent.phase == Phase::Published {
        report(
            ctx,
            operation,
            OperationPhase::Verifying,
            "逐个复验全部引用环境，保持完整引用闭包停用",
        )?;
        for reference in &details.plan.references {
            cancel.check()?;
            let release = catalog.release(&reference.release_id)?;
            let owner = Layout::new(&layout.root, &reference.release_id)?;
            assert_protection(layout, &details, &cancel)?;
            let bytes = instances::candidate_after_base(
                &owner,
                &reference.instance_id,
                &intent.transaction,
                &cancel,
                |environment| validator(&owner, release, environment, &cancel),
            )?;
            assert_protection(layout, &details, &cancel)?;
            let path = candidate_path(layout, intent, &reference.instance_id)?;
            save_candidate(layout, &path, &bytes)?;
            intent
                .candidates
                .insert(reference.instance_id.clone(), sha(&bytes));
            store_intent(layout, intent)?;
        }
        intent.phase = Phase::Validated;
        store_intent(layout, intent)?;
    }
    if intent.phase == Phase::Validated {
        if intent.candidates.len() != details.plan.references.len() {
            bail!("引用闭包未全部复验，不允许部分提交");
        }
        assert_protection(layout, &details, &cancel)?;
        intent.phase = Phase::Committing;
        store_intent(layout, intent)?;
    }
    if intent.phase == Phase::Committing {
        report(
            ctx,
            operation,
            OperationPhase::Committing,
            "提交全部引用generation后，一次解除基础Python组件停用",
        )?;
        for reference in &details.plan.references {
            cancel.check()?;
            let bytes = read_small(
                layout,
                &candidate_path(layout, intent, &reference.instance_id)?,
                MAX_DETAIL,
            )?;
            if intent.candidates.get(&reference.instance_id) != Some(&sha(&bytes)) {
                bail!("持久引用候选SHA不符");
            }
            let owner = Layout::new(&layout.root, &reference.release_id)?;
            instances::commit_after_base(
                &owner,
                &reference.instance_id,
                &intent.transaction,
                &bytes,
            )?;
        }
        assert_protection(layout, &details, &cancel)?;
        crate::python_integrity::verify(layout)?;
        cancel.check()?;
        let registry = Registry::load(&layout.root)?;
        if registry == details.registry_disabled {
            expected_registry.store_for_base(&layout.root, &intent.transaction)?;
        } else if registry != expected_registry {
            bail!("最终组件提交前版本登记变化，保留全局停用");
        }
        // Once the gate is removed the transaction is durably complete. A late cancel
        // cannot relabel clean, committed references as a rolled back bad base.
        intent.phase = Phase::Committed;
        store_intent(layout, intent)?;
    }
    Ok(())
}
fn finish(ctx: &WorkspaceMutation, operation: &OperationHandle, result: &Result<()>) -> Result<()> {
    let (status, error) = match result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
            (OperationStatus::Cancelled, None)
        }
        Err(error) => (
            OperationStatus::Failed,
            Some(OperationError {
                code: "base_python_repair_failed".into(),
                message: format!("{error:#}"),
            }),
        ),
    };
    operation.finish_and_persist(ctx, status, error)
}
pub(super) fn execute(
    ctx: &WorkspaceMutation,
    catalog: &Catalog,
    plan_sha256: &str,
    operation: &OperationHandle,
    log: &super::Logger,
    validator: &mut Validator<'_>,
) -> Result<()> {
    operation.persist(ctx)?;
    let result = (|| -> Result<()> {
        let layout = ctx.layout();
        let cancel = operation.cancel_token();
        let plan = plan(&layout.root, catalog, &cancel)?;
        if plan.plan_sha256 != plan_sha256 || !plan.repair_available || !plan.blockers.is_empty() {
            bail!("基础Python修复预览已变化或存在阻断；请刷新并查看完整引用闭包");
        }
        let material = format!(
            "{}:{}:{}:{}",
            layout.root.display(),
            super::stamp(),
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        );
        let transaction = format!("base-python-{}", &sha(material.as_bytes())[..24]);
        let directory = layout.root.join(transaction_directory(&transaction)?);
        let staging = PathBuf::from("staging").join(&transaction).join("python");
        let staged = prepare_candidate(ctx, &layout.root.join(&staging), operation, log)?;
        // Assets and candidate creation are permitted before quarantine, but the
        // immutable user-reviewed plan must still match immediately before intent.
        let refreshed = plan_for_compare(&layout.root, catalog, &cancel)?;
        if refreshed.plan_sha256 != plan.plan_sha256 {
            bail!("获取候选期间引用闭包或受保护内容变化；未开始替换");
        }
        let before = plan.before.clone().context("计划缺少原始基础Python观察")?;
        let registry_before = Registry::load(&layout.root)?;
        let registry_disabled =
            disabled_registry(&registry_before, &plan.references, &transaction)?;
        layout.ensure_dir(&directory)?;
        let registry_path = layout.root.join("state/registry.json");
        let original_registry_sha256 = if registry_path.exists() {
            let bytes = read_small(layout, &registry_path, MAX_DETAIL)?;
            let digest = sha(&bytes);
            write_new(layout, &directory.join("registry-before.json"), &bytes)?;
            Some(digest)
        } else {
            None
        };
        let mut original_states = BTreeMap::new();
        for reference in &plan.references {
            let path = layout
                .root
                .join("state/instances")
                .join(format!("{}.json", reference.instance_id));
            let bytes = read_small(layout, &path, MAX_DETAIL)?;
            write_new(
                layout,
                &directory
                    .join("states-before")
                    .join(format!("{}.json", reference.instance_id)),
                &bytes,
            )?;
            original_states.insert(reference.instance_id.clone(), sha(&bytes));
        }
        let details = Details {
            schema_version: 1,
            transaction: transaction.clone(),
            plan,
            registry_before,
            registry_disabled,
            original_states,
            original_registry_sha256,
        };
        let details_bytes = serde_json::to_vec_pretty(&details)?;
        if details_bytes.len() as u64 > MAX_DETAIL {
            bail!("基础Python不可变计划超过32MiB");
        }
        write_new(layout, &directory.join("details.json"), &details_bytes)?;
        if let Some(prior) = read_intent(layout)? {
            if prior.phase != Phase::Committed {
                bail!("已有未完成基础Python事务");
            }
            let path = layout
                .root
                .join(transaction_directory(&prior.transaction)?)
                .join("committed-intent.json");
            save_candidate(
                layout,
                &path,
                &read_small(layout, &layout.root.join(RECORD), MAX_RECORD)?,
            )?;
        }
        let mut intent = Intent {
            schema_version: 1,
            component_id: COMPONENT.into(),
            root: layout.root.clone(),
            transaction,
            phase: Phase::Prepared,
            details: directory.strip_prefix(&layout.root)?.join("details.json"),
            details_sha256: sha(&details_bytes),
            staging,
            backup: directory.strip_prefix(&layout.root)?.join("base-before"),
            previous: directory
                .strip_prefix(&layout.root)?
                .join("previous-published"),
            before,
            staged,
            candidates: BTreeMap::new(),
            snapshot_complete: false,
        };
        store_intent(layout, &intent)?;
        drive(ctx, catalog, &mut intent, operation, validator)
    })();
    finish(ctx, operation, &result)?;
    result
}
// Separate name avoids shadowing the pure planner by the immutable local `plan`.
fn plan_for_compare(root: &Path, catalog: &Catalog, cancel: &CancelToken) -> Result<Plan> {
    plan(root, catalog, cancel)
}
pub(super) fn recover(
    ctx: &WorkspaceMutation,
    catalog: &Catalog,
    operation: &OperationHandle,
    _log: &super::Logger,
    validator: &mut Validator<'_>,
) -> Result<()> {
    operation.persist(ctx)?;
    let result = (|| -> Result<()> {
        report(
            ctx,
            operation,
            OperationPhase::Recovering,
            "恢复基础Python引用闭包事务；保留原始失败和独立快照",
        )?;
        let mut intent = read_intent(ctx.layout())?.context("没有待恢复基础Python事务")?;
        drive(ctx, catalog, &mut intent, operation, validator)
    })();
    finish(ctx, operation, &result)?;
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture {
        root: PathBuf,
        layout: Layout,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-base-repair-{}-{}-{}",
                std::process::id(),
                model::now(),
                SERIAL.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&root).unwrap();
            let layout = Layout::new(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            Self { root, layout }
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
                    .starts_with("nt-base-repair-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }
    #[test]
    fn missing_or_broken_python_preview_is_rust_only_and_lists_fixed_scope() {
        let f = Fixture::new();
        let catalog = Catalog::embedded().unwrap();
        let value = preview(&f.root, &catalog).unwrap();
        assert!(value["integrity_error"].is_string());
        assert_eq!(value["expected_files"].as_array().unwrap().len(), 4184);
        assert_eq!(value["target"], TARGET);
        assert!(value["references"].as_array().unwrap().is_empty());
        let python = f.root.join(TARGET).join(PATCH).join("python.exe");
        f.layout.ensure_dir(python.parent().unwrap()).unwrap();
        fs::write(&python, b"deliberately not executable").unwrap();
        let broken = preview(&f.root, &catalog).unwrap();
        assert!(broken["integrity_error"].is_string());
        assert_ne!(value["plan_sha256"], broken["plan_sha256"]);
        assert_eq!(fs::read(python).unwrap(), b"deliberately not executable");
    }
    #[test]
    fn unknown_pending_schema_blocks_repair_and_preserves_record_bytes() {
        let f = Fixture::new();
        f.layout.ensure_dir(&f.root.join("state")).unwrap();
        let path = f.root.join(RECORD);
        let bytes = b"{\"schema_version\":99,\"transaction\":\"base-python-foreign\"}";
        fs::write(&path, bytes).unwrap();
        let value = preview(&f.root, &Catalog::embedded().unwrap()).unwrap();
        assert_eq!(value["repair_available"], false);
        assert_eq!(value["recovery_available"], false);
        assert!(value["recovery_error"].is_string());
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
    #[test]
    fn prepared_intent_without_registry_gate_blocks_every_nonterminal_phase() {
        let f = Fixture::new();
        f.layout.ensure_dir(&f.root.join("state")).unwrap();
        let transaction = "base-python-strong-kill";
        let directory = transaction_directory(transaction).unwrap();
        let observed = Tree {
            exists: true,
            bytes: 7,
            files: 1,
            sha256: sha(b"fixture"),
            minor_alias: false,
        };
        let mut intent = Intent {
            schema_version: 1,
            component_id: COMPONENT.into(),
            root: f.root.clone(),
            transaction: transaction.into(),
            phase: Phase::Prepared,
            details: directory.join("details.json"),
            details_sha256: sha(b"immutable details"),
            staging: PathBuf::from("staging").join(transaction).join("python"),
            backup: directory.join("base-before"),
            previous: directory.join("previous-published"),
            before: observed.clone(),
            staged: observed,
            candidates: BTreeMap::new(),
            snapshot_complete: false,
        };
        Registry::load(&f.root)
            .unwrap()
            .assert_base_python_ready()
            .unwrap();
        for phase in [
            Phase::Prepared,
            Phase::Quarantined,
            Phase::Snapshotted,
            Phase::Publishing,
            Phase::Published,
            Phase::Validated,
            Phase::Committing,
        ] {
            intent.phase = phase;
            store_intent(&f.layout, &intent).unwrap();
            assert!(assert_ready(&f.root).is_err());
        }
        intent.phase = Phase::Committed;
        store_intent(&f.layout, &intent).unwrap();
        assert_ready(&f.root).unwrap();
        let original = fs::read(f.root.join(RECORD)).unwrap();
        intent.staging = PathBuf::from("../outside");
        assert!(store_intent(&f.layout, &intent).is_err());
        assert_eq!(fs::read(f.root.join(RECORD)).unwrap(), original);
    }
    #[test]
    fn unregistered_venv_and_mixed_base_identity_block_the_reference_closure() {
        let f = Fixture::new();
        let environment = f.root.join("e/g0000000000000099");
        f.layout.ensure_dir(&environment).unwrap();
        let cfg = format!(
            "home = {}\nbase-executable = {}\n",
            f.root.join(TARGET).join(PATCH).display(),
            f.root.join(TARGET).join(PATCH).join("python.exe").display()
        );
        fs::write(environment.join("pyvenv.cfg"), &cfg).unwrap();
        let value = preview(&f.root, &Catalog::embedded().unwrap()).unwrap();
        assert_eq!(value["repair_available"], false);
        assert!(value["blockers"]
            .as_array()
            .unwrap()
            .iter()
            .any(|value| value.as_str().unwrap().contains("未登记")));
        fs::write(
            environment.join("pyvenv.cfg"),
            format!("{cfg}base-prefix = C:\\foreign-python\n"),
        )
        .unwrap();
        assert!(pyvenv_reference(&f.layout, &environment).is_err());
    }
    #[test]
    fn independent_snapshot_resumes_prefix_and_never_accepts_foreign_backup_bytes() {
        let f = Fixture::new();
        let source = f.root.join(TARGET);
        let backup = f.root.join("backups/independent");
        f.layout.ensure_dir(&source).unwrap();
        fs::write(source.join("a.bin"), b"original component bytes").unwrap();
        f.layout.ensure_dir(&backup).unwrap();
        fs::write(backup.join("a.bin"), b"original").unwrap();
        copy_snapshot(&f.layout, &source, &backup, &CancelToken::new()).unwrap();
        assert_eq!(
            tree(&f.layout, &source, Some(&source), &CancelToken::new()).unwrap(),
            tree(&f.layout, &backup, Some(&backup), &CancelToken::new()).unwrap()
        );
        fs::write(source.join("a.bin"), b"modified component bytes").unwrap();
        assert_eq!(
            fs::read(backup.join("a.bin")).unwrap(),
            b"original component bytes"
        );
        assert!(copy_snapshot(&f.layout, &source, &backup, &CancelToken::new()).is_err());
        assert_eq!(
            fs::read(backup.join("a.bin")).unwrap(),
            b"original component bytes"
        );
    }
    #[test]
    fn unpublished_partial_candidate_is_preserved_and_final_publication_is_atomic() {
        let f = Fixture::new();
        let directory = f.root.join("backups/base-python-candidate/candidates");
        f.layout.ensure_dir(&directory).unwrap();
        let partial = directory.join(".candidate-killed.tmp");
        fs::write(&partial, b"partial original failure").unwrap();
        let final_path = directory.join("g0000000000000001.json");
        save_candidate(&f.layout, &final_path, b"complete candidate").unwrap();
        assert_eq!(fs::read(&partial).unwrap(), b"partial original failure");
        assert_eq!(fs::read(&final_path).unwrap(), b"complete candidate");
        save_candidate(&f.layout, &final_path, b"complete candidate").unwrap();
        assert!(save_candidate(&f.layout, &final_path, b"different candidate").is_err());
        assert_eq!(fs::read(&final_path).unwrap(), b"complete candidate");
        let prepared = directory.join(".candidate-prepared.tmp");
        fs::write(&prepared, b"foreign replacement").unwrap();
        assert!(publish_new_file(&prepared, &final_path).is_err());
        assert_eq!(fs::read(&prepared).unwrap(), b"foreign replacement");
        assert_eq!(fs::read(final_path).unwrap(), b"complete candidate");
    }
    #[test]
    fn own_atomic_write_leftovers_do_not_poison_protection_but_foreign_state_does() {
        let f = Fixture::new();
        f.layout.ensure_dir(&f.root.join("state")).unwrap();
        let before = capture(&f.layout, &[], &CancelToken::new()).unwrap();
        let transaction = "base-python-state-interruption";
        let directory = f
            .root
            .join(transaction_directory(transaction).unwrap())
            .join("atomic-writes");
        f.layout.ensure_dir(&directory).unwrap();
        let partial = directory.join(".state-killed.tmp");
        fs::write(&partial, b"{partial state json").unwrap();
        assert_eq!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            before
        );
        let registry = Registry {
            schema_version: 3,
            base_python_pending: Some(transaction.into()),
            ..Registry::default()
        };
        registry.store_for_base(&f.root, transaction).unwrap();
        assert_eq!(Registry::load(&f.root).unwrap(), registry);
        assert_eq!(fs::read(&partial).unwrap(), b"{partial state json");
        assert_eq!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            before
        );
        assert!(!fs::read_dir(f.root.join("state"))
            .unwrap()
            .any(|entry| entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".state-")));
        fs::write(
            f.root.join("state/.state-foreign.tmp"),
            b"unknown original state",
        )
        .unwrap();
        assert_ne!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            before
        );
    }
    #[test]
    fn obsolete_download_accounting_is_ignored_and_preserved() {
        let f = Fixture::new();
        let ctx = WorkspaceMutation::acquire(&f.root, &format!("dev-{}", "a".repeat(40))).unwrap();
        let before = capture(ctx.layout(), &[], &CancelToken::new()).unwrap();
        for name in ["download-budget.json", "download-budget-enrollment.json"] {
            let path = f.root.join("state").join(name);
            fs::write(&path, b"old unreadable accounting state").unwrap();
        }
        let receipt = f.root.join("state/download-receipts");
        fs::create_dir_all(&receipt).unwrap();
        fs::write(receipt.join("foreign.json"), b"{broken legacy receipt}").unwrap();
        assert_eq!(
            capture(ctx.layout(), &[], &CancelToken::new()).unwrap(),
            before
        );
        assert_eq!(
            fs::read(receipt.join("foreign.json")).unwrap(),
            b"{broken legacy receipt}"
        );
    }
    #[test]
    fn profiles_content_change_and_new_unrelated_state_change_protection() {
        let f = Fixture::new();
        let profile = f.root.join("profiles/default/large.data");
        f.layout.ensure_dir(profile.parent().unwrap()).unwrap();
        fs::write(&profile, b"user data").unwrap();
        let original = capture(&f.layout, &[], &CancelToken::new()).unwrap();
        fs::write(&profile, b"user edit").unwrap();
        assert_ne!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            original
        );
        fs::write(profile, b"user data").unwrap();
        assert_eq!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            original
        );
        f.layout.ensure_dir(&f.root.join("state")).unwrap();
        fs::write(f.root.join("state/unknown.json"), b"foreign").unwrap();
        assert_ne!(
            capture(&f.layout, &[], &CancelToken::new()).unwrap(),
            original
        );
    }
    #[cfg(windows)]
    #[test]
    fn renamed_minor_alias_is_only_allowed_for_exact_intent_roots_and_can_be_repaired() {
        let f = Fixture::new();
        let source = f.root.join("staging/base-python-test/python");
        let target = f.root.join(TARGET);
        f.layout.ensure_dir(&source.join(PATCH)).unwrap();
        fs::write(source.join(PATCH).join("python.exe"), b"fixture").unwrap();
        make_alias(&f.layout, &source, &source).unwrap();
        let expected = tree(&f.layout, &source, Some(&source), &CancelToken::new()).unwrap();
        f.layout.ensure_dir(target.parent().unwrap()).unwrap();
        fs::rename(&source, &target).unwrap();
        assert!(tree(&f.layout, &target, Some(&target), &CancelToken::new()).is_err());
        assert_eq!(
            tree_with_aliases(
                &f.layout,
                &target,
                Some(&target),
                std::slice::from_ref(&source),
                &CancelToken::new()
            )
            .unwrap(),
            expected
        );
        remove_known_alias(&f.layout, &target, &[source]).unwrap();
        make_alias(&f.layout, &target, &target).unwrap();
        assert_eq!(
            tree(&f.layout, &target, Some(&target), &CancelToken::new()).unwrap(),
            expected
        );
        let outside = f.root.join("other");
        f.layout.ensure_dir(&outside).unwrap();
        remove_known_alias(&f.layout, &target, std::slice::from_ref(&target)).unwrap();
        junction::create(&outside, target.join(ALIAS)).unwrap();
        assert!(tree_with_aliases(
            &f.layout,
            &target,
            Some(&target),
            std::slice::from_ref(&target),
            &CancelToken::new()
        )
        .is_err());
        junction::delete(target.join(ALIAS)).unwrap();
        fs::remove_dir(target.join(ALIAS)).unwrap();
    }
}
