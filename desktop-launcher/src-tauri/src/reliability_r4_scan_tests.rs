//! R1必要扫描基础合同：真实小文件/目录，确定性取消；不替代原生或时延验收。
use super::*;
use crate::operations::{Cancelled, OperationKind, OperationManager};
use std::{cell::RefCell, sync::Arc};

type ReadHook = Box<dyn FnMut(&Path, u64)>;
type VisitHook = Box<dyn FnMut(&Path)>;
thread_local! {
    static READ_HOOK: RefCell<Option<ReadHook>> = const { RefCell::new(None) };
    static VISIT_HOOK: RefCell<Option<VisitHook>> = const { RefCell::new(None) };
    static PHYSICAL_READ_HOOK: RefCell<Option<ReadHook>> = const { RefCell::new(None) };
    static REBUILD_LIMITS: RefCell<Option<(u64, usize)>> = const { RefCell::new(None) };
}
pub(super) fn rebuild_limits() -> Option<(u64, usize)> {
    REBUILD_LIMITS.with(|slot| *slot.borrow())
}
struct BudgetLimits;
impl BudgetLimits {
    fn new(bytes: u64, nodes: usize) -> Self {
        REBUILD_LIMITS.with(|slot| assert!(slot.replace(Some((bytes, nodes))).is_none()));
        Self
    }
}
impl Drop for BudgetLimits {
    fn drop(&mut self) {
        REBUILD_LIMITS.with(|slot| *slot.borrow_mut() = None);
    }
}
pub(super) fn after_read(path: &Path, bytes: u64) {
    READ_HOOK.with(|slot| {
        if let Some(hook) = slot.borrow_mut().as_mut() {
            hook(path, bytes);
        }
    });
}
pub(super) fn after_physical_read(path: &Path, bytes: u64) {
    PHYSICAL_READ_HOOK.with(|slot| {
        if let Some(hook) = slot.borrow_mut().as_mut() {
            hook(path, bytes);
        }
    });
}
pub(super) fn before_visit(path: &Path) {
    VISIT_HOOK.with(|slot| {
        if let Some(hook) = slot.borrow_mut().as_mut() {
            hook(path);
        }
    });
}
struct Hooks;
impl Hooks {
    fn read(hook: impl FnMut(&Path, u64) + 'static) -> Self {
        READ_HOOK.with(|slot| assert!(slot.replace(Some(Box::new(hook))).is_none()));
        Self
    }
    fn visit(hook: impl FnMut(&Path) + 'static) -> Self {
        VISIT_HOOK.with(|slot| assert!(slot.replace(Some(Box::new(hook))).is_none()));
        Self
    }
    fn physical_read(hook: impl FnMut(&Path, u64) + 'static) -> Self {
        PHYSICAL_READ_HOOK.with(|slot| assert!(slot.replace(Some(Box::new(hook))).is_none()));
        Self
    }
}
impl Drop for Hooks {
    fn drop(&mut self) {
        READ_HOOK.with(|slot| *slot.borrow_mut() = None);
        VISIT_HOOK.with(|slot| *slot.borrow_mut() = None);
        PHYSICAL_READ_HOOK.with(|slot| *slot.borrow_mut() = None);
    }
}

pub(crate) fn with_read_hook<T>(
    hook: impl FnMut(&Path, u64) + 'static,
    work: impl FnOnce() -> T,
) -> T {
    let _guard = Hooks::read(hook);
    work()
}

