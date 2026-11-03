//! 只读查询执行者：身份读取在后台完成，管理器锁内不进行文件或进程 I/O。
use super::{engine_bridge, Logger};
use crate::{
    model::{self, Catalog, Layout},
    query_tasks::{
        CleanupProof, QueryError, QueryHandle, QueryIdentity, QueryResolution, QueryTarget,
    },
};
use anyhow::{bail, Context, Result};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    thread,
    time::Duration,
};

const CONTROL_LIMIT: u64 = 32 * 1024 * 1024;
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read_control(layout: &Layout, path: &Path, handle: &QueryHandle) -> Result<Option<Vec<u8>>> {
    handle.check()?;
    layout.guard_path(path)?;
    let metadata = match fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    if !metadata.is_file() || metadata.len() > CONTROL_LIMIT {
        bail!("检查控制文件不是受限普通文件");
    }
    let mut file = File::open(path)?;
    let mut bytes = Vec::new();
    let mut block = [0; 64 * 1024];
    loop {
        handle.check()?;
        let count = file.read(&mut block)?;
        if count == 0 {
            break;
        }
        if bytes.len() + count > CONTROL_LIMIT as usize {
            bail!("检查控制文件超过大小上限");
        }
        bytes.extend_from_slice(&block[..count]);
    }
    handle.check()?;
    if file.metadata()?.len() != metadata.len() || bytes.len() as u64 != metadata.len() {
        bail!("检查身份读取期间文件变化");
    }
    Ok(Some(bytes))
}

#[cfg(windows)]
fn directory_fence(root: &Path) -> Result<String> {
    use std::os::windows::{fs::OpenOptionsExt, io::AsRawHandle};
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION, FILE_FLAG_BACKUP_SEMANTICS,
    };
    let directory = fs::OpenOptions::new()
        .read(true)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
        .open(root)?;
    let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    if unsafe { GetFileInformationByHandle(directory.as_raw_handle() as _, &mut info) } == 0 {
        return Err(std::io::Error::last_os_error()).context("读取工作区卷及目录身份失败");
    }
    Ok(format!(
        "{}:{}:{}:{}:{}",
        info.dwVolumeSerialNumber,
        info.nFileIndexHigh,
        info.nFileIndexLow,
        info.ftCreationTime.dwHighDateTime,
        info.ftCreationTime.dwLowDateTime
    ))
}
#[cfg(unix)]
fn directory_fence(root: &Path) -> Result<String> {
    use std::os::unix::fs::MetadataExt;
    let metadata = fs::metadata(root)?;
    Ok(format!("{}:{}", metadata.dev(), metadata.ino()))
}
#[cfg(not(any(windows, unix)))]
fn directory_fence(_root: &Path) -> Result<String> {
    bail!("当前平台不支持可靠的工作区目录身份");
}

fn canonical_root(root: &Path) -> Result<PathBuf> {
    let canonical = fs::canonicalize(root)?;
    #[cfg(windows)]
    {
        let value = canonical.to_str().context("工作区路径不是有效Unicode")?;
        if let Some(drive_path) = value.strip_prefix(r"\\?\") {
            if drive_path.starts_with("UNC\\") {
                bail!("检查不支持网络工作区");
            }
            return Ok(PathBuf::from(drive_path));
        }
    }
    Ok(canonical)
}

