//! 固定源码发布意图与未绑定实例发现。所有恢复写操作必须持有workspace lease。
use crate::{
    instances,
    model::{self, Layout, Registry, Release, WorkspaceMutation},
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

const LIMIT: u64 = 2_000_000_000;
const RECORD_LIMIT: u64 = 64 * 1024;
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Tree {
    bytes: u64,
    files: usize,
    sha256: String,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Pending,
    Committed,
    RolledBack,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    root: PathBuf,
    release: Release,
    staging: PathBuf,
    backup: PathBuf,
    target: PathBuf,
    staged: Tree,
    previous: Option<Tree>,
    phase: Phase,
}

fn fingerprint(layout: &Layout, base: &Path) -> Result<Tree> {
    fn walk(
        layout: &Layout,
        base: &Path,
        path: &Path,
        nodes: &mut BTreeMap<String, Option<(u64, String)>>,
        bytes: &mut u64,
        files: &mut usize,
    ) -> Result<()> {
        layout.guard_path(path)?;
        let metadata = fs::symlink_metadata(path)?;
        let relative = path
            .strip_prefix(base)?
            .to_str()
            .context("源码树路径不是UTF-8")?
            .replace('\\', "/");
        if metadata.is_dir() {
            if nodes.insert(relative, None).is_some() {
                bail!("源码树路径重复");
            }
        } else {
            if !metadata.is_file() || metadata.len() > LIMIT {
                bail!("源码树存在非普通或超限文件");
            }
            let mut input = File::open(path)?;
            let mut hash = Sha256::new();
            let mut count = 0u64;
            let mut buffer = [0; 65536];
            loop {
                let read = input.read(&mut buffer)?;
                if read == 0 {
                    break;
                }
                count = count.checked_add(read as u64).context("源码文件长度溢出")?;
                if count > LIMIT {
                    bail!("源码文件读取超限");
                }
                hash.update(&buffer[..read]);
            }
            *bytes = bytes.checked_add(count).context("源码树长度溢出")?;
            *files += 1;
            if nodes
                .insert(relative, Some((count, format!("{:x}", hash.finalize()))))
                .is_some()
            {
                bail!("源码树路径重复");
            }
        }
        if *bytes > LIMIT || nodes.len() > 50_000 {
            bail!("源码树超过恢复校验上限");
        }
        if metadata.is_dir() {
            for item in fs::read_dir(path)? {
                walk(layout, base, &item?.path(), nodes, bytes, files)?;
            }
        }
        Ok(())
    }
    layout.guard_path(base)?;
    if !base.is_dir() {
        bail!("源码发布路径不是普通目录");
    }
    let mut nodes = BTreeMap::new();
    let mut bytes = 0;
    let mut files = 0;
    walk(layout, base, base, &mut nodes, &mut bytes, &mut files)?;
    let mut aliases = std::collections::BTreeSet::new();
    if nodes
        .keys()
        .any(|key| !aliases.insert(key.to_ascii_lowercase()))
    {
        bail!("源码树存在Windows大小写别名");
    }
    Ok(Tree {
        bytes,
        files,
        sha256: format!("{:x}", Sha256::digest(serde_json::to_vec(&nodes)?)),
    })
}
fn record_path(layout: &Layout, release: &Release) -> Result<PathBuf> {
    let path = layout
        .root
        .join("state")
        .join(format!("gui-source-{}.json", release.id));
    layout.guard_path(&path)?;
    Ok(path)
}
fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        bail!("源码意图路径必须是受限相对路径");
    }
    for component in path.components() {
        match component {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("源码意图路径不是UTF-8")?)?
            }
            _ => bail!("源码意图路径包含跳转"),
        }
    }
    Ok(())
}
fn validate(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    release.validate()?;
    if intent.schema_version != 1
        || intent.root != layout.root
        || intent.release != *release
        || intent.target != Path::new("releases").join(&release.id)
    {
        bail!("源码发布意图schema或身份不匹配，保留现场");
    }
    for (path, parent, prefix) in [
        (&intent.staging, "staging", "locked-source-".to_string()),
        (&intent.backup, "backups", format!("source-{}-", release.id)),
    ] {
        relative(path)?;
        if path.parent() != Some(Path::new(parent))
            || !path
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with(&prefix))
        {
            bail!("源码意图stage/backup不在固定命名空间");
        }
        layout.guard_path(&layout.root.join(path))?;
    }
    for tree in std::iter::once(&intent.staged).chain(intent.previous.as_ref()) {
        if tree.bytes > LIMIT
            || tree.files > 50_000
            || tree.sha256.len() != 64
            || !tree
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("源码意图树摘要无效");
        }
    }
    if intent.staged.files == 0 {
        bail!("候选源码树不能为空");
    }
    layout.guard_path(&layout.root.join(&intent.target))
}
fn load(layout: &Layout, release: &Release) -> Result<Option<Intent>> {
    let path = record_path(layout, release)?;
    if !path.exists() {
        return Ok(None);
    }
    if !path.is_file() || fs::metadata(&path)?.len() > RECORD_LIMIT {
        bail!("源码意图记录不是受限普通文件");
    }
    let intent: Intent = serde_json::from_slice(&fs::read(path)?)?;
    validate(layout, release, &intent)?;
    Ok(Some(intent))
}
fn save(layout: &Layout, intent: &Intent) -> Result<()> {
    validate(layout, &intent.release, intent)?;
    model::write_json_atomic(&record_path(layout, &intent.release)?, intent)
}
fn verify_at(layout: &Layout, release: &Release, directory: &Path) -> Result<()> {
    let mut selected = layout.clone();
    selected.release_dir = directory.into();
    selected.app = directory.join("app");
    super::verify_source(&selected, release)
}
fn existing(layout: &Layout, path: &Path) -> Result<Option<Tree>> {
    layout.guard_path(path)?;
    if path.exists() {
        Ok(Some(fingerprint(layout, path)?))
    } else {
        Ok(None)
    }
}
fn rollback(layout: &Layout, intent: &mut Intent) -> Result<()> {
    let target = layout.root.join(&intent.target);
    let backup = layout.root.join(&intent.backup);
    if existing(layout, &target)?.is_none()
        && existing(layout, &backup)? == intent.previous
        && intent.previous.is_some()
    {
        fs::rename(&backup, &target)?;
    }
    if existing(layout, &target)? != intent.previous || backup.exists() {
        bail!("源码回撤未完成，原意图保持pending");
    }
    intent.phase = Phase::RolledBack;
    save(layout, intent)
}