const CANDIDATE: &str = "g2222222222222222";
struct Fixture {
    ctx: WorkspaceMutation,
    root: PathBuf,
    canonical: PathBuf,
    marker: Vec<u8>,
}
impl Fixture {
    fn new() -> Self {
        let parent = std::env::var_os("NEXT_TRAINER_SCAN_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        assert!(parent.is_absolute());
        fs::create_dir_all(&parent).unwrap();
        let root = parent.join(format!(
            "nt-r4-scan-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        assert!(!root.exists());
        let ctx = WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
        let canonical = root.canonicalize().unwrap();
        let marker = format!("reliability_r4_scan_tests:{}", root.display()).into_bytes();
        fs::write(root.join(".codex-r4-scan-owner"), &marker).unwrap();
        let fixture = Self {
            ctx,
            root,
            canonical,
            marker,
        };
        fixture.write("e/g1111111111111111/keeper.bin", b"original");
        fixture
    }
    fn write(&self, relative: &str, content: &[u8]) -> PathBuf {
        let path = self.root.join(relative);
        self.ctx
            .layout()
            .ensure_dir(path.parent().unwrap())
            .unwrap();
        fs::write(&path, content).unwrap();
        path
    }
    fn boundary(&self) -> RebuildBoundary {
        rebuild_boundary(&self.ctx, &CancelToken::new()).unwrap()
    }
    fn candidate(&self, content: &[u8]) -> PathBuf {
        self.write(&format!("e/{CANDIDATE}/candidate.bin"), content)
    }
    fn check(&self, boundary: &RebuildBoundary, cancel: &CancelToken) -> Result<()> {
        rebuild_check_boundary(&self.ctx, boundary, CANDIDATE, cancel)
    }
    fn candidate_state(&self) -> InstanceState {
        InstanceState {
            schema_version: 2,
            component: "gui".into(),
            instance_id: CANDIDATE.into(),
            storage_version: 1,
            release_id: release(self.ctx.layout()).unwrap().into(),
            root_absolute: self.ctx.layout().root.clone(),
            recipe_id: "r4-fixture".into(),
            recipe_sha256: "a".repeat(64),
            generation: 1,
            validated_generation: 0,
            dirty: true,
            ignored: vec![],
            verified: Observation {
                environment: Tree::new(),
                profiles: Tree::new(),
                profiles_summary: None,
                protected: BTreeMap::new(),
            },
            pending: None,
            base_python_pending: None,
            registration_origin: None,
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        // 只回收本测试新建、绝对路径及内容标记均仍一致的目录。
        if self.root.canonicalize().ok().as_ref() == Some(&self.canonical)
            && fs::read(self.root.join(".codex-r4-scan-owner"))
                .ok()
                .as_ref()
                == Some(&self.marker)
        {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
}

#[test]
fn combined_budget_boundary_rejects_split_byte_allowances() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    fixture.candidate(b"12345678");
    let _limits = BudgetLimits::new(15, 50_000);
    let error = fixture.check(&boundary, &CancelToken::new()).unwrap_err();
    assert!(error.to_string().contains("实例树超出验证上限"));
}

#[test]
fn combined_budget_candidate_sha_rejects_split_byte_allowances() {
    let fixture = Fixture::new();
    fixture.candidate(b"12345678");
    let _limits = BudgetLimits::new(15, 50_000);
    let error =
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .unwrap_err();
    assert!(error.to_string().contains("实例树超出验证上限"));
}

#[test]
fn combined_budget_observe_rejects_split_byte_allowances() {
    let fixture = Fixture::new();
    fixture.candidate(b"12345678");
    let _limits = BudgetLimits::new(15, 50_000);
    let error = rebuild_observe_candidate(
        fixture.ctx.layout(),
        &fixture.candidate_state(),
        &CancelToken::new(),
    )
    .unwrap_err();
    assert!(error.to_string().contains("实例树超出验证上限"));
}

#[test]
fn combined_budget_production_limits_cannot_be_raised_by_test_overrides() {
    assert_eq!(MAX_TREE, 4 * 1024 * 1024 * 1024);
    assert_eq!(MAX_TREE_NODES, 50_000);
    assert_eq!(rebuild_tree_limits().bytes, MAX_TREE);
    assert_eq!(rebuild_tree_limits().nodes, MAX_TREE_NODES);
    let _limits = BudgetLimits::new(u64::MAX, usize::MAX);
    assert_eq!(rebuild_tree_limits().bytes, MAX_TREE);
    assert_eq!(rebuild_tree_limits().nodes, MAX_TREE_NODES);
}

#[test]
fn combined_budget_exact_limit_counts_e_root_and_candidate_root_once() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    fixture.candidate(b"12345678");
    // e根、旧实例目录/文件、候选目录/文件，共5节点、16字节。
    let _limits = BudgetLimits::new(16, 5);
    fixture.check(&boundary, &CancelToken::new()).unwrap();
    let actual =
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .unwrap();
    let candidate = fixture.root.join(format!("e/{CANDIDATE}"));
    let expected =
        hash(&serde_json::to_vec(&scan(fixture.ctx.layout(), &candidate, &[]).unwrap()).unwrap());
    assert_eq!(actual, expected);
    rebuild_observe_candidate(
        fixture.ctx.layout(),
        &fixture.candidate_state(),
        &CancelToken::new(),
    )
    .unwrap();
}

#[test]
fn combined_budget_node_limit_rejects_each_formal_observation_entry() {
    for entry in ["boundary", "sha", "observe"] {
        let fixture = Fixture::new();
        let boundary = fixture.boundary();
        fixture.candidate(b"12345678");
        // 非目标3节点、候选2节点，分别不过界，合计5>4。
        let _limits = BudgetLimits::new(16, 4);
        let error = match entry {
            "boundary" => fixture.check(&boundary, &CancelToken::new()).unwrap_err(),
            "sha" => rebuild_candidate_tree_sha_controlled(
                fixture.ctx.layout(),
                CANDIDATE,
                &CancelToken::new(),
            )
            .unwrap_err(),
            _ => rebuild_observe_candidate(
                fixture.ctx.layout(),
                &fixture.candidate_state(),
                &CancelToken::new(),
            )
            .unwrap_err(),
        };
        assert!(
            error.to_string().contains("实例树超出验证上限"),
            "{entry}: {error}"
        );
    }
}

#[test]
fn combined_budget_empty_candidate_directories_still_consume_nodes() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    fixture.candidate(b"12345678");
    fixture
        .ctx
        .layout()
        .ensure_dir(&fixture.root.join(format!("e/{CANDIDATE}/empty")))
        .unwrap();
    let _limits = BudgetLimits::new(16, 5);
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
    assert!(rebuild_candidate_tree_sha_controlled(
        fixture.ctx.layout(),
        CANDIDATE,
        &CancelToken::new(),
    )
    .is_err());
}

#[test]
fn combined_budget_actual_candidate_growth_stops_after_one_excess_byte() {
    for entry in ["sha", "observe"] {
        let fixture = Fixture::new();
        let path = fixture.candidate(&vec![0x51; 65_536]);
        let watched = path.clone();
        let reads = Arc::new(std::sync::Mutex::new(Vec::new()));
        let record = reads.clone();
        let mut extended = false;
        let _hooks = Hooks::physical_read(move |at, bytes| {
            if at == watched {
                record.lock().unwrap().push(bytes);
                if !extended && bytes != 0 {
                    extended = true;
                    OpenOptions::new()
                        .append(true)
                        .open(&watched)
                        .unwrap()
                        .write_all(&vec![0x52; 65_536])
                        .unwrap();
                }
            }
        });
        let _limits = BudgetLimits::new(8 + 65_536, 100);
        let error = if entry == "sha" {
            rebuild_candidate_tree_sha_controlled(
                fixture.ctx.layout(),
                CANDIDATE,
                &CancelToken::new(),
            )
            .unwrap_err()
        } else {
            rebuild_observe_candidate(
                fixture.ctx.layout(),
                &fixture.candidate_state(),
                &CancelToken::new(),
            )
            .unwrap_err()
        };
        assert!(
            error.to_string().contains("实例树超出验证上限"),
            "{entry}: {error}"
        );
        assert_eq!(*reads.lock().unwrap(), [65_536, 1], "{entry}");
        assert_eq!(fs::metadata(path).unwrap().len(), 2 * 65_536);
    }
}

#[test]
fn combined_budget_metadata_candidate_walk_uses_operation_cancel_without_reading_content() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    let watched = fixture.candidate(b"12345678");
    let manager = Arc::new(OperationManager::default());
    let operation = manager
        .start("r4-budget-walk", OperationKind::Repair)
        .unwrap();
    let cancelling = manager.clone();
    let _hooks = Hooks::visit(move |path| {
        if path == watched {
            cancelling.cancel("r4-budget-walk").unwrap();
        }
    });
    let _limits = BudgetLimits::new(15, 5);
    let error = fixture
        .check(&boundary, &operation.cancel_token())
        .unwrap_err();
    assert!(error.downcast_ref::<Cancelled>().is_some());
    assert!(manager.snapshot("r4-budget-walk").unwrap().cancel_requested);
}

#[test]
fn combined_budget_cancel_wins_over_growth_detected_in_same_physical_read() {
    let fixture = Fixture::new();
    let watched = fixture.candidate(&vec![0x51; 65_536]);
    let manager = Arc::new(OperationManager::default());
    let operation = manager
        .start("r4-budget-read", OperationKind::Repair)
        .unwrap();
    let cancelling = manager.clone();
    let mut reads = 0;
    let _hooks = Hooks::physical_read(move |path, bytes| {
        if path == watched && bytes != 0 {
            reads += 1;
            if reads == 1 {
                OpenOptions::new()
                    .append(true)
                    .open(&watched)
                    .unwrap()
                    .write_all(b"growth")
                    .unwrap();
            } else {
                cancelling.cancel("r4-budget-read").unwrap();
            }
        }
    });
    let _limits = BudgetLimits::new(8 + 65_536, 100);
    let error = rebuild_candidate_tree_sha_controlled(
        fixture.ctx.layout(),
        CANDIDATE,
        &operation.cancel_token(),
    )
    .unwrap_err();
    assert!(error.downcast_ref::<Cancelled>().is_some());
}

#[test]
fn combined_budget_checked_totals_reject_byte_and_node_overflow() {
    assert!(TreeUsage {
        bytes: u64::MAX,
        nodes: 0
    }
    .combine(TreeUsage { bytes: 1, nodes: 0 })
    .is_err());
    assert!(TreeUsage {
        bytes: 0,
        nodes: usize::MAX
    }
    .combine(TreeUsage { bytes: 0, nodes: 1 })
    .is_err());
}

#[test]
fn candidate_hash_accepts_operation_cancel_after_first_real_64k_read() {
    let fixture = Fixture::new();
    let path = fixture.candidate(&vec![0x5a; 3 * 65_536]);
    let manager = Arc::new(OperationManager::default());
    let operation = manager
        .start("r4-candidate", OperationKind::Repair)
        .unwrap();
    let cancel = operation.cancel_token();
    let observed = Arc::new(std::sync::Mutex::new(Vec::new()));
    let record = observed.clone();
    let cancel_manager = manager.clone();
    let watched = path.clone();
    let hooks = Hooks::read(move |at, bytes| {
        if at == watched {
            record.lock().unwrap().push(bytes);
            cancel_manager.cancel("r4-candidate").unwrap();
        }
    });
    let error = rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &cancel)
        .unwrap_err();
    assert!(error.downcast_ref::<Cancelled>().is_some());
    assert_eq!(*observed.lock().unwrap(), [65_536]);
    assert!(manager.snapshot("r4-candidate").unwrap().cancel_requested);
    drop(hooks);
    // 显式新token的封存/后续扫描不能被旧操作取消污染。
    assert!(rebuild_candidate_tree_sha_controlled(
        fixture.ctx.layout(),
        CANDIDATE,
        &CancelToken::new()
    )
    .is_ok());
    assert_eq!(fs::read(path).unwrap(), vec![0x5a; 3 * 65_536]);
}

#[test]
fn controlled_scan_keeps_query_observer_authoritative_cancel_error() {
    use crate::query_tasks::{
        CleanupProof, QueryAction, QueryClock, QueryError, QueryIdentity, QueryResolution,
        QueryScope, QueryTarget, QueryTaskManager,
    };
    let fixture = Fixture::new();
    let path = fixture.candidate(&vec![0x5a; 2 * 65_536]);
    let manager = QueryTaskManager::default();
    let target = QueryTarget {
        root: fixture.root.to_string_lossy().into(),
        release_id: release(fixture.ctx.layout()).unwrap().into(),
        engine_id: "kohya".into(),
        action: QueryAction::InspectReadonly,
        rebuild: false,
        scope: QueryScope::Full,
    };
    let identity = QueryIdentity {
        target: target.clone(),
        workspace_fence: "r4-query-fixture".into(),
        instance_id: None,
        generation: None,
        state_sha256: None,
        receipt_sha256: None,
        binding_sha256: None,
        lock_sha256: "1".repeat(64),
        recipe_sha256: "2".repeat(64),
    };
    let mut handle = manager
        .begin(target, QueryClock::start(Duration::from_secs(60)).unwrap())
        .unwrap()
        .handle;
    assert!(matches!(
        handle.resolve(identity).unwrap(),
        QueryResolution::Execute
    ));
    assert!(handle.try_start().unwrap());
    let task = handle.task_id().to_owned();
    let watched = path.clone();
    let cancelling = manager.clone();
    let _hooks = Hooks::read(move |at, _| {
        if at == watched {
            cancelling.cancel(&task).unwrap();
        }
    });
    let error = scan_observation::with(&handle.observer(), || {
        rebuild_candidate_tree_sha_controlled(
            fixture.ctx.layout(),
            CANDIDATE,
            &handle.cancel_token(),
        )
    })
    .unwrap_err();
    assert_eq!(
        error.downcast_ref::<QueryError>().unwrap().code,
        "query_cancelled"
    );
    assert!(error.downcast_ref::<Cancelled>().is_none());
    handle
        .finish(
            Err(error.downcast::<QueryError>().unwrap()),
            None,
            CleanupProof::no_worker_started(),
        )
        .unwrap();
}

#[test]
fn boundary_traversal_observes_real_operation_cancel_without_query_observer() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    fixture.candidate(b"candidate");
    let manager = Arc::new(OperationManager::default());
    let operation = manager.start("r4-walk", OperationKind::Repair).unwrap();
    let watched = fixture.root.join("e/g1111111111111111");
    let cancel_manager = manager.clone();
    let _hooks = Hooks::visit(move |path| {
        if path == watched {
            cancel_manager.cancel("r4-walk").unwrap();
        }
    });
    let error = fixture
        .check(&boundary, &operation.cancel_token())
        .unwrap_err();
    assert!(error.downcast_ref::<Cancelled>().is_some());
    assert!(scan_observation::observer().is_none());
}