pub(crate) fn identity(target: &QueryTarget, handle: &QueryHandle) -> Result<QueryIdentity> {
    handle.check()?;
    let requested = Path::new(&target.root);
    Layout::new(requested, &target.release_id)?.guard_path(requested)?;
    let root = canonical_root(requested)?;
    let layout = Layout::new(&root, &target.release_id)?;
    let marker = read_control(&layout, &root.join(".launcher-workspace"), handle)?
        .context("缺少受管工作区标记")?;
    if marker != model::WORKSPACE_MARKER.as_bytes() {
        bail!("只可检查正式启动器工作区");
    }
    let fence = directory_fence(&root)?;
    if target.engine_id == "gui" {
        let registry_bytes = read_control(&layout, &root.join("state/registry.json"), handle)?
            .context("重装预览缺少正式登记")?;
        let registry: model::Registry = serde_json::from_slice(&registry_bytes)?;
        registry.validate()?;
        let binding = registry.gui_binding(&target.release_id);
        let state = match binding {
            Some(binding) => read_control(
                &layout,
                &root
                    .join("state/instances")
                    .join(format!("{}.json", binding.instance_id)),
                handle,
            )?,
            None => None,
        };
        let receipt = read_control(&layout, &layout.release_dir.join("release.json"), handle)?;
        // 历史修复预览还绑定原安装事务，避免旧计划在journal变化后被复用。
        let state =
            if target.action == crate::query_tasks::QueryAction::LegacyEnvironmentRepairPreview {
                let original = super::legacy_install_recovery::candidate(
                    &root,
                    &Catalog::for_workspace(&root)?
                        .release(&target.release_id)?
                        .clone(),
                )?
                .context("没有可修复的未完成历史安装")?;
                Some(serde_json::to_vec(&(state.as_deref(), original))?)
            } else {
                state
            };
        // 唯一内置配方仍由其正式解码器验证，不能信任工作区自述摘要。
        crate::recipe::GuiRecipe::embedded()?;
        let lock_sha256 = digest(include_bytes!("../../catalog/gui-cp310-win-x64-v1.lock"));
        let mut normalized = target.clone();
        normalized.root = root.to_str().context("工作区路径无效")?.to_owned();
        handle.check()?;
        return Ok(QueryIdentity {
            target: normalized,
            workspace_fence: digest(format!("{fence}:{}", digest(&marker)).as_bytes()),
            instance_id: binding.map(|value| value.instance_id.clone()),
            generation: binding.map(|value| value.generation),
            state_sha256: state.as_deref().map(digest),
            receipt_sha256: receipt.as_deref().map(digest),
            binding_sha256: Some(digest(&registry_bytes)),
            recipe_sha256: lock_sha256.clone(),
            lock_sha256,
        });
    }
    let state_root = root
        .join("state/engines")
        .join(&target.release_id)
        .join(&target.engine_id);
    let state = read_control(&layout, &state_root.join("state.json"), handle)?;
    let parsed = state
        .as_ref()
        .map(|bytes| serde_json::from_slice::<Value>(bytes))
        .transpose()?;
    let instance = parsed
        .as_ref()
        .and_then(|value| value["instance_id"].as_str())
        .map(str::to_owned);
    let generation = parsed
        .as_ref()
        .and_then(|value| value["generation"].as_u64());
    if let Some(instance) = &instance {
        model::validate_component(instance)?;
    }
    // dirty 新代次仍引用上一已验证代次；观察实际receipt，而非不存在的新代次路径。
    let receipt_generation = parsed
        .as_ref()
        .and_then(|value| value["validated_generation"].as_u64())
        .or(generation);
    let receipt = match (&instance, receipt_generation) {
        (Some(_), Some(0)) => None,
        (Some(instance), Some(generation)) => read_control(
            &layout,
            &state_root
                .join("instances")
                .join(instance)
                .join(format!("{generation}.json")),
            handle,
        )?,
        (None, None) if state.is_none() => None,
        _ => bail!("引擎绑定缺少实例或代次"),
    };
    let binding = read_control(&layout, &root.join("state/registry.json"), handle)?;
    let lock = engine_bridge::embedded_lock(&target.engine_id).context("缺少固定引擎资产锁")?;
    let lock_value: Value = serde_json::from_slice(lock)?;
    let recipe_sha256 = lock_value["recipe_sha256"]
        .as_str()
        .context("资产锁缺少配方摘要")?
        .to_owned();
    handle.check()?;
    let mut normalized = target.clone();
    normalized.root = root.to_str().context("工作区路径无效")?.to_owned();
    Ok(QueryIdentity {
        target: normalized,
        workspace_fence: digest(format!("{fence}:{}", digest(&marker)).as_bytes()),
        instance_id: instance,
        generation,
        state_sha256: state.as_deref().map(digest),
        receipt_sha256: receipt.as_deref().map(digest),
        binding_sha256: binding.as_deref().map(digest),
        lock_sha256: digest(lock),
        recipe_sha256,
    })
}

fn query_error(error: anyhow::Error) -> QueryError {
    match error.downcast::<QueryError>() {
        Ok(error) => error,
        Err(error) => QueryError::new("query_failed", format!("{error:#}")),
    }
}