/// 重启只在所有存在目录与意图摘要精确匹配时完成发布或回撤；未知树从不覆盖。
pub(super) fn recover_source(ctx: &WorkspaceMutation, release: &Release) -> Result<()> {
    let layout = ctx.layout();
    let Some(mut intent) = load(layout, release)? else {
        return Ok(());
    };
    if intent.phase != Phase::Pending {
        return Ok(());
    }
    let staging = layout.root.join(&intent.staging);
    let backup = layout.root.join(&intent.backup);
    let target = layout.root.join(&intent.target);
    let stage_tree = existing(layout, &staging)?;
    let backup_tree = existing(layout, &backup)?;
    let target_tree = existing(layout, &target)?;
    if stage_tree
        .as_ref()
        .is_some_and(|tree| tree != &intent.staged)
        || backup_tree
            .as_ref()
            .is_some_and(|tree| Some(tree) != intent.previous.as_ref())
        || target_tree
            .as_ref()
            .is_some_and(|tree| tree != &intent.staged && Some(tree) != intent.previous.as_ref())
    {
        bail!("源码发布现场含未知树，保留全部目录与pending意图");
    }
    if target_tree.as_ref() == Some(&intent.staged)
        && stage_tree.is_none()
        && backup_tree == intent.previous
    {
        verify_at(layout, release, &target)?;
        intent.phase = Phase::Committed;
        return save(layout, &intent);
    }
    if let Some(stage_tree) = stage_tree {
        if stage_tree != intent.staged || target_tree.as_ref() == Some(&intent.staged) {
            bail!("源码stage/target出现重复候选，拒绝自动替换");
        }
        verify_at(layout, release, &staging)?;
        if target_tree == intent.previous && target_tree.is_some() && backup_tree.is_none() {
            layout.ensure_dir(backup.parent().context("备份缺少父目录")?)?;
            fs::rename(&target, &backup)?;
        } else if target_tree.is_some() || backup_tree != intent.previous {
            bail!("源码发布旧路径身份不完整，保留现场");
        }
        layout.ensure_dir(target.parent().context("正式目录缺少父目录")?)?;
        if let Err(error) = fs::rename(&staging, &target) {
            let rollback = rollback(layout, &mut intent);
            return Err(error).with_context(|| format!("源码发布失败；回撤结果：{rollback:?}"));
        }
        verify_at(layout, release, &target)?;
        if fingerprint(layout, &target)? != intent.staged {
            bail!("发布后源码树已变化，pending保留");
        }
        intent.phase = Phase::Committed;
        return save(layout, &intent);
    }
    rollback(layout, &mut intent)
}