#[test]
fn boundary_skips_candidate_bytes_but_independent_sha_still_covers_all_content() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    let path = fixture.candidate(&vec![0x31; 2 * 65_536]);
    let read_candidate = Arc::new(std::sync::Mutex::new(0u64));
    let record = read_candidate.clone();
    let watched = path.clone();
    let hooks = Hooks::read(move |at, _| {
        if at == watched {
            *record.lock().unwrap() += 1;
        }
    });
    fixture.check(&boundary, &CancelToken::new()).unwrap();
    assert_eq!(*read_candidate.lock().unwrap(), 0);
    let original =
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .unwrap();
    assert_eq!(*read_candidate.lock().unwrap(), 2);
    drop(hooks);
    let modified = fs::metadata(&path).unwrap().modified().unwrap();
    fs::write(&path, vec![0x32; 2 * 65_536]).unwrap();
    File::options()
        .write(true)
        .open(&path)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(modified))
        .unwrap();
    assert_ne!(
        original,
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .unwrap()
    );
    fixture.write(&format!("e/{CANDIDATE}/extra-dir/extra.bin"), b"extra");
    assert_ne!(
        original,
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .unwrap()
    );
}

#[test]
fn boundary_rejects_preexisting_candidate_before_exclusion() {
    let fixture = Fixture::new();
    fixture.candidate(b"already-owned");
    let boundary = fixture.boundary();
    let error = fixture.check(&boundary, &CancelToken::new()).unwrap_err();
    assert!(error.to_string().contains("候选原路径非空"));
    assert_eq!(
        fs::read(fixture.root.join(format!("e/{CANDIDATE}/candidate.bin"))).unwrap(),
        b"already-owned"
    );
}