pub(crate) fn run(mut handle: QueryHandle, target: QueryTarget, log: Logger) {
    // 此段没有启动外部资源，失败可以用 no_worker_started 收口。
    let resolved = (|| -> Result<Option<(QueryIdentity, model::Release)>> {
        let identity = identity(&target, &handle)?;
        let catalog = Catalog::for_workspace(Path::new(&identity.target.root))?;
        let release = catalog.release(&target.release_id)?.clone();
        match handle.resolve(identity.clone())? {
            QueryResolution::Joined(snapshot) => {
                log(format!(
                    "[INFO] 检查 {} 复用任务 {} {:?}",
                    handle.task_id(),
                    snapshot.canonical_task_id,
                    snapshot.status
                ));
                return Ok(None);
            }
            QueryResolution::Stopped => {
                handle.check()?;
                bail!("检查已停止");
            }
            QueryResolution::Execute => {}
        }
        loop {
            handle.check()?;
            if handle.try_start()? {
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
        // 排队后重新核身份，不把旧代次送给 worker。
        if identity != self::identity(&identity.target, &handle)? {
            bail!("排队期间检查目标已变化，请重新检查");
        }
        Ok(Some((identity, release)))
    })();
    let (expected, release) = match resolved {
        Ok(Some(value)) => value,
        Ok(None) => return,
        Err(error) => {
            let error = query_error(error);
            log(format!("[WARN] 检查未启动 {}：{}", handle.task_id(), error));
            let _ = handle.finish(Err(error), None, CleanupProof::no_worker_started());
            return;
        }
    };
    if expected.target.engine_id == "gui" {
        let observer = handle.observer();
        let result = crate::scan_observation::with(&observer, || {
            if expected.target.action
                == crate::query_tasks::QueryAction::LegacyEnvironmentRepairPreview
            {
                super::Engine::preview_legacy_environment_repair_controlled(
                    Path::new(&expected.target.root),
                    &release.id,
                    &handle.cancel_token(),
                    Some(&observer),
                )
            } else {
                super::gui_rebuild::preview_controlled(
                    Path::new(&expected.target.root),
                    &release,
                    &handle.cancel_token(),
                )
            }
        })
        .map_err(query_error);
        let current = if result.is_ok() {
            identity(&expected.target, &handle).ok()
        } else {
            None
        };
        match handle.finish(result, current, CleanupProof::no_worker_started()) {
            Ok(snapshot) => log(format!(
                "[INFO] 主程序重装预览 {} {:?}",
                snapshot.task_id, snapshot.status
            )),
            Err(error) => log(format!(
                "[ERROR] 主程序重装预览未收口 {}：{}",
                handle.task_id(),
                error
            )),
        }
        return;
    }
    let mut outcome = engine_bridge::query_managed(
        Path::new(&expected.target.root),
        &release,
        &expected.target.engine_id,
        expected.target.action.as_str(),
        expected.target.rebuild,
        expected.target.scope,
        &handle,
        &log,
    );
    while outcome.cleanup.is_none() {
        let _ = handle.cleanup_pending(QueryError::new(
            "query_cleanup_pending",
            "正在回收本次检查进程与管道",
        ));
        match outcome.pending.as_mut() {
            Some(pending) => match pending.reap() {
                Ok(proof) => {
                    outcome.cleanup = proof;
                    if outcome.cleanup.is_some() {
                        outcome.cleanup_observation = pending.cleanup_observation();
                    }
                }
                Err(error) => log(format!(
                    "[WARN] 检查回收仍未确认 {}：{error:#}",
                    handle.task_id()
                )),
            },
            None => {
                // 不丢弃没有回收证明的任务，也不伪造 no_worker_started。
                log(format!("[ERROR] 检查缺少资源回收归属 {}", handle.task_id()));
                return;
            }
        }
        if outcome.cleanup.is_none() {
            thread::sleep(Duration::from_millis(100));
        }
    }
    if let Some(observation) = &outcome.cleanup_observation {
        match serde_json::to_string(observation) {
            Ok(details) => log(format!(
                "[INFO] 检查资源已回收 {} {details}",
                handle.task_id()
            )),
            Err(error) => log(format!(
                "[WARN] 检查回收记录序列化失败 {}：{error}",
                handle.task_id()
            )),
        }
    }
    let current = if outcome.result.is_ok() {
        identity(&expected.target, &handle).ok()
    } else {
        None
    };
    let result = outcome.result.map_err(query_error);
    match handle.finish(
        result,
        current,
        outcome.cleanup.expect("loop requires real cleanup proof"),
    ) {
        Ok(snapshot) => log(format!(
            "[INFO] 引擎检查 {} {:?}",
            snapshot.task_id, snapshot.status
        )),
        Err(error) => log(format!(
            "[ERROR] 检查终态未确认 {}：{}",
            handle.task_id(),
            error
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        model::{Registry, WorkspaceMutation},
        query_tasks::*,
    };
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        root: PathBuf,
        target: QueryTarget,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "ntq-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            assert!(!root.exists());
            let release = Catalog::embedded().unwrap().releases[0].id.clone();
            let workspace = WorkspaceMutation::acquire(&root, &release).unwrap();
            Registry::default().store(&root).unwrap();
            drop(workspace);
            Self {
                target: QueryTarget {
                    root: root.to_string_lossy().into_owned(),
                    release_id: release,
                    engine_id: "kohya".into(),
                    action: QueryAction::InspectReadonly,
                    rebuild: false,
                    scope: QueryScope::Full,
                },
                root,
            }
        }
        fn handle(&self) -> (QueryTaskManager, QueryHandle) {
            let manager = QueryTaskManager::default();
            let admission = manager
                .begin(
                    self.target.clone(),
                    QueryClock::start(Duration::from_secs(30)).unwrap(),
                )
                .unwrap();
            (manager, admission.handle)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            assert!(self.root.starts_with(std::env::temp_dir()));
            assert!(self
                .root
                .file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("ntq-"));
            fs::remove_dir_all(&self.root).unwrap();
        }
    }

    #[test]
    fn identity_observes_state_and_receipt_changes_without_writing_controls() {
        let f = Fixture::new();
        let (_manager, handle) = f.handle();
        let empty = identity(&f.target, &handle).unwrap();
        assert!(empty.instance_id.is_none());
        let state_root = f
            .root
            .join("state/engines")
            .join(&f.target.release_id)
            .join("kohya");
        let instance = "t0123456789abcde";
        let receipts = state_root.join("instances").join(instance);
        fs::create_dir_all(&receipts).unwrap();
        let state_bytes = br#"{"instance_id":"t0123456789abcde","generation":1}"#;
        fs::write(state_root.join("state.json"), state_bytes).unwrap();
        fs::write(receipts.join("1.json"), b"first receipt").unwrap();
        let first = identity(&f.target, &handle).unwrap();
        assert_eq!(first.instance_id.as_deref(), Some(instance));
        assert_eq!(first.generation, Some(1));
        assert_ne!(empty, first);
        fs::write(receipts.join("1.json"), b"other receipt").unwrap();
        let second = identity(&f.target, &handle).unwrap();
        assert_ne!(first.receipt_sha256, second.receipt_sha256);
        assert_eq!(first.state_sha256, second.state_sha256);
        assert_eq!(
            fs::read(state_root.join("state.json")).unwrap(),
            state_bytes
        );
        assert_eq!(first.workspace_fence, second.workspace_fence);
    }

    #[test]
    fn cancelled_identity_does_not_start_io_or_initialize_missing_state() {
        let f = Fixture::new();
        let (manager, handle) = f.handle();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        manager.cancel(handle.task_id()).unwrap();
        assert!(identity(&f.target, &handle).is_err());
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        assert!(!f.root.join("state/engines").exists());
    }

    #[test]
    fn gui_preview_identity_tracks_release_receipt_without_mutating_registry() {
        let mut f = Fixture::new();
        f.target.engine_id = "gui".into();
        f.target.action = QueryAction::GuiRebuildPreview;
        f.target.scope = QueryScope::Plan;
        f.target.rebuild = true;
        let (_manager, handle) = f.handle();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let before = identity(&f.target, &handle).unwrap();
        let release = f.root.join("releases").join(&f.target.release_id);
        fs::create_dir_all(&release).unwrap();
        fs::write(release.join("release.json"), b"receipt identity change").unwrap();
        let after = identity(&f.target, &handle).unwrap();
        assert_ne!(before.receipt_sha256, after.receipt_sha256);
        assert_eq!(before.workspace_fence, after.workspace_fence);
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
    }

    #[test]
    fn dirty_generation_identity_still_observes_last_validated_receipt() {
        let f = Fixture::new();
        let (_manager, handle) = f.handle();
        let state_root = f
            .root
            .join("state/engines")
            .join(&f.target.release_id)
            .join("kohya");
        let instance = "t0123456789abcde";
        let receipts = state_root.join("instances").join(instance);
        fs::create_dir_all(&receipts).unwrap();
        fs::write(
            state_root.join("state.json"),
            br#"{"instance_id":"t0123456789abcde","generation":2,"validated_generation":1}"#,
        )
        .unwrap();
        fs::write(receipts.join("1.json"), b"original receipt").unwrap();
        let first = identity(&f.target, &handle).unwrap();
        fs::write(receipts.join("1.json"), b"modified receipt").unwrap();
        let second = identity(&f.target, &handle).unwrap();
        assert_eq!(first.generation, Some(2));
        assert_ne!(first.receipt_sha256, second.receipt_sha256);
        assert_eq!(first.state_sha256, second.state_sha256);
    }

    #[test]
    fn directory_replacement_changes_the_workspace_fence() {
        let f = Fixture::new();
        let (_manager, handle) = f.handle();
        let before = identity(&f.target, &handle).unwrap();
        let original = f.root.with_extension("previous");
        assert!(!original.exists());
        fs::rename(&f.root, &original).unwrap();
        fs::create_dir(&f.root).unwrap();
        fs::write(f.root.join(".launcher-workspace"), model::WORKSPACE_MARKER).unwrap();
        fs::create_dir(f.root.join("state")).unwrap();
        fs::copy(
            original.join("state/registry.json"),
            f.root.join("state/registry.json"),
        )
        .unwrap();
        let after = identity(&f.target, &handle).unwrap();
        assert_ne!(before.workspace_fence, after.workspace_fence);
        assert_eq!(before.binding_sha256, after.binding_sha256);
        assert!(original.starts_with(std::env::temp_dir()));
        fs::remove_dir_all(original).unwrap();
    }
}