/// 先提交确切stage/backup/target与新旧树摘要，然后才进行目录移动。
pub(super) fn publish_source(
    ctx: &WorkspaceMutation,
    release: &Release,
    staging: &Path,
) -> Result<()> {
    let layout = ctx.layout();
    recover_source(ctx, release)?;
    layout.guard_path(staging)?;
    verify_at(layout, release, staging)?;
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let suffix = format!("{}-{}-{serial}", model::now(), std::process::id());
    let intent = Intent {
        schema_version: 1,
        root: layout.root.clone(),
        release: release.clone(),
        staging: staging.strip_prefix(&layout.root)?.into(),
        backup: Path::new("backups").join(format!("source-{}-{suffix}", release.id)),
        target: Path::new("releases").join(&release.id),
        staged: fingerprint(layout, staging)?,
        previous: existing(layout, &layout.release_dir)?,
        phase: Phase::Pending,
    };
    validate(layout, release, &intent)?;
    if layout.root.join(&intent.backup).exists() {
        bail!("源码备份目标已存在，拒绝覆盖");
    }
    if let Some(previous) = load(layout, release)? {
        if previous.phase == Phase::Pending {
            bail!("旧源码发布事务尚未恢复");
        }
        let archive = layout
            .root
            .join("state")
            .join(format!("gui-source-{}-{suffix}.history.json", release.id));
        layout.guard_path(&archive)?;
        let bytes = fs::read(record_path(layout, release)?)?;
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(archive)?;
        output.write_all(&bytes)?;
        output.sync_all()?;
    }
    save(layout, &intent)?;
    recover_source(ctx, release)
}