#[test]
fn boundary_retains_non_target_and_old_snapshot_content_checks() {
    let fixture = Fixture::new();
    let old = fixture.write("backups/old-pending/snapshot.bin", b"snapshot");
    let mut boundary = fixture.boundary();
    boundary.snapshots.insert(
        PathBuf::from("backups/old-pending"),
        scan(fixture.ctx.layout(), old.parent().unwrap(), &[]).unwrap(),
    );
    fixture.candidate(b"candidate");
    fixture.check(&boundary, &CancelToken::new()).unwrap();
    fs::write(&old, b"changed!").unwrap();
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
    fs::write(&old, b"snapshot").unwrap();
    let keeper = fixture.root.join("e/g1111111111111111/keeper.bin");
    let modified = fs::metadata(&keeper).unwrap().modified().unwrap();
    fs::write(&keeper, b"modified").unwrap();
    File::options()
        .write(true)
        .open(&keeper)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(modified))
        .unwrap();
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
    fs::write(&keeper, b"original").unwrap();
    fixture.write("e/g1111111111111111/unknown-dir/new.bin", b"new");
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
}

#[test]
fn boundary_does_not_exempt_unknown_engine_ownership_or_candidate_root_file() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    fixture.candidate(b"candidate");
    fixture.write("e/t333333333333333/unknown.bin", b"unknown-engine");
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
    fs::remove_file(fixture.root.join("e/t333333333333333/unknown.bin")).unwrap();
    fs::remove_dir(fixture.root.join("e/t333333333333333")).unwrap();
    let candidate = fixture.root.join(format!("e/{CANDIDATE}"));
    fs::remove_file(candidate.join("candidate.bin")).unwrap();
    fs::remove_dir(&candidate).unwrap();
    fs::write(&candidate, b"file-instead-of-directory").unwrap();
    assert!(fixture.check(&boundary, &CancelToken::new()).is_err());
    assert!(rebuild_candidate_tree_sha_controlled(
        fixture.ctx.layout(),
        CANDIDATE,
        &CancelToken::new()
    )
    .is_err());
}

