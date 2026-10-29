//! 固定路径 GUI 实例事务；修改必须持有同一 workspace lease，dirty 仅由复验清除。
use crate::model::{self, Layout, WorkspaceMutation};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

const MAX_FILE: u64 = 1024 * 1024 * 1024;
const MAX_TREE: u64 = 4 * MAX_FILE;
const MAX_STATE: u64 = 32 * 1024 * 1024;
static NEXT: AtomicU64 = AtomicU64::new(0);
type Tree = BTreeMap<PathBuf, Node>;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Fingerprint {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    tag = "kind",
    content = "fingerprint",
    rename_all = "snake_case",
    deny_unknown_fields
)]
enum Node {
    Directory,
    File(Fingerprint),
    PythonAlias(PathBuf),
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Observation {
    environment: Tree,
    profiles: Tree,
    protected: BTreeMap<PathBuf, Tree>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Pending {
    instance_id: String,
    generation: u64,
    base_generation: u64,
    recipe_sha256: String,
    tree_sha256: String,
    directory: PathBuf,
    files: BTreeMap<PathBuf, Option<Fingerprint>>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct InstanceState {
    schema_version: u32,
    component: String,
    instance_id: String,
    #[serde(default, skip_serializing_if = "model::legacy_storage_version")]
    storage_version: u32,
    release_id: String,
    root_absolute: PathBuf,
    recipe_id: String,
    recipe_sha256: String,
    generation: u64,
    validated_generation: u64,
    dirty: bool,
    ignored: Vec<PathBuf>,
    verified: Observation,
    pending: Option<Pending>,
}
pub(crate) struct RepairPlan {
    state: InstanceState,
    paths: Vec<PathBuf>,
    diagnosed: Observation,
}
pub(crate) struct MutationTicket {
    state: InstanceState,
}

impl InstanceState {
    pub(crate) fn id(&self) -> &str {
        &self.instance_id
    }
    pub(crate) fn storage_version(&self) -> u32 {
        self.storage_version
    }
    pub(crate) fn release_id(&self) -> &str {
        &self.release_id
    }
    pub(crate) fn generation(&self) -> u64 {
        self.generation
    }
    pub(crate) fn dirty(&self) -> bool {
        self.dirty
    }
    pub(crate) fn recipe_id(&self) -> &str {
        &self.recipe_id
    }
    pub(crate) fn recipe_sha256(&self) -> &str {
        &self.recipe_sha256
    }
}
fn release(layout: &Layout) -> Result<&str> {
    layout
        .release_dir
        .file_name()
        .and_then(|name| name.to_str())
        .context("缺少release身份")
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        bail!("实例路径必须为非空相对路径");
    }
    for part in path.components() {
        match part {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("路径不是UTF-8")?)?
            }
            _ => bail!("实例路径不允许跳转或盘符"),
        }
    }
    Ok(())
}
fn state_path(layout: &Layout, id: &str) -> Result<PathBuf> {
    model::validate_component(id)?;
    let path = layout
        .root
        .join("state/instances")
        .join(format!("{id}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}
pub(crate) fn path(state: &InstanceState) -> Result<PathBuf> {
    let layout = Layout::new(&state.root_absolute, &state.release_id)?;
    let path = model::environment_path(
        &layout.root,
        &state.release_id,
        &state.instance_id,
        state.storage_version,
    )?;
    layout.guard_path(&path)?;
    Ok(path)
}
fn fingerprint(layout: &Layout, path: &Path) -> Result<Fingerprint> {
    layout.guard_path(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > MAX_FILE {
        bail!("实例只接受受限普通文件");
    }
    let mut input = File::open(path)?;
    let mut digest = Sha256::new();
    let mut total = 0u64;
    let mut buffer = [0; 65536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        total += count as u64;
        if total > MAX_FILE {
            bail!("实例文件读取超限");
        }
        digest.update(&buffer[..count]);
    }
    Ok(Fingerprint {
        bytes: total,
        sha256: format!("{:x}", digest.finalize()),
    })
}
fn ignored(paths: &[PathBuf], path: &Path) -> bool {
    paths.iter().any(|ignored| path.starts_with(ignored))
}
fn windows_key(path: &Path) -> String {
    path.to_string_lossy()
        .replace('\\', "/")
        .to_ascii_lowercase()
}
fn scan(layout: &Layout, base: &Path, ignores: &[PathBuf]) -> Result<Tree> {
    scan_tree(layout, base, ignores, None)
}
fn python_alias_node(layout: &Layout, alias: &Path, target: &Path) -> Result<Node> {
    layout.guard_path(alias.parent().context("Python别名缺少父目录")?)?;
    layout.guard_path(target)?;
    #[cfg(windows)]
    {
        if !junction::exists(alias)?
            || junction::get_target(alias)?.canonicalize()? != target.canonicalize()?
            || !target.is_dir()
        {
            bail!("Python minor别名未指向同根固定patch目录");
        }
        Ok(Node::PythonAlias(
            target.strip_prefix(&layout.root)?.to_path_buf(),
        ))
    }
    #[cfg(not(windows))]
    bail!("Python minor junction仅在Windows允许")
}
fn scan_tree(
    layout: &Layout,
    base: &Path,
    ignores: &[PathBuf],
    python_alias: Option<(&Path, &Path)>,
) -> Result<Tree> {
    struct Options<'a> {
        ignores: &'a [PathBuf],
        python_alias: Option<(&'a Path, &'a Path)>,
    }
    fn walk(
        layout: &Layout,
        base: &Path,
        current: &Path,
        options: &Options<'_>,
        tree: &mut Tree,
        total: &mut u64,
        aliases: &mut BTreeSet<String>,
    ) -> Result<()> {
        if let Some((alias, target)) = options.python_alias {
            if current == alias {
                tree.insert(
                    current.strip_prefix(base)?.to_path_buf(),
                    python_alias_node(layout, alias, target)?,
                );
                return Ok(());
            }
        }
        layout.guard_path(current)?;
        let rel = current.strip_prefix(base)?.to_path_buf();
        if !rel.as_os_str().is_empty() && ignored(options.ignores, &rel) {
            return Ok(());
        }
        if !aliases.insert(
            rel.to_string_lossy()
                .replace('\\', "/")
                .to_ascii_lowercase(),
        ) {
            bail!("实例树存在大小写别名");
        }
        let meta = fs::symlink_metadata(current)?;
        let node = if meta.is_dir() {
            Node::Directory
        } else {
            let digest = fingerprint(layout, current)?;
            *total = total.checked_add(digest.bytes).context("实例树长度溢出")?;
            Node::File(digest)
        };
        tree.insert(rel, node);
        if tree.len() > 50_000 || *total > MAX_TREE {
            bail!("实例树超出验证上限");
        }
        if meta.is_dir() {
            for entry in fs::read_dir(current)? {
                walk(layout, base, &entry?.path(), options, tree, total, aliases)?;
            }
        }
        Ok(())
    }
    layout.guard_path(base)?;
    let mut tree = Tree::new();
    if base.exists() {
        walk(
            layout,
            base,
            base,
            &Options {
                ignores,
                python_alias,
            },
            &mut tree,
            &mut 0,
            &mut BTreeSet::new(),
        )?;
    }
    Ok(tree)
}
fn python_tree(layout: &Layout) -> Result<Tree> {
    let python = layout.root.join("python/3.10.19");
    let alias = python.join("cpython-3.10-windows-x86_64-none");
    let target = python.join("cpython-3.10.19-windows-x86_64-none");
    scan_tree(layout, &python, &[], Some((&alias, &target)))
}
fn observe(layout: &Layout, state: &InstanceState) -> Result<Observation> {
    let current = path(state)?;
    let mut protected = BTreeMap::new();
    for root in [&layout.release_dir, &layout.root.join("tools/uv.exe")] {
        protected.insert(
            root.strip_prefix(&layout.root)?.to_path_buf(),
            scan(layout, root, &[])?,
        );
    }
    protected.insert(PathBuf::from("python/3.10.19"), python_tree(layout)?);
    for container in ["environments", "e"] {
        let base = layout.root.join(container);
        let excluded = match state.storage_version {
            0 if container == "environments" => Some(
                current
                    .parent()
                    .context("GUI实例缺少父目录")?
                    .strip_prefix(&base)?
                    .to_path_buf(),
            ),
            1 if container == "e" => Some(current.strip_prefix(&base)?.to_path_buf()),
            _ => None,
        };
        let tree = scan(layout, &base, &excluded.into_iter().collect::<Vec<_>>())?;
        if container == "e"
            && state.storage_version == 0
            && state.pending.is_some()
            && !state.verified.protected.contains_key(Path::new("e"))
        {
            // 旧 dirty 事务不能追认过去未保护的新容器。只有 e 仍为空时才沿原合同恢复。
            if tree.keys().any(|path| !path.as_os_str().is_empty()) {
                bail!("旧实例事务未记录短路径环境保护树，且 e 已含内容；保留 dirty 与快照");
            }
        } else {
            protected.insert(PathBuf::from(container), tree);
        }
    }
    Ok(Observation {
        environment: scan(layout, &path(state)?, &state.ignored)?,
        profiles: scan(layout, &layout.root.join("profiles"), &[])?,
        protected,
    })
}
fn validate(layout: &Layout, id: &str, state: &InstanceState) -> Result<()> {
    if state.schema_version != 2
        || state.component != "gui"
        || state.instance_id != id
        || state.root_absolute != layout.root
        || state.release_id != release(layout)?
        || state.generation == 0
        || !valid_hash(&state.recipe_sha256)
    {
        bail!("实例schema或持久身份不支持，保留原记录");
    }
    model::validate_component(&state.recipe_id)?;
    let environment = path(state)?;
    if let Some(binding) = model::Registry::load(&layout.root)?.gui_binding(&state.release_id) {
        if binding.instance_id == state.instance_id
            && binding.storage_version != state.storage_version
        {
            bail!("实例存储版本与既有绑定不一致，拒绝重新解释环境路径");
        }
    }
    let alternate_storage = 1 - state.storage_version;
    if let Ok(alternate) = model::environment_path(
        &layout.root,
        &state.release_id,
        state.id(),
        alternate_storage,
    ) {
        if alternate.exists() {
            bail!("同一实例 ID 在另一存储命名空间已有目录，拒绝切换路径解释");
        }
    }
    layout.guard_path(&environment)?;
    for ignore in &state.ignored {
        relative(ignore)?;
        if !matches!(
            ignore.file_name().and_then(|value| value.to_str()),
            Some("__pycache__" | "logs")
        ) && ignore.extension().is_none_or(|value| value != "pyc")
        {
            bail!("忽略清单只接受显式pyc、__pycache__或logs路径");
        }
    }
    let mut roots: BTreeSet<_> = [
        layout.release_dir.strip_prefix(&layout.root)?.to_path_buf(),
        PathBuf::from("tools/uv.exe"),
        PathBuf::from("python/3.10.19"),
        PathBuf::from("environments"),
    ]
    .into_iter()
    .collect();
    if state.storage_version == 1 || state.verified.protected.contains_key(Path::new("e")) {
        roots.insert(PathBuf::from("e"));
    }
    if state
        .verified
        .protected
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>()
        != roots
    {
        bail!("实例缺少固定非目标组件保护树");
    }
    for root in state.verified.protected.keys() {
        relative(root)?;
        layout.guard_path(&layout.root.join(root))?;
    }
    for tree in [&state.verified.environment, &state.verified.profiles]
        .into_iter()
        .chain(state.verified.protected.values())
    {
        for (rel, node) in tree {
            if !rel.as_os_str().is_empty() {
                relative(rel)?;
            }
            if let Node::File(value) = node {
                if value.bytes > MAX_FILE || !valid_hash(&value.sha256) {
                    bail!("实例树摘要无效");
                }
            }
            if let Node::PythonAlias(target) = node {
                relative(target)?;
            }
        }
    }
    match (&state.pending, state.dirty) {
        (None, true) if state.generation == 1 && state.validated_generation == 0 => {}
        (None, false) if state.generation == state.validated_generation => {}
        (Some(pending), true)
            if pending.instance_id == id
                && pending.generation == state.generation
                && pending.base_generation == state.validated_generation
                && pending.base_generation.checked_add(1) == Some(state.generation)
                && pending.recipe_sha256 == state.recipe_sha256
                && pending.tree_sha256 == hash(&serde_json::to_vec(&state.verified)?) =>
        {
            relative(&pending.directory)?;
            let prefix = Path::new("backups/gui-instances").join(id);
            if !pending.directory.starts_with(&prefix)
                || pending.directory.components().count() != prefix.components().count() + 1
                || !pending
                    .directory
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| {
                        name.starts_with(&format!("generation-{}-", state.generation))
                    })
            {
                bail!("实例快照路径身份无效");
            }
            layout.guard_path(&layout.root.join(&pending.directory))?;
            validate_paths(state, &pending.files.keys().cloned().collect::<Vec<_>>())?;
            for (rel, original) in &pending.files {
                if state.verified.environment.get(rel)
                    != original
                        .as_ref()
                        .map(|value| Node::File(value.clone()))
                        .as_ref()
                {
                    bail!("快照文件与诊断树不一致");
                }
            }
        }
        _ => bail!("实例dirty/generation/事务状态不一致"),
    }
    Ok(())
}
pub(crate) fn load(layout: &Layout, id: &str) -> Result<InstanceState> {
    let target = state_path(layout, id)?;
    if fs::metadata(&target)?.len() > MAX_STATE {
        bail!("实例记录过大");
    }
    let state: InstanceState = serde_json::from_slice(&fs::read(target)?)?;
    validate(layout, id, &state)?;
    Ok(state)
}
fn save(layout: &Layout, state: &InstanceState) -> Result<()> {
    validate(layout, &state.instance_id, state)?;
    if serde_json::to_vec(state)?.len() as u64 > MAX_STATE {
        bail!("实例记录超过可重读上限");
    }
    model::write_json_atomic(&state_path(layout, &state.instance_id)?, state)
}
pub(crate) fn create(
    ctx: &WorkspaceMutation,
    id: &str,
    recipe_id: &str,
    recipe_sha256: &str,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let target = state_path(layout, id)?;
    if target.exists() {
        let _ = load(layout, id)?;
        bail!("实例ID已经存在，拒绝覆盖");
    }
    model::validate_component(recipe_id)?;
    if !valid_hash(recipe_sha256) {
        bail!("配方SHA256无效");
    }
    let mut state = InstanceState {
        schema_version: 2,
        component: "gui".into(),
        instance_id: id.into(),
        storage_version: 1,
        release_id: release(layout)?.into(),
        root_absolute: layout.root.clone(),
        recipe_id: recipe_id.into(),
        recipe_sha256: recipe_sha256.into(),
        generation: 1,
        validated_generation: 0,
        dirty: true,
        ignored: vec![],
        verified: Observation {
            environment: Tree::new(),
            profiles: Tree::new(),
            protected: BTreeMap::new(),
        },
        pending: None,
    };
    let environment = path(&state)?;
    if model::environment_path(&layout.root, release(layout)?, id, 0)?.exists() {
        bail!("同一实例 ID 的旧环境目录已存在，拒绝为它创建短路径别名");
    }
    let parent = environment.parent().context("实例缺少父目录")?;
    layout.ensure_dir(parent)?;
    // 原子目录创建独占短 ID；state 或物理目录任一重名都拒绝覆盖。
    fs::create_dir(&environment)?;
    state.verified = observe(layout, &state)?;
    save(layout, &state)?;
    Ok(state)
}
pub(crate) fn assert_usable(state: &InstanceState) -> Result<()> {
    let layout = Layout::new(&state.root_absolute, &state.release_id)?;
    let current = load(&layout, &state.instance_id)?;
    if current != *state
        || state.dirty
        || state.generation != state.validated_generation
        || state.verified.protected.get(Path::new("python/3.10.19")) != Some(&python_tree(&layout)?)
        || scan(&layout, &path(state)?, &state.ignored)? != state.verified.environment
    {
        bail!("实例dirty、过期或不匹配已验证generation，禁止使用");
    }
    Ok(())
}
fn clean(
    layout: &Layout,
    mut state: InstanceState,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let before = observe(layout, &state)?;
    if !matches!(before.environment.get(Path::new("")), Some(Node::Directory)) {
        bail!("GUI实例目录缺失，保持dirty");
    }
    validator(&path(&state)?)?;
    if observe(layout, &state)? != before || load(layout, &state.instance_id)? != state {
        bail!("验证器改变受保护树或持久实例已变化，保持dirty");
    }
    state.verified = before;
    state.validated_generation = state.generation;
    state.dirty = false;
    state.pending = None;
    save(layout, &state)?;
    Ok(state)
}
pub(crate) fn validate_new(
    ctx: &WorkspaceMutation,
    state: &InstanceState,
    ignores: &[PathBuf],
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let mut current = load(layout, state.id())?;
    if current != *state || !current.dirty || current.generation != 1 || current.pending.is_some() {
        bail!("新实例安装许可不匹配");
    }
    if !current.ignored.is_empty() && current.ignored != ignores {
        bail!("新实例已固定运行时忽略合同，不能重新豁免文件");
    }
    current.ignored = ignores.into();
    validate(layout, current.id(), &current)?;
    let observed = observe(layout, &current)?;
    if observed.profiles != current.verified.profiles
        || observed.protected != current.verified.protected
    {
        bail!("安装改变了profiles或非目标受管组件保护树");
    }
    // 忽略合同先持久化，验证失败或重启仍能恢复同一合同。
    save(layout, &current)?;
    clean(layout, current, validator)
}
fn validate_paths(state: &InstanceState, paths: &[PathBuf]) -> Result<()> {
    if paths.is_empty() || paths.len() > 20_000 {
        bail!("修复文件清单为空或超限");
    }
    let mut unique = BTreeSet::new();
    let known: BTreeMap<_, _> = state
        .verified
        .environment
        .keys()
        .map(|path| (windows_key(path), path))
        .collect();
    for rel in paths {
        relative(rel)?;
        if ignored(&state.ignored, rel) || !unique.insert(windows_key(rel)) {
            bail!("修复清单重复或落入忽略路径");
        }
        let mut current = Some(rel.as_path());
        while let Some(part) = current {
            if known
                .get(&windows_key(part))
                .is_some_and(|known| known.as_path() != part)
                || (part == rel
                    && matches!(state.verified.environment.get(part), Some(Node::Directory)))
                || (part != rel
                    && matches!(state.verified.environment.get(part), Some(Node::File(_))))
            {
                bail!("修复路径身份冲突、大小写别名或父路径不是目录");
            }
            current = part.parent();
        }
    }
    for rel in paths {
        let mut parent = rel.parent();
        while let Some(directory) = parent {
            if unique.contains(&windows_key(directory)) {
                bail!("修复清单存在父子冲突");
            }
            parent = directory.parent();
        }
    }
    Ok(())
}
pub(crate) fn plan(
    ctx: &WorkspaceMutation,
    id: &str,
    expected_generation: u64,
    paths: &[PathBuf],
) -> Result<RepairPlan> {
    let state = load(ctx.layout(), id)?;
    if state.dirty
        || state.generation != state.validated_generation
        || state.generation != expected_generation
    {
        bail!("修复计划generation已过期");
    }
    let diagnosed = observe(ctx.layout(), &state)?;
    let mut facts = state.clone();
    facts.verified = diagnosed.clone();
    validate_paths(&facts, paths)?;
    // 诊断不能把闭包外已被替换的解释器/控制文件重新认作可信基线。
    // profiles 与其他组件允许在两个操作之间正常变化，本次事务从诊断时保护它们。
    let mut trusted = state.verified.clone();
    trusted.profiles = diagnosed.profiles.clone();
    trusted.protected = diagnosed.protected.clone();
    // 基础Python由所有引用实例共享；单包修复不能接纳已变更的基础运行时。
    trusted.protected.insert(
        PathBuf::from("python/3.10.19"),
        state
            .verified
            .protected
            .get(Path::new("python/3.10.19"))
            .context("缺少基础Python基线")?
            .clone(),
    );
    let allowed = paths.iter().map(|path| (path.clone(), None)).collect();
    protected(&trusted, &diagnosed, &allowed)?;
    Ok(RepairPlan {
        state,
        paths: paths.into(),
        diagnosed,
    })
}
fn copy(
    layout: &Layout,
    source: &Path,
    destination: &Path,
    create_new: bool,
) -> Result<Fingerprint> {
    let expected = fingerprint(layout, source)?;
    layout.guard_path(destination)?;
    layout.ensure_dir(destination.parent().context("复制缺少父目录")?)?;
    // 恢复也先独立复制到新文件，不能truncate调用者可能替换成硬链接的目标。
    let output_path = if create_new {
        destination.to_path_buf()
    } else {
        layout.root.join("backups/gui-instances").join(format!(
            ".restore-{}-{}-{}.tmp",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ))
    };
    layout.guard_path(&output_path)?;
    let mut input = File::open(source)?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output_path)?;
    let bytes = std::io::copy(
        &mut Read::by_ref(&mut input).take(MAX_FILE + 1),
        &mut output,
    )?;
    output.sync_all()?;
    drop(output);
    if bytes != expected.bytes
        || fingerprint(layout, &output_path)? != expected
        || fingerprint(layout, source)? != expected
    {
        bail!("实例独立复制摘要不符，保持原事务状态");
    }
    if !create_new {
        layout.guard_path(destination)?;
        if destination.exists() {
            if !destination.is_file() {
                bail!("恢复目标不是普通文件，保持dirty");
            }
            fs::remove_file(destination)?;
        }
        fs::rename(&output_path, destination)?;
    }
    Ok(expected)
}
pub(crate) fn begin(ctx: &WorkspaceMutation, plan: &RepairPlan) -> Result<MutationTicket> {
    let layout = ctx.layout();
    let mut state = load(layout, plan.state.id())?;
    if state != plan.state {
        bail!("诊断后持久实例已变化");
    }
    if state.dirty || observe(layout, &state)? != plan.diagnosed {
        bail!("修复诊断树已经变化，拒绝使用旧计划");
    }
    state.verified = plan.diagnosed.clone();
    validate_paths(&state, &plan.paths)?;
    let generation = state
        .generation
        .checked_add(1)
        .context("实例generation溢出")?;
    let directory = Path::new("backups/gui-instances")
        .join(state.id())
        .join(format!(
            "generation-{generation}-{}-{}",
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    let backup = layout.root.join(&directory);
    layout.guard_path(&backup)?;
    layout.ensure_dir(backup.parent().context("快照缺少父目录")?)?;
    fs::create_dir(&backup)?;
    let mut pending = Pending {
        instance_id: state.instance_id.clone(),
        generation,
        base_generation: state.generation,
        recipe_sha256: state.recipe_sha256.clone(),
        tree_sha256: hash(&serde_json::to_vec(&state.verified)?),
        directory,
        files: BTreeMap::new(),
    };
    let environment = path(&state)?;
    let sorted: BTreeSet<_> = plan.paths.iter().cloned().collect();
    for (index, rel) in sorted.into_iter().enumerate() {
        let original = match state.verified.environment.get(&rel) {
            Some(Node::File(value)) => Some(value.clone()),
            None => None,
            _ => bail!("修复目标不是普通文件"),
        };
        let snapshot = backup.join(index.to_string());
        layout.guard_path(&snapshot)?;
        if let Some(expected) = &original {
            if copy(layout, &environment.join(&rel), &snapshot, true)? != *expected {
                bail!("诊断后修复目标已变化");
            }
        } else {
            let mut marker = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(snapshot)?;
            marker.write_all(b"missing\n")?;
            marker.sync_all()?;
        }
        pending.files.insert(rel, original);
    }
    model::write_json_atomic(&backup.join("manifest.json"), &pending)?;
    if observe(layout, &state)? != state.verified || load(layout, state.id())? != plan.state {
        bail!("快照期间受保护内容变化，未授权修改");
    }
    state.generation = generation;
    state.dirty = true;
    state.pending = Some(pending);
    save(layout, &state)?;
    Ok(MutationTicket { state })
}
fn check_snapshots(layout: &Layout, state: &InstanceState) -> Result<()> {
    let pending = state.pending.as_ref().context("实例没有待恢复事务")?;
    let backup = layout.root.join(&pending.directory);
    let manifest = backup.join("manifest.json");
    layout.guard_path(&manifest)?;
    if fs::metadata(&manifest)?.len() > MAX_STATE {
        bail!("快照清单过大");
    }
    let stored: Pending = serde_json::from_slice(&fs::read(manifest)?)?;
    if stored != *pending {
        bail!("快照清单与持久事务不一致");
    }
    for (index, original) in pending.files.values().enumerate() {
        let snapshot = backup.join(index.to_string());
        layout.guard_path(&snapshot)?;
        match original {
            Some(expected) if fingerprint(layout, &snapshot)? == *expected => {}
            None if fs::metadata(&snapshot)?.len() == 8 && fs::read(&snapshot)? == b"missing\n" => {
            }
            _ => bail!("独立快照损坏，保持dirty"),
        }
    }
    Ok(())
}
pub(crate) fn reload_ticket(layout: &Layout, id: &str) -> Result<MutationTicket> {
    let state = load(layout, id)?;
    if !state.dirty {
        bail!("实例没有dirty事务");
    }
    check_snapshots(layout, &state)?;
    Ok(MutationTicket { state })
}
fn checked(ctx: &WorkspaceMutation, ticket: &MutationTicket) -> Result<InstanceState> {
    let state = load(ctx.layout(), ticket.state.id())?;
    if state != ticket.state || !state.dirty {
        bail!("事务ticket已经过期或不属于工作区");
    }
    check_snapshots(ctx.layout(), &state)?;
    Ok(state)
}
fn protected(
    before: &Observation,
    after: &Observation,
    files: &BTreeMap<PathBuf, Option<Fingerprint>>,
) -> Result<()> {
    let mut expected = before.environment.clone();
    let mut actual = after.environment.clone();
    for rel in files.keys() {
        if matches!(actual.get(rel), Some(Node::Directory)) {
            bail!("修复目标被替换为目录");
        }
        expected.remove(rel);
        actual.remove(rel);
        let mut parent = rel.parent();
        while let Some(directory) = parent {
            if !before.environment.contains_key(directory)
                && matches!(actual.get(directory), Some(Node::Directory))
            {
                actual.remove(directory);
            }
            parent = directory.parent();
        }
    }
    if expected != actual
        || before.profiles != after.profiles
        || before.protected != after.protected
    {
        bail!("修复改变了非目标文件、目录或profiles，保持dirty");
    }
    Ok(())
}
pub(crate) fn commit(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let state = checked(ctx, ticket)?;
    protected(
        &state.verified,
        &observe(ctx.layout(), &state)?,
        &state.pending.as_ref().context("缺少事务")?.files,
    )?;
    clean(ctx.layout(), state, validator)
}
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let state = checked(ctx, ticket)?;
    let pending = state.pending.as_ref().context("缺少恢复快照")?;
    protected(&state.verified, &observe(layout, &state)?, &pending.files)?;
    let environment = path(&state)?;
    for (index, (rel, original)) in pending.files.iter().enumerate() {
        let target = environment.join(rel);
        layout.guard_path(&target)?;
        match original {
            Some(expected) => {
                if copy(
                    layout,
                    &layout.root.join(&pending.directory).join(index.to_string()),
                    &target,
                    false,
                )? != *expected
                {
                    bail!("恢复摘要不符，保持dirty");
                }
            }
            None => {
                if target.exists() {
                    if !target.is_file() {
                        bail!("原missing路径不是普通文件");
                    }
                    fs::remove_file(&target)?;
                }
                let mut parent = target.parent();
                while let Some(directory) = parent {
                    let rel = directory.strip_prefix(&environment)?;
                    if state.verified.environment.contains_key(rel) {
                        break;
                    }
                    layout.guard_path(directory)?;
                    if !directory.exists() {
                        parent = directory.parent();
                        continue;
                    }
                    if fs::read_dir(directory)?.next().is_some() {
                        break;
                    }
                    fs::remove_dir(directory)?;
                    parent = directory.parent();
                }
            }
        }
    }
    if observe(layout, &state)? != state.verified {
        bail!("同路径恢复未还原原树，保持dirty");
    }
    clean(layout, state, validator)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture {
        root: PathBuf,
        ctx: WorkspaceMutation,
        state: InstanceState,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-instance-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx =
                WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let base = root.join("python/3.10.19/base.dll");
            ctx.layout().ensure_dir(base.parent().unwrap()).unwrap();
            fs::write(base, b"original non-target").unwrap();
            let state = create(&ctx, "g0000000000000001", "recipe-one", &"b".repeat(64)).unwrap();
            let env = path(&state).unwrap();
            fs::create_dir(env.join("package")).unwrap();
            fs::write(env.join("package/a.py"), b"original-a").unwrap();
            fs::write(env.join("package/b.py"), b"original-b").unwrap();
            fs::write(env.join("protected.py"), b"preserved").unwrap();
            let state = validate_new(&ctx, &state, &[], |_| Ok(())).unwrap();
            Self { root, ctx, state }
        }
        fn ticket(&self) -> MutationTicket {
            begin(
                &self.ctx,
                &plan(
                    &self.ctx,
                    self.state.id(),
                    self.state.generation(),
                    &[
                        "package/a.py".into(),
                        "package/b.py".into(),
                        "new-dir/new.py".into(),
                    ],
                )
                .unwrap(),
            )
            .unwrap()
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
                    .starts_with("nt-instance-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }
    #[test]
    fn real_multifile_failure_recovers_original_and_missing_paths_from_disk() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        let ticket = f.ticket();
        fs::write(env.join("package/a.py"), b"broken-a").unwrap();
        fs::remove_file(env.join("package/b.py")).unwrap();
        fs::create_dir(env.join("new-dir")).unwrap();
        fs::write(env.join("new-dir/new.py"), b"added").unwrap();
        assert!(commit(&f.ctx, &ticket, |_| bail!("真实多文件验证失败")).is_err());
        assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
        assert!(assert_usable(&f.state).is_err());
        drop(ticket);
        let restored = recover(
            &f.ctx,
            &reload_ticket(f.ctx.layout(), f.state.id()).unwrap(),
            |at| {
                assert_eq!(at, env);
                assert_eq!(fs::read(at.join("package/a.py"))?, b"original-a");
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(fs::read(env.join("package/b.py")).unwrap(), b"original-b");
        assert!(!env.join("new-dir").exists());
        assert_eq!(restored.generation(), 2);
        assert_usable(&restored).unwrap();
    }
    #[test]
    fn external_changes_and_stale_generation_never_unlock_dirty() {
        let f = Fixture::new();
        assert!(plan(&f.ctx, f.state.id(), 99, &["package/a.py".into()]).is_err());
        let ticket = f.ticket();
        fs::write(path(&f.state).unwrap().join("protected.py"), b"foreign").unwrap();
        assert!(commit(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
    }
    #[test]
    fn successful_commit_detaches_snapshots_and_rejects_old_tickets() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        let ticket = f.ticket();
        let backup = f
            .root
            .join(&ticket.state.pending.as_ref().unwrap().directory);
        let before = fs::read(backup.join("1")).unwrap();
        fs::write(env.join("package/a.py"), b"repaired").unwrap();
        assert_eq!(fs::read(backup.join("1")).unwrap(), before);
        let state = commit(&f.ctx, &ticket, |at| {
            if fs::read(at.join("package/a.py"))? != b"repaired" {
                bail!("包未修好");
            }
            Ok(())
        })
        .unwrap();
        assert_usable(&state).unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(plan(
            &f.ctx,
            state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
        fs::write(env.join("package/a.py"), b"corrupt-again").unwrap();
        // 损坏目标仍允许重新诊断修复；计划后的外部变化必须拒绝执行。
        let planned = plan(
            &f.ctx,
            state.id(),
            state.generation(),
            &["package/a.py".into()],
        )
        .unwrap();
        fs::write(env.join("package/a.py"), b"changed-after-plan").unwrap();
        assert!(begin(&f.ctx, &planned).is_err());
    }
    #[test]
    fn snapshot_corruption_and_unknown_state_preserve_bytes_and_dirty() {
        let f = Fixture::new();
        let ticket = f.ticket();
        let backup = f
            .ctx
            .layout()
            .root
            .join(&ticket.state.pending.as_ref().unwrap().directory);
        fs::write(backup.join("0"), b"bad snapshot").unwrap();
        assert!(reload_ticket(f.ctx.layout(), f.state.id()).is_err());
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        let target = state_path(f.ctx.layout(), f.state.id()).unwrap();
        let mut value = serde_json::to_value(load(f.ctx.layout(), f.state.id()).unwrap()).unwrap();
        value["schema_version"] = 999.into();
        let bytes = serde_json::to_vec(&value).unwrap();
        fs::write(&target, &bytes).unwrap();
        assert!(load(f.ctx.layout(), f.state.id()).is_err());
        assert!(create(&f.ctx, f.state.id(), "other", &"c".repeat(64)).is_err());
        assert_eq!(fs::read(target).unwrap(), bytes);
    }
    #[test]
    fn explicit_runtime_ignores_do_not_exempt_profile_or_whole_environment() {
        let f = Fixture::new();
        assert!(validate_paths(&f.state, &["../outside".into()]).is_err());
        assert!(validate_paths(&f.state, &["package".into()]).is_err());
        assert!(validate_paths(&f.state, &["PACKAGE/a.py".into()]).is_err());
        let mut invalid = f.state.clone();
        invalid.ignored = vec![PathBuf::from("package")];
        assert!(validate(f.ctx.layout(), invalid.id(), &invalid).is_err());
        let ticket = f.ticket();
        fs::write(
            f.root.join("profiles/default/profile.json"),
            b"profile changed",
        )
        .unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
    }
    #[test]
    fn source_base_tools_and_other_instances_are_transaction_protected() {
        for relative in [
            "releases/source-placeholder.txt",
            "tools/uv.exe",
            "python/3.10.19/base.dll",
            "environments/other/instances/safe/gui/protected.py",
            "e/g0000000000000002/protected.py",
        ] {
            let f = Fixture::new();
            let protected = if relative.starts_with("releases/") {
                f.ctx.layout().app.join("gui.py")
            } else {
                f.root.join(relative)
            };
            f.ctx
                .layout()
                .ensure_dir(protected.parent().unwrap())
                .unwrap();
            fs::write(&protected, b"original non-target").unwrap();
            let ticket = f.ticket();
            fs::write(&protected, b"foreign non-target mutation").unwrap();
            assert!(commit(&f.ctx, &ticket, |_| Ok(())).is_err());
            assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
            assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
        }
    }
    #[test]
    fn normal_usable_check_does_not_scan_large_profile_model_files() {
        let f = Fixture::new();
        let model = f.root.join("profiles/default/large-model.bin");
        File::create(model).unwrap().set_len(MAX_FILE + 1).unwrap();
        assert_usable(&f.state).unwrap();
    }

    #[test]
    fn compact_storage_is_fixed_and_collisions_or_storage_reinterpretation_are_rejected() {
        let f = Fixture::new();
        assert_eq!(f.state.storage_version(), 1);
        assert_eq!(f.state.release_id(), release(f.ctx.layout()).unwrap());
        assert_eq!(path(&f.state).unwrap(), f.root.join("e/g0000000000000001"));
        assert!(f
            .state
            .verified
            .protected
            .contains_key(Path::new("environments")));
        assert!(f.state.verified.protected.contains_key(Path::new("e")));
        assert!(!f.state.verified.protected[Path::new("e")]
            .contains_key(Path::new("g0000000000000001")));
        assert!(create(&f.ctx, f.state.id(), "recipe-one", &"b".repeat(64)).is_err());
        let record = state_path(f.ctx.layout(), f.state.id()).unwrap();
        let original = fs::read(&record).unwrap();
        let other_layout = Layout::new(&f.root, &format!("dev-{}", "c".repeat(40))).unwrap();
        assert!(load(&other_layout, f.state.id()).is_err());
        assert_eq!(fs::read(&record).unwrap(), original);
        let collision = "g0000000000000002";
        f.ctx
            .layout()
            .ensure_dir(&f.root.join("e").join(collision))
            .unwrap();
        fs::write(
            f.root.join("e").join(collision).join("sentinel"),
            b"preexisting",
        )
        .unwrap();
        assert!(create(&f.ctx, collision, "recipe-one", &"b".repeat(64)).is_err());
        assert_eq!(
            fs::read(f.root.join("e").join(collision).join("sentinel")).unwrap(),
            b"preexisting"
        );
        let mut state = f.state.clone();
        state.storage_version = 0;
        fs::write(&record, serde_json::to_vec(&state).unwrap()).unwrap();
        assert!(load(f.ctx.layout(), state.id()).is_err());
        fs::write(&record, &original).unwrap();
        state = f.state.clone();
        state.storage_version = 99;
        assert!(validate(f.ctx.layout(), state.id(), &state).is_err());
        assert!(load(f.ctx.layout(), "g0000000000000003").is_err());
    }

    #[test]
    fn old_schema_two_missing_storage_field_keeps_original_path_and_can_repair() {
        let f = Fixture::new();
        let compact = path(&f.state).unwrap();
        let mut legacy = f.state.clone();
        legacy.storage_version = 0;
        let old = model::environment_path(&f.root, legacy.release_id(), legacy.id(), 0).unwrap();
        f.ctx.layout().ensure_dir(old.parent().unwrap()).unwrap();
        fs::rename(compact, &old).unwrap();
        legacy.verified = observe(f.ctx.layout(), &legacy).unwrap();
        legacy.verified.protected.remove(Path::new("e"));
        let record = state_path(f.ctx.layout(), legacy.id()).unwrap();
        let bytes = serde_json::to_vec(&legacy).unwrap();
        assert!(!String::from_utf8_lossy(&bytes).contains("storage_version"));
        fs::write(&record, &bytes).unwrap();
        let loaded = load(f.ctx.layout(), legacy.id()).unwrap();
        assert_eq!(loaded.storage_version(), 0);
        assert_eq!(path(&loaded).unwrap(), old);
        assert_usable(&loaded).unwrap();
        assert_eq!(fs::read(&record).unwrap(), bytes);
        let ticket = begin(
            &f.ctx,
            &plan(&f.ctx, loaded.id(), 1, &["package/a.py".into()]).unwrap(),
        )
        .unwrap();
        assert!(ticket.state.verified.protected.contains_key(Path::new("e")));
        let recovered = recover(&f.ctx, &ticket, |_| Ok(())).unwrap();
        assert_eq!(path(&recovered).unwrap(), old);
        assert_eq!(recovered.storage_version(), 0);
        assert_eq!(recovered.generation(), 2);
    }

    #[test]
    fn legacy_dirty_without_e_baseline_recovers_only_while_new_container_is_empty() {
        let f = Fixture::new();
        let compact = path(&f.state).unwrap();
        let mut legacy = f.state.clone();
        legacy.storage_version = 0;
        let old = model::environment_path(&f.root, legacy.release_id(), legacy.id(), 0).unwrap();
        f.ctx.layout().ensure_dir(old.parent().unwrap()).unwrap();
        fs::rename(compact, &old).unwrap();
        legacy.verified = observe(f.ctx.layout(), &legacy).unwrap();
        save(f.ctx.layout(), &legacy).unwrap();
        let mut ticket = begin(
            &f.ctx,
            &plan(&f.ctx, legacy.id(), 1, &["package/a.py".into()]).unwrap(),
        )
        .unwrap();
        ticket.state.verified.protected.remove(Path::new("e"));
        ticket.state.pending.as_mut().unwrap().tree_sha256 =
            hash(&serde_json::to_vec(&ticket.state.verified).unwrap());
        let pending = ticket.state.pending.as_ref().unwrap();
        model::write_json_atomic(
            &f.root.join(&pending.directory).join("manifest.json"),
            pending,
        )
        .unwrap();
        save(f.ctx.layout(), &ticket.state).unwrap();
        let other = f.root.join("e/g0000000000000002");
        f.ctx.layout().ensure_dir(&other).unwrap();
        fs::write(other.join("sentinel"), b"unrecorded environment").unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(load(f.ctx.layout(), legacy.id()).unwrap().dirty());
        fs::remove_file(other.join("sentinel")).unwrap();
        fs::remove_dir(other).unwrap();
        let recovered = recover(&f.ctx, &ticket, |_| Ok(())).unwrap();
        assert_eq!(recovered.storage_version(), 0);
        assert_eq!(path(&recovered).unwrap(), old);
    }
    #[test]
    fn plan_rejects_prior_non_target_environment_damage() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        fs::write(env.join("package/a.py"), b"target damage").unwrap();
        fs::write(f.root.join("profiles/default/profile.json"), b"user edit").unwrap();
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_ok());
        fs::write(env.join("protected.py"), b"prior foreign replacement").unwrap();
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
        assert!(!load(f.ctx.layout(), f.state.id()).unwrap().dirty());
    }
    #[test]
    fn base_python_change_disables_every_reference_and_blocks_package_plan() {
        let f = Fixture::new();
        let base = f.root.join("python/3.10.19/base.dll");
        f.ctx.layout().ensure_dir(base.parent().unwrap()).unwrap();
        fs::write(base, b"modified shared runtime").unwrap();
        assert!(assert_usable(&f.state).is_err());
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
    }
    #[cfg(windows)]
    #[test]
    fn only_the_exact_managed_minor_junction_is_recorded_without_traversal() {
        let f = Fixture::new();
        let root = f.root.join("python/3.10.19");
        let target = root.join("cpython-3.10.19-windows-x86_64-none");
        f.ctx.layout().ensure_dir(&target).unwrap();
        fs::write(target.join("python.exe"), b"fixed python").unwrap();
        let alias = root.join("cpython-3.10-windows-x86_64-none");
        junction::create(&target, &alias).unwrap();
        let observed = observe(f.ctx.layout(), &f.state).unwrap();
        let tree = &observed.protected[Path::new("python/3.10.19")];
        assert!(matches!(
            tree.get(Path::new("cpython-3.10-windows-x86_64-none")),
            Some(Node::PythonAlias(_))
        ));
        assert!(!tree.contains_key(Path::new("cpython-3.10-windows-x86_64-none/python.exe")));
        junction::delete(&alias).unwrap();
        // junction::delete 只移除重解析数据，随后删除留下的空目录。
        fs::remove_dir(&alias).unwrap();
        let outside = f.root.join("outside");
        f.ctx.layout().ensure_dir(&outside).unwrap();
        junction::create(&outside, &alias).unwrap();
        assert!(observe(f.ctx.layout(), &f.state).is_err());
        junction::delete(alias).unwrap();
    }
}
