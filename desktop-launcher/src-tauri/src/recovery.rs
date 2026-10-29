//! P6 单个合成文件的中断恢复样机；不是生产 GUI RepairPlan 或 v1 状态迁移。
//! 所有写入口借用同一个 WorkspaceMutation，绝不在内部重取 workspace lease。
use crate::model::{self, Layout, WorkspaceMutation};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::Read,
    path::{Component, Path, PathBuf},
};

const SCHEMA: u32 = 2;
const SCOPE: &str = "p6-synthetic-single-file";
const MAX_FILE_BYTES: u64 = 1024 * 1024;
const MAX_PRESERVED: usize = 64;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Fingerprint {
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    operation_id: String,
    base_generation: u64,
    relative_path: PathBuf,
    fingerprint: Fingerprint,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct InstanceState {
    schema_version: u32,
    scope: String,
    instance_id: String,
    release_id: String,
    root_absolute: PathBuf,
    target_relative: PathBuf,
    pub generation: u64,
    verified_generation: u64,
    pub dirty: bool,
    verified: Fingerprint,
    preserved: BTreeMap<PathBuf, Fingerprint>,
    pending: Option<Snapshot>,
}

/// 只标识已持久化的修改许可；丢弃 ticket 或取消操作不会清除 dirty。
#[derive(Clone, Debug)]
pub struct MutationTicket {
    root_absolute: PathBuf,
    instance_id: String,
    operation_id: String,
    pub generation: u64,
    pub target_path: PathBuf,
    pub snapshot_path: PathBuf,
}

fn release_id(layout: &Layout) -> Result<&str> {
    layout
        .release_dir
        .file_name()
        .and_then(|name| name.to_str())
        .context("P6 布局缺少有效 release ID")
}

fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        bail!("P6 路径必须为非空相对路径");
    }
    for component in path.components() {
        match component {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("P6 路径不是 UTF-8")?)?;
            }
            _ => bail!("P6 路径不允许跳转或盘符"),
        }
    }
    Ok(())
}