#[cfg(windows)]
#[test]
fn boundary_and_candidate_sha_reject_candidate_reparse_points() {
    let fixture = Fixture::new();
    let boundary = fixture.boundary();
    let candidate = fixture.root.join(format!("e/{CANDIDATE}"));
    let target = fixture.root.join("e/g1111111111111111");
    junction::create(&target, &candidate).unwrap();
    let boundary_rejected = fixture.check(&boundary, &CancelToken::new()).is_err();
    let hash_rejected =
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .is_err();
    junction::delete(&candidate).unwrap();
    assert!(boundary_rejected);
    assert!(hash_rejected);
    fixture.candidate(b"candidate");
    let link = candidate.join("linked-directory");
    junction::create(&target, &link).unwrap();
    let nested_rejected =
        rebuild_candidate_tree_sha_controlled(fixture.ctx.layout(), CANDIDATE, &CancelToken::new())
            .is_err();
    junction::delete(&link).unwrap();
    assert!(nested_rejected);
}

// 仅构造扫描合同使用的clean synthetic实例。无真实配方、依赖或运行验证，
// 不据此授予安装健康；create/validate_new仍使用正式state与保护树规则。
fn precommit_clean_scan_state(fixture: &Fixture) -> InstanceState {
    let layout = fixture.ctx.layout();
    model::Registry::default().store(&fixture.root).unwrap();
    fixture.write("python/3.10.19/base.dll", &vec![0x31; 3 * 65_536]);
    fixture.write("tools/uv.exe", b"synthetic scan fixture, never executed");
    fixture.write("environments/retained/fixture.bin", b"retained non-target");
    let source = layout
        .release_dir
        .strip_prefix(&fixture.root)
        .unwrap()
        .join("scan-fixture.bin");
    fixture.write(source.to_str().unwrap(), b"synthetic retained source");
    let state = create(
        &fixture.ctx,
        CANDIDATE,
        "precommit-scan-fixture",
        &"c".repeat(64),
    )
    .unwrap();
    fixture.write(
        &format!("e/{CANDIDATE}/package/payload.bin"),
        &vec![0x51; 3 * 65_536],
    );
    validate_new_controlled(&fixture.ctx, &state, &[], &CancelToken::new(), |_| Ok(())).unwrap()
}