/// 仅列出持久身份验证通过且未绑定到任意release的实例，不接管或修改它们。
pub(super) fn list_unbound(root: &Path, release: &Release) -> Result<Vec<String>> {
    let layout = Layout::new(root, &release.id)?;
    let directory = root.join("state/instances");
    layout.guard_path(&directory)?;
    if !directory.exists() {
        return Ok(vec![]);
    }
    let registry = Registry::load(root)?;
    let mut result = vec![];
    let mut count = 0;
    for item in fs::read_dir(directory)? {
        count += 1;
        if count > 500 {
            bail!("实例记录超过500项，请保留现场诊断");
        }
        let item = item?;
        let path = item.path();
        layout.guard_path(&path)?;
        if path.extension().is_some_and(|value| value == "tmp") {
            continue;
        }
        if !item.file_type()?.is_file() || path.extension().is_none_or(|value| value != "json") {
            bail!("实例记录目录包含未知项目");
        }
        let id = path
            .file_stem()
            .and_then(|value| value.to_str())
            .context("实例记录文件名无效")?;
        if registry.installed.iter().any(|record| {
            record
                .gui
                .as_ref()
                .is_some_and(|binding| binding.instance_id == id)
        }) {
            continue;
        }
        // release_id只用于路由到验证器，未通过完整load之前不信任任何字段。
        if fs::metadata(&path)?.len() > 32 * 1024 * 1024 {
            bail!("实例记录超过可读上限");
        }
        let routed = (|| -> Result<Layout> {
            let value: serde_json::Value = serde_json::from_slice(&fs::read(&path)?)?;
            let owner = value
                .get("release_id")
                .and_then(|value| value.as_str())
                .context("实例缺少release路由身份")?;
            Layout::new(root, owner)
        })();
        let owned = routed.and_then(|owner| instances::load(&owner, id));
        match owned {
            Ok(state) => {
                let environment = instances::path(&state)?;
                if state.release_id() != release.id {
                    continue;
                }
                result.push(format!("未绑定GUI实例 {}（generation {}，{}，路径 {}）；保留原实例，重新安装会创建新候选", state.id(), state.generation(), if state.dirty() { "dirty，尚未验证" } else { "clean，验证后尚未提交绑定" }, environment.display()));
            }
            Err(error) => result.push(format!(
                "未绑定实例记录 {id} 无法按当前版本读取：{error:#}；原文件保留"
            )),
        }
    }
    result.sort();
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture {
        root: PathBuf,
        ctx: WorkspaceMutation,
        release: Release,
    }
    impl Fixture {
        fn new() -> Self {
            let release = model::Catalog::embedded().unwrap().releases[0].clone();
            let root = std::env::temp_dir().join(format!(
                "nt-gui-publish-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
            Self { root, ctx, release }
        }
        fn pending(&self) -> Intent {
            let layout = self.ctx.layout();
            layout.ensure_dir(&layout.release_dir).unwrap();
            fs::write(layout.release_dir.join("old.txt"), b"old source").unwrap();
            let stage = self.root.join("staging/locked-source-test");
            layout.ensure_dir(&stage).unwrap();
            fs::write(stage.join("new.txt"), b"new source").unwrap();
            let intent = Intent {
                schema_version: 1,
                root: self.root.clone(),
                release: self.release.clone(),
                staging: PathBuf::from("staging/locked-source-test"),
                backup: Path::new("backups").join(format!("source-{}-test", self.release.id)),
                target: Path::new("releases").join(&self.release.id),
                staged: fingerprint(layout, &stage).unwrap(),
                previous: Some(fingerprint(layout, &layout.release_dir).unwrap()),
                phase: Phase::Pending,
            };
            save(layout, &intent).unwrap();
            intent
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
                    .starts_with("nt-gui-publish-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }
    #[test]
    fn restart_rolls_back_exact_old_tree_if_stage_was_lost() {
        let f = Fixture::new();
        let intent = f.pending();
        let layout = f.ctx.layout();
        fs::rename(&layout.release_dir, f.root.join(&intent.backup)).unwrap();
        fs::remove_file(f.root.join(&intent.staging).join("new.txt")).unwrap();
        fs::remove_dir(f.root.join(&intent.staging)).unwrap();
        recover_source(&f.ctx, &f.release).unwrap();
        assert_eq!(
            fs::read(layout.release_dir.join("old.txt")).unwrap(),
            b"old source"
        );
        assert_eq!(
            load(layout, &f.release).unwrap().unwrap().phase,
            Phase::RolledBack
        );
    }
    #[test]
    fn unknown_target_or_future_schema_preserves_every_original_byte() {
        let f = Fixture::new();
        let intent = f.pending();
        let layout = f.ctx.layout();
        fs::write(layout.release_dir.join("old.txt"), b"external mutation").unwrap();
        assert!(recover_source(&f.ctx, &f.release).is_err());
        assert_eq!(
            fs::read(layout.release_dir.join("old.txt")).unwrap(),
            b"external mutation"
        );
        assert!(f.root.join(&intent.staging).exists());
        let record = record_path(layout, &f.release).unwrap();
        let mut value = serde_json::to_value(intent).unwrap();
        value["schema_version"] = 999.into();
        let bytes = serde_json::to_vec(&value).unwrap();
        fs::write(&record, &bytes).unwrap();
        assert!(recover_source(&f.ctx, &f.release).is_err());
        assert_eq!(fs::read(record).unwrap(), bytes);
    }
    #[test]
    fn unbound_instance_discovery_validates_identity_and_preserves_state() {
        let f = Fixture::new();
        let state =
            instances::create(&f.ctx, "g0000000000000001", "recipe-one", &"b".repeat(64)).unwrap();
        let record = f.root.join("state/instances/g0000000000000001.json");
        let bytes = fs::read(&record).unwrap();
        let rows = list_unbound(&f.root, &f.release).unwrap();
        assert_eq!(rows.len(), 1);
        assert!(rows[0].contains("g0000000000000001") && rows[0].contains("dirty"));
        assert_eq!(fs::read(&record).unwrap(), bytes);
        assert!(instances::path(&state).unwrap().exists());
        let mut value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        value["schema_version"] = 999.into();
        let changed = serde_json::to_vec(&value).unwrap();
        fs::write(&record, &changed).unwrap();
        assert!(list_unbound(&f.root, &f.release).unwrap()[0].contains("无法按当前版本读取"));
        assert_eq!(fs::read(record).unwrap(), changed);
    }
}