fn state_path(layout: &Layout, id: &str) -> Result<PathBuf> {
    model::validate_component(id)?;
    let path = layout
        .root
        .join("state/recovery-v2")
        .join(format!("{id}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}

fn target_path(layout: &Layout, id: &str, target: &Path) -> Result<PathBuf> {
    relative(target)?;
    let allowed = Path::new("staging").join("p6-synthetic").join(id);
    if !target.starts_with(&allowed) || target == allowed {
        bail!("P6 仅允许修改本实例 staging/p6-synthetic/<id>/ 内的合成文件");
    }
    let path = layout.root.join(target);
    layout.guard_path(&path)?;
    Ok(path)
}

fn snapshot_relative(id: &str, operation: &str, generation: u64) -> Result<PathBuf> {
    model::validate_component(id)?;
    model::validate_component(operation)?;
    Ok(Path::new("backups/p6-recovery")
        .join(id)
        .join(operation)
        .join(format!("generation-{generation}.bin")))
}

fn fingerprint(layout: &Layout, path: &Path) -> Result<Fingerprint> {
    layout.guard_path(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() > MAX_FILE_BYTES {
        bail!("P6 只接受不超过 1MiB 的普通文件：{}", path.display());
    }
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0u8; 16384];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > MAX_FILE_BYTES {
            bail!("P6 文件在读取时超过 1MiB");
        }
        hasher.update(&buffer[..count]);
    }
    Ok(Fingerprint {
        bytes,
        sha256: format!("{:x}", hasher.finalize()),
    })
}

fn valid_fingerprint(value: &Fingerprint) -> bool {
    value.bytes <= MAX_FILE_BYTES
        && value.sha256.len() == 64
        && value
            .sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_state(layout: &Layout, id: &str, state: &InstanceState) -> Result<()> {
    if state.schema_version != SCHEMA || state.scope != SCOPE {
        bail!("P6 recovery schema/scope 不支持；保留原文件并拒绝写入");
    }
    if state.instance_id != id
        || state.root_absolute != layout.root
        || state.release_id != release_id(layout)?
        || !valid_fingerprint(&state.verified)
        || state.preserved.is_empty()
        || state.preserved.len() > MAX_PRESERVED
    {
        bail!("P6 状态身份、路径或摘要无效");
    }
    target_path(layout, id, &state.target_relative)?;
    let profile = layout
        .profile
        .join("profile.json")
        .strip_prefix(&layout.root)?
        .to_path_buf();
    if !state.preserved.contains_key(&profile) {
        bail!("P6 状态缺少 profile 保护摘要");
    }
    for (path, digest) in &state.preserved {
        validate_preserved(layout, &state.target_relative, path)?;
        if !valid_fingerprint(digest) {
            bail!("P6 非目标文件摘要无效");
        }
    }
    match (&state.pending, state.dirty) {
        (None, false) if state.verified_generation == state.generation => {}
        (Some(snapshot), true)
            if snapshot.base_generation == state.verified_generation
                && snapshot.base_generation.checked_add(1) == Some(state.generation)
                && snapshot.fingerprint == state.verified
                && snapshot.relative_path
                    == snapshot_relative(id, &snapshot.operation_id, state.generation)? =>
        {
            layout.guard_path(&layout.root.join(&snapshot.relative_path))?;
        }
        _ => bail!("P6 dirty/generation/snapshot 状态不一致"),
    }
    Ok(())
}

fn validate_preserved(layout: &Layout, target: &Path, path: &Path) -> Result<()> {
    relative(path)?;
    if path == target
        || path.starts_with("state/recovery-v2")
        || path.starts_with("backups/p6-recovery")
    {
        bail!("P6 保护清单不能包含目标或恢复控制文件");
    }
    layout.guard_path(&layout.root.join(path))
}

fn check_preserved(layout: &Layout, state: &InstanceState) -> Result<()> {
    for (path, expected) in &state.preserved {
        if fingerprint(layout, &layout.root.join(path))? != *expected {
            bail!("P6 非目标文件已变化，保持 dirty：{}", path.display());
        }
    }
    Ok(())
}

/// 不创建、不迁移、不修复状态；未知 schema 或未知字段原样拒读。
pub fn load(layout: &Layout, id: &str) -> Result<InstanceState> {
    let path = state_path(layout, id)?;
    let metadata = fs::symlink_metadata(&path)?;
    if !metadata.is_file() || metadata.len() > 64 * 1024 {
        bail!("P6 状态不是受限普通文件，拒绝读取或修改");
    }
    let state: InstanceState = serde_json::from_slice(&fs::read(path)?)?;
    validate_state(layout, id, &state)?;
    Ok(state)
}

/// 首次登记已经存在的合成目标；profile.json 始终加入保护集。
pub fn initialize_synthetic(
    ctx: &WorkspaceMutation,
    id: &str,
    target_rel: &Path,
    preserved: &[PathBuf],
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let path = state_path(layout, id)?;
    if path.exists() {
        let _ = load(layout, id)?;
        bail!("P6 实例已经登记，不覆盖原记录");
    }
    if preserved.len() >= MAX_PRESERVED {
        bail!("P6 保护集过大");
    }
    let target = target_path(layout, id, target_rel)?;
    let mut fingerprints = BTreeMap::new();
    let profile = layout.profile.join("profile.json");
    for path in preserved
        .iter()
        .cloned()
        .chain(std::iter::once(profile.strip_prefix(&layout.root)?.into()))
    {
        validate_preserved(layout, target_rel, &path)?;
        fingerprints.insert(path.clone(), fingerprint(layout, &layout.root.join(path))?);
    }
    let state = InstanceState {
        schema_version: SCHEMA,
        scope: SCOPE.into(),
        instance_id: id.into(),
        release_id: release_id(layout)?.into(),
        root_absolute: layout.root.clone(),
        target_relative: target_rel.into(),
        generation: 0,
        verified_generation: 0,
        dirty: false,
        verified: fingerprint(layout, &target)?,
        preserved: fingerprints,
        pending: None,
    };
    validate_state(layout, id, &state)?;
    model::write_json_atomic(&path, &state)?;
    Ok(state)
}

/// 重新核对磁盘状态，公开字段的内存修改或旧的 clean 副本不能解锁 dirty 实例。
pub fn assert_usable(state: &InstanceState) -> Result<()> {
    let layout = Layout::new(&state.root_absolute, &state.release_id)?;
    let current = load(&layout, &state.instance_id)?;
    if &current != state || current.dirty {
        bail!("P6 实例 dirty 或记录已经过期，禁止使用");
    }
    let target = target_path(&layout, &current.instance_id, &current.target_relative)?;
    if fingerprint(&layout, &target)? != current.verified {
        bail!("P6 目标与已验证 generation 不符");
    }
    check_preserved(&layout, &current)
}

fn copy_new(layout: &Layout, source: &Path, target: &Path) -> Result<Fingerprint> {
    layout.guard_path(source)?;
    layout.guard_path(target)?;
    layout.ensure_dir(target.parent().context("P6 快照缺少父目录")?)?;
    let mut input = File::open(source)?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    let count = std::io::copy(
        &mut Read::by_ref(&mut input).take(MAX_FILE_BYTES + 1),
        &mut output,
    )?;
    output.sync_all()?;
    if count > MAX_FILE_BYTES {
        bail!("P6 快照超过大小上限，未授权修改目标");
    }
    drop(output);
    fingerprint(layout, target)
}

pub fn begin(
    ctx: &WorkspaceMutation,
    id: &str,
    operation_id: &str,
    expected_generation: u64,
) -> Result<MutationTicket> {
    let layout = ctx.layout();
    let mut state = load(layout, id)?;
    let original_state = state.clone();
    assert_usable(&state)?;
    if state.generation != expected_generation {
        bail!("P6 generation 已变化，拒绝执行旧计划");
    }
    let generation = state
        .generation
        .checked_add(1)
        .context("P6 generation 溢出")?;
    let snapshot_rel = snapshot_relative(id, operation_id, generation)?;
    let snapshot_path = layout.root.join(&snapshot_rel);
    let target = target_path(layout, id, &state.target_relative)?;
    let copied = copy_new(layout, &target, &snapshot_path)?;
    if copied != state.verified || fingerprint(layout, &target)? != state.verified {
        bail!("P6 快照或目标在复制期间发生变化；目标尚未授权修改");
    }
    check_preserved(layout, &state)?;
    if load(layout, id)? != original_state {
        bail!("P6 状态在快照期间变化，拒绝覆盖");
    }
    state.pending = Some(Snapshot {
        operation_id: operation_id.into(),
        base_generation: state.generation,
        relative_path: snapshot_rel,
        fingerprint: copied,
    });
    state.generation = generation;
    state.dirty = true;
    validate_state(layout, id, &state)?;
    model::write_json_atomic(&state_path(layout, id)?, &state)?;
    Ok(MutationTicket {
        root_absolute: layout.root.clone(),
        instance_id: id.into(),
        operation_id: operation_id.into(),
        generation,
        target_path: target,
        snapshot_path,
    })
}

fn checked_snapshot(layout: &Layout, state: &InstanceState) -> Result<PathBuf> {
    if !state.dirty {
        bail!("P6 实例没有待恢复事务");
    }
    let snapshot = state.pending.as_ref().context("P6 缺少快照记录")?;
    let path = layout.root.join(&snapshot.relative_path);
    if fingerprint(layout, &path)? != snapshot.fingerprint {
        bail!("P6 快照损坏，保留 dirty 和当前目标");
    }
    check_preserved(layout, state)?;
    Ok(path)
}

fn validate_and_clean(
    layout: &Layout,
    mut state: InstanceState,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let original_state = state.clone();
    let target = target_path(layout, &state.instance_id, &state.target_relative)?;
    let before = fingerprint(layout, &target)?;
    validator(&target)?;
    if fingerprint(layout, &target)? != before {
        bail!("P6 验证器修改了目标，保持 dirty");
    }
    check_preserved(layout, &state)?;
    if load(layout, &state.instance_id)? != original_state {
        bail!("P6 状态在验收期间变化，保持原磁盘记录");
    }
    state.verified = before;
    state.verified_generation = state.generation;
    state.dirty = false;
    state.pending = None;
    validate_state(layout, &state.instance_id, &state)?;
    model::write_json_atomic(&state_path(layout, &state.instance_id)?, &state)?;
    Ok(state)
}

pub fn commit(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let state = load(layout, &ticket.instance_id)?;
    let snapshot = checked_snapshot(layout, &state)?;
    if ticket.root_absolute != layout.root
        || ticket.generation != state.generation
        || ticket.snapshot_path != snapshot
        || ticket.target_path != target_path(layout, &state.instance_id, &state.target_relative)?
        || state
            .pending
            .as_ref()
            .map(|pending| pending.operation_id.as_str())
            != Some(ticket.operation_id.as_str())
    {
        bail!("P6 ticket 不属于当前事务，拒绝提交");
    }
    validate_and_clean(layout, state, validator)
}

/// 只依靠 schema2 磁盘记录恢复；不需要旧进程的 ticket 或内存状态。
pub fn recover(
    ctx: &WorkspaceMutation,
    id: &str,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let state = load(layout, id)?;
    let snapshot = checked_snapshot(layout, &state)?;
    let target = target_path(layout, id, &state.target_relative)?;
    // 实例绝对路径不变；任何中途失败都仍由磁盘 dirty 禁止使用。
    let mut input = File::open(&snapshot)?;
    let mut output = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&target)?;
    let copied = std::io::copy(
        &mut Read::by_ref(&mut input).take(MAX_FILE_BYTES + 1),
        &mut output,
    )?;
    output.sync_all()?;
    drop(output);
    if copied > MAX_FILE_BYTES || fingerprint(layout, &target)? != state.verified {
        bail!("P6 同路径恢复摘要不符，保持 dirty");
    }
    validate_and_clean(layout, state, validator)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);
    const ORIGINAL: &[u8] = b"original-package\n";

    struct Fixture {
        root: PathBuf,
        release: String,
    }

    impl Fixture {
        fn new() -> Self {
            let base = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
                .map(PathBuf::from)
                .unwrap_or_else(std::env::temp_dir);
            let root = base.join(format!(
                "nt-p6-recovery-{}-{}-{} 中文 空格",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            assert!(!root.exists());
            let release = model::Catalog::embedded().unwrap().releases()[0].id.clone();
            let fixture = Self { root, release };
            let ctx = fixture.acquire();
            let target = fixture.target();
            ctx.layout().ensure_dir(target.parent().unwrap()).unwrap();
            fs::write(&target, ORIGINAL).unwrap();
            fs::write(target.with_file_name("other.py"), b"non-target\n").unwrap();
            model::Journal::new(&fixture.release)
                .unwrap()
                .store(&fixture.root)
                .unwrap();
            let journal = Path::new("state").join(format!("journal-{}.json", fixture.release));
            initialize_synthetic(
                &ctx,
                "demo",
                Path::new("staging/p6-synthetic/demo/package.py"),
                &[PathBuf::from("staging/p6-synthetic/demo/other.py"), journal],
            )
            .unwrap();
            fixture
        }
        fn acquire(&self) -> WorkspaceMutation {
            WorkspaceMutation::acquire(&self.root, &self.release).unwrap()
        }
        fn target(&self) -> PathBuf {
            self.root.join("staging/p6-synthetic/demo/package.py")
        }
    }

    fn original(path: &Path) -> Result<()> {
        if fs::read(path)? != ORIGINAL {
            bail!("合成包内容未恢复");
        }
        Ok(())
    }

    #[test]
    fn modified_file_cancel_stays_dirty_then_recovers_same_absolute_path() {
        let fixture = Fixture::new();
        let ctx = fixture.acquire();
        let clean = load(ctx.layout(), "demo").unwrap();
        let protected = clean.preserved.clone();
        let ticket = begin(&ctx, "demo", "cancel-after-write", 0).unwrap();
        let snapshot_path = ticket.snapshot_path.clone();
        fs::write(&ticket.target_path, b"partially installed\n").unwrap();
        assert_eq!(fs::read(&snapshot_path).unwrap(), ORIGINAL);
        drop(ticket); // 模拟取消：不得从 Drop 清 dirty。
        assert!(load(ctx.layout(), "demo").unwrap().dirty);
        assert!(assert_usable(&clean).is_err());
        drop(ctx);
        let restarted = fixture.acquire();
        let restored = recover(&restarted, "demo", original).unwrap();
        assert!(!restored.dirty);
        assert_eq!(restored.generation, 1);
        assert_eq!(restored.preserved, protected);
        assert_eq!(
            fixture.target(),
            restarted.layout().root.join(&restored.target_relative)
        );
        assert_usable(&restored).unwrap();
        assert_eq!(fs::read(snapshot_path).unwrap(), ORIGINAL);
    }

    #[test]
    fn failed_validation_and_damaged_snapshot_never_clear_dirty() {
        let fixture = Fixture::new();
        let ctx = fixture.acquire();
        let ticket = begin(&ctx, "demo", "validation-fails", 0).unwrap();
        fs::write(&ticket.target_path, b"changed").unwrap();
        assert!(commit(&ctx, &ticket, |_| bail!("实际验收失败")).is_err());
        assert!(recover(&ctx, "demo", |_| bail!("恢复后验收失败")).is_err());
        assert!(load(ctx.layout(), "demo").unwrap().dirty);
        fs::write(&ticket.target_path, b"second-partial").unwrap();
        fs::write(&ticket.snapshot_path, b"damaged snapshot").unwrap();
        assert!(recover(&ctx, "demo", original).is_err());
        assert_eq!(fs::read(&ticket.target_path).unwrap(), b"second-partial");
        assert!(load(ctx.layout(), "demo").unwrap().dirty);
    }

    #[test]
    fn commit_checks_protected_bytes_and_stale_generation() {
        let fixture = Fixture::new();
        let ctx = fixture.acquire();
        assert!(begin(&ctx, "demo", "stale-plan", 9).is_err());
        let ticket = begin(&ctx, "demo", "commit-one", 0).unwrap();
        fs::write(&ticket.target_path, b"valid replacement").unwrap();
        let non_target = fixture.target().with_file_name("other.py");
        fs::write(&non_target, b"unexpected change").unwrap();
        assert!(commit(&ctx, &ticket, |_| Ok(())).is_err());
        fs::write(non_target, b"non-target\n").unwrap();
        let next = commit(&ctx, &ticket, |path| {
            if fs::read(path)? != b"valid replacement" {
                bail!("候选不符");
            }
            Ok(())
        })
        .unwrap();
        assert_eq!(next.generation, 1);
        assert_usable(&next).unwrap();
        assert!(commit(&ctx, &ticket, |_| Ok(())).is_err());
        assert!(begin(&ctx, "demo", "stale-plan", 0).is_err());
    }

    #[test]
    fn unknown_schema_is_preserved_and_target_outside_synthetic_scope_is_rejected() {
        let fixture = Fixture::new();
        let ctx = fixture.acquire();
        let path = state_path(ctx.layout(), "demo").unwrap();
        let mut value: serde_json::Value =
            serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        value["schema_version"] = 999.into();
        let unknown = serde_json::to_vec_pretty(&value).unwrap();
        fs::write(&path, &unknown).unwrap();
        assert!(load(ctx.layout(), "demo").is_err());
        assert!(begin(&ctx, "demo", "unknown", 0).is_err());
        assert!(recover(&ctx, "demo", original).is_err());
        assert!(initialize_synthetic(
            &ctx,
            "demo",
            Path::new("staging/p6-synthetic/demo/package.py"),
            &[]
        )
        .is_err());
        assert_eq!(fs::read(path).unwrap(), unknown);
        let profile = ctx.layout().profile.join("profile.json");
        let before = fs::read(&profile).unwrap();
        assert!(initialize_synthetic(
            &ctx,
            "outside",
            Path::new("profiles/default/profile.json"),
            &[]
        )
        .is_err());
        assert_eq!(fs::read(profile).unwrap(), before);
        assert_eq!(fs::read(fixture.target()).unwrap(), ORIGINAL);
    }

    #[test]
    fn validator_writes_are_rejected_and_forged_clean_copy_cannot_unlock() {
        let fixture = Fixture::new();
        let ctx = fixture.acquire();
        let ticket = begin(&ctx, "demo", "read-only-validator", 0).unwrap();
        assert!(commit(&ctx, &ticket, |path| {
            fs::write(path, b"validator mutation")?;
            Ok(())
        })
        .is_err());
        let mut forged = load(ctx.layout(), "demo").unwrap();
        forged.dirty = false;
        assert!(assert_usable(&forged).is_err());
        assert!(load(ctx.layout(), "demo").unwrap().dirty);
    }
}