fn precommit_assert_same_usability(state: &InstanceState, expected_usable: bool) {
    assert!(scan_observation::observer().is_none());
    let legacy = assert_usable(state);
    let controlled = assert_usable_controlled(state, &CancelToken::new());
    assert_eq!(legacy.is_ok(), expected_usable, "legacy: {legacy:?}");
    assert_eq!(
        controlled.is_ok(),
        expected_usable,
        "controlled: {controlled:?}"
    );
    if let (Err(legacy), Err(controlled)) = (legacy, controlled) {
        assert_eq!(format!("{legacy:#}"), format!("{controlled:#}"));
    }
}

#[test]
fn precommit_controlled_clean_scan_matches_legacy_usability() {
    let fixture = Fixture::new();
    let state = precommit_clean_scan_state(&fixture);
    precommit_assert_same_usability(&state, true);
}

#[test]
fn precommit_controlled_same_size_mtime_environment_tamper_matches_legacy_rejection() {
    let fixture = Fixture::new();
    let state = precommit_clean_scan_state(&fixture);
    let file = path(&state).unwrap().join("package/payload.bin");
    let before = fs::metadata(&file).unwrap();
    let modified = before.modified().unwrap();
    fs::write(&file, vec![0x52; before.len() as usize]).unwrap();
    File::options()
        .write(true)
        .open(&file)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(modified))
        .unwrap();
    assert_eq!(fs::metadata(&file).unwrap().len(), before.len());
    assert_eq!(fs::metadata(&file).unwrap().modified().unwrap(), modified);
    precommit_assert_same_usability(&state, false);
}

#[test]
fn precommit_controlled_same_size_mtime_python_tamper_matches_legacy_rejection() {
    let fixture = Fixture::new();
    let state = precommit_clean_scan_state(&fixture);
    let file = fixture.root.join("python/3.10.19/base.dll");
    let before = fs::metadata(&file).unwrap();
    let modified = before.modified().unwrap();
    fs::write(&file, vec![0x32; before.len() as usize]).unwrap();
    File::options()
        .write(true)
        .open(&file)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(modified))
        .unwrap();
    assert_eq!(fs::metadata(&file).unwrap().len(), before.len());
    assert_eq!(fs::metadata(&file).unwrap().modified().unwrap(), modified);
    precommit_assert_same_usability(&state, false);
}

#[test]
fn precommit_controlled_changed_disk_state_matches_legacy_rejection() {
    let fixture = Fixture::new();
    let state = precommit_clean_scan_state(&fixture);
    let mut changed = state.clone();
    changed.generation += 1;
    changed.validated_generation = changed.generation;
    save(fixture.ctx.layout(), &changed).unwrap();
    assert_ne!(load(fixture.ctx.layout(), state.id()).unwrap(), state);
    precommit_assert_same_usability(&state, false);
}

#[test]
fn precommit_controlled_base_python_gate_matches_legacy_rejection() {
    let fixture = Fixture::new();
    let state = precommit_clean_scan_state(&fixture);
    let mut registry = model::Registry::load(&fixture.root).unwrap();
    registry.schema_version = 3;
    registry.base_python_pending = Some("base-python-precommit-fixture".into());
    registry.store(&fixture.root).unwrap();
    precommit_assert_same_usability(&state, false);
}

#[test]
fn precommit_controlled_usability_directory_cancel_without_query_observer() {
    for branch in ["python", "environment"] {
        let fixture = Fixture::new();
        let state = precommit_clean_scan_state(&fixture);
        let manager = Arc::new(OperationManager::default());
        let operation = manager
            .start("precommit-directory", OperationKind::Repair)
            .unwrap();
        let watched = if branch == "python" {
            fixture.root.join("python/3.10.19")
        } else {
            path(&state).unwrap().join("package")
        };
        let requests = Arc::new(std::sync::Mutex::new(0));
        let count = requests.clone();
        let cancel_manager = manager.clone();
        let hooks = Hooks::visit(move |at| {
            if at == watched {
                *count.lock().unwrap() += 1;
                assert_eq!(
                    cancel_manager.cancel("precommit-directory").unwrap(),
                    crate::operations::CancelReceipt::Accepted
                );
            }
        });
        assert!(scan_observation::observer().is_none());
        let error = assert_usable_controlled(&state, &operation.cancel_token()).unwrap_err();
        assert!(
            error.downcast_ref::<Cancelled>().is_some(),
            "{branch}: {error}"
        );
        assert_eq!(*requests.lock().unwrap(), 1, "{branch}");
        assert!(
            manager
                .snapshot("precommit-directory")
                .unwrap()
                .cancel_requested
        );
        drop(hooks);
        precommit_assert_same_usability(&state, true);
    }
}

#[test]
fn precommit_controlled_usability_first_hash_block_cancel_without_query_observer() {
    for branch in ["python", "environment"] {
        let fixture = Fixture::new();
        let state = precommit_clean_scan_state(&fixture);
        let manager = Arc::new(OperationManager::default());
        let operation = manager
            .start("precommit-hash", OperationKind::Repair)
            .unwrap();
        let watched = if branch == "python" {
            fixture.root.join("python/3.10.19/base.dll")
        } else {
            path(&state).unwrap().join("package/payload.bin")
        };
        let reads = Arc::new(std::sync::Mutex::new(Vec::new()));
        let record = reads.clone();
        let cancel_manager = manager.clone();
        let hooks = Hooks::read(move |at, bytes| {
            if at == watched {
                record.lock().unwrap().push(bytes);
                assert_eq!(
                    cancel_manager.cancel("precommit-hash").unwrap(),
                    crate::operations::CancelReceipt::Accepted
                );
            }
        });
        assert!(scan_observation::observer().is_none());
        let error = assert_usable_controlled(&state, &operation.cancel_token()).unwrap_err();
        assert!(
            error.downcast_ref::<Cancelled>().is_some(),
            "{branch}: {error}"
        );
        assert_eq!(*reads.lock().unwrap(), [65_536], "{branch}");
        assert!(manager.snapshot("precommit-hash").unwrap().cancel_requested);
        drop(hooks);
        precommit_assert_same_usability(&state, true);
    }
}

#[test]
fn precommit_controlled_observe_inner_directory_cancel_reaches_each_protected_branch() {
    for branch in [
        "source",
        "python",
        "environments",
        "other-instance",
        "environment",
    ] {
        let fixture = Fixture::new();
        let state = precommit_clean_scan_state(&fixture);
        let manager = Arc::new(OperationManager::default());
        let operation = manager
            .start("precommit-observe", OperationKind::Repair)
            .unwrap();
        let watched = match branch {
            "source" => fixture.ctx.layout().release_dir.clone(),
            "python" => fixture.root.join("python/3.10.19"),
            "environments" => fixture.root.join("environments/retained"),
            "other-instance" => fixture.root.join("e/g1111111111111111"),
            _ => path(&state).unwrap().join("package"),
        };
        let visits = Arc::new(std::sync::Mutex::new(0));
        let record = visits.clone();
        let cancel_manager = manager.clone();
        let hooks = Hooks::visit(move |at| {
            if at == watched {
                *record.lock().unwrap() += 1;
                assert_eq!(
                    cancel_manager.cancel("precommit-observe").unwrap(),
                    crate::operations::CancelReceipt::Accepted
                );
            }
        });
        assert!(scan_observation::observer().is_none());
        let error = observe_inner(
            fixture.ctx.layout(),
            &state,
            &operation.cancel_token(),
            false,
        )
        .unwrap_err();
        assert!(
            error.downcast_ref::<Cancelled>().is_some(),
            "{branch}: {error}"
        );
        assert_eq!(*visits.lock().unwrap(), 1, "{branch}");
        assert!(
            manager
                .snapshot("precommit-observe")
                .unwrap()
                .cancel_requested
        );
        drop(hooks);
        assert_eq!(
            observe_inner(fixture.ctx.layout(), &state, &CancelToken::new(), false).unwrap(),
            state.verified
        );
    }
}
