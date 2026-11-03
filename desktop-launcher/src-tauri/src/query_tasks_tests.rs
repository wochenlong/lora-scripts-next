//! 纯内存合同；不替代bridge/真实Job/管道/IPC/UI验收。
use super::*;
use serde_json::json;
use std::{sync::Barrier, thread};

fn target(n: u64) -> QueryTarget {
    QueryTarget {
        root: format!("F:/contract-root-{n}"),
        release_id: "dev-contract".into(),
        engine_id: "kohya".into(),
        action: QueryAction::InspectReadonly,
        rebuild: false,
        scope: QueryScope::Full,
    }
}
fn identity(n: u64) -> QueryIdentity {
    QueryIdentity {
        target: target(n),
        workspace_fence: format!("volume-directory-marker-{n}"),
        instance_id: Some(format!("instance-{n}")),
        generation: Some(1),
        state_sha256: Some("1".repeat(64)),
        receipt_sha256: Some("2".repeat(64)),
        binding_sha256: Some("3".repeat(64)),
        lock_sha256: "4".repeat(64),
        recipe_sha256: "5".repeat(64),
    }
}
fn clock() -> QueryClock {
    QueryClock::start(Duration::from_secs(60)).unwrap()
}

#[test]
fn gui_preview_target_cannot_be_confused_with_engine_actions() {
    assert_eq!(
        serde_json::to_value(QueryAction::GuiRebuildPreview).unwrap(),
        json!("preview_gui_rebuild")
    );
    let manager = QueryTaskManager::default();
    let mut t = target(0);
    t.engine_id = "gui".into();
    assert!(manager.begin(t.clone(), clock()).is_err());
    t.action = QueryAction::GuiRebuildPreview;
    t.scope = QueryScope::Plan;
    assert!(manager.begin(t.clone(), clock()).is_err());
    t.rebuild = true;
    assert!(manager.begin(t.clone(), clock()).is_ok());
    t.engine_id = "kohya".into();
    assert!(manager.begin(t, clock()).is_err());
}
fn admission(manager: &QueryTaskManager, n: u64) -> QueryAdmission {
    manager.begin(target(n), clock()).unwrap()
}
fn execute(manager: &QueryTaskManager, n: u64) -> QueryHandle {
    let mut h = admission(manager, n).handle;
    assert!(matches!(
        h.resolve(identity(n)).unwrap(),
        QueryResolution::Execute
    ));
    h
}
fn success(h: &QueryHandle, n: u64) -> QuerySnapshot {
    h.finish(
        Ok(json!({"healthy":true})),
        Some(identity(n)),
        CleanupProof::no_worker_started(),
    )
    .unwrap()
}
fn fail(h: &QueryHandle, error: QueryError) -> QuerySnapshot {
    h.finish(Err(error), None, CleanupProof::no_worker_started())
        .unwrap()
}
fn worker(n: u32) -> WorkerIdentity {
    WorkerIdentity {
        pid: n,
        creation_time: u64::from(n) + 10,
        job_id: format!("owned-job-{n}"),
    }
}
fn readers() -> ReaderCleanup {
    ReaderCleanup {
        stdin_closed: true,
        stdout_reader_joined: true,
        stderr_reader_joined: true,
    }
}
fn reaped(n: u32) -> CleanupProof {
    CleanupProof::reaped(worker(n), true, 0, readers()).unwrap()
}
fn limits() -> QueryLimits {
    QueryLimits::default()
}

#[test]
fn immediate_memory_admission_has_stable_id_and_unresolved_state() {
    let m = QueryTaskManager::default();
    let a = admission(&m, 1);
    assert_eq!(a.acceptance.task_id, a.handle.task_id());
    assert_eq!(a.acceptance.canonical_task_id, a.acceptance.task_id);
    assert_eq!(a.acceptance.snapshot.status, QueryStatus::Resolving);
    assert!(a.acceptance.snapshot.identity.is_none());
    assert!(!a.acceptance.snapshot.result_available);
    assert!(!a.acceptance.shared);
    assert_eq!(m.active_count().unwrap(), 1);
}

#[test]
fn resolving_error_keeps_unique_handle_for_failed_terminal() {
    let m = QueryTaskManager::default();
    let mut h = admission(&m, 1).handle;
    let mut bad = identity(1);
    bad.lock_sha256 = "invalid".into();
    let error = h.resolve(bad).unwrap_err();
    assert_eq!(error.code, "query_identity_invalid");
    assert_eq!(fail(&h, error).status, QueryStatus::Failed);
    assert_eq!(m.active_count().unwrap(), 0);
}

#[test]
fn same_final_identity_has_one_executor_and_original_alias_remains() {
    let m = QueryTaskManager::default();
    let leader = execute(&m, 1);
    let a = admission(&m, 1);
    let id = a.acceptance.task_id.clone();
    let mut follower = a.handle;
    let snapshot = match follower.resolve(identity(1)).unwrap() {
        QueryResolution::Joined(s) => s,
        _ => panic!("must join"),
    };
    assert_eq!(snapshot.task_id, id);
    assert_eq!(snapshot.canonical_task_id, leader.task_id());
    assert_eq!(m.active_count().unwrap(), 1);
    assert!(follower.attach_worker(worker(12)).is_err());
    assert!(follower
        .finish(
            Ok(json!({})),
            Some(identity(1)),
            CleanupProof::no_worker_started()
        )
        .is_err());
    assert!(leader.try_start().unwrap());
    leader.attach_worker(worker(11)).unwrap();
    assert_eq!(m.snapshot(&id).unwrap().worker, Some(worker(11)));
    leader
        .finish(Ok(json!({})), Some(identity(1)), reaped(11))
        .unwrap();
    assert_eq!(m.snapshot(&id).unwrap().status, QueryStatus::Succeeded);
}

#[test]
fn full_distinct_identity_capacity_still_allows_duplicate_resolution() {
    let m = QueryTaskManager::default();
    let leaders: Vec<_> = (1..=4).map(|n| execute(&m, n)).collect();
    let mut duplicate = admission(&m, 1).handle;
    assert!(matches!(
        duplicate.resolve(identity(1)).unwrap(),
        QueryResolution::Joined(_)
    ));
    let mut unique = admission(&m, 5).handle;
    let error = unique.resolve(identity(5)).unwrap_err();
    assert_eq!(error.code, "query_capacity");
    assert_eq!(fail(&unique, error).status, QueryStatus::Failed);
    assert_eq!(m.active_count().unwrap(), 4);
    for (n, h) in (1..=4).zip(leaders.iter()) {
        success(h, n);
    }
}

#[test]
fn independent_resolver_pool_is_bounded_and_errors_do_not_drop_work() {
    let mut l = limits();
    l.max_resolving = 2;
    let m = QueryTaskManager::new(l).unwrap();
    let a = admission(&m, 1);
    let b = admission(&m, 2);
    assert_eq!(
        m.begin(target(3), clock()).unwrap_err().code,
        "query_resolver_capacity"
    );
    fail(
        &a.handle,
        QueryError::new("resolution_failed", "invalid control"),
    );
    assert!(m.begin(target(3), clock()).is_ok());
    fail(
        &b.handle,
        QueryError::new("resolution_failed", "invalid control"),
    );
}

#[test]
fn only_one_scan_slot_is_held_until_proven_finish() {
    let m = QueryTaskManager::default();
    let first = execute(&m, 1);
    let second = execute(&m, 2);
    assert!(first.try_start().unwrap());
    assert!(!second.try_start().unwrap());
    assert_eq!(
        m.snapshot(second.task_id()).unwrap().status,
        QueryStatus::Queued
    );
    m.cancel(first.task_id()).unwrap();
    assert!(!second.try_start().unwrap());
    fail(&first, QueryError::new("cancelled", "done"));
    assert!(second.try_start().unwrap());
    success(&second, 2);
}

#[test]
fn leaving_all_subscriptions_is_not_cancellation_and_join_preserves_deadline() {
    let m = QueryTaskManager::default();
    let a = admission(&m, 1);
    let original_deadline = a.acceptance.snapshot.deadline_at_ms;
    let b = m.join(&a.acceptance.task_id).unwrap();
    assert!(m
        .leave(&a.acceptance.task_id, &a.acceptance.subscription_id)
        .unwrap());
    assert!(m.leave(&b.task_id, &b.subscription_id).unwrap());
    assert!(!m.leave(&b.task_id, &b.subscription_id).unwrap());
    let s = m.snapshot(&b.task_id).unwrap();
    assert_eq!(s.subscriber_count, 0);
    assert!(!s.cancel_requested);
    let joined = m.join(&b.task_id).unwrap();
    assert_eq!(joined.snapshot.deadline_at_ms, original_deadline);
}

#[test]
fn explicit_alias_cancel_is_shared_and_success_cannot_override_it() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    let mut other = admission(&m, 1).handle;
    assert!(matches!(
        other.resolve(identity(1)).unwrap(),
        QueryResolution::Joined(_)
    ));
    assert_eq!(
        m.cancel(other.task_id()).unwrap(),
        QueryCancelReceipt::Accepted
    );
    assert_eq!(
        m.cancel(h.task_id()).unwrap(),
        QueryCancelReceipt::AlreadyRequested
    );
    assert!(h.cancel_token().is_cancel_requested());
    assert_eq!(success(&h, 1).status, QueryStatus::Cancelled);
    assert_eq!(
        m.snapshot(other.task_id()).unwrap().status,
        QueryStatus::Cancelled
    );
    assert!(m.result(other.task_id()).unwrap().result.is_none());
}

#[test]
fn success_before_cancel_returns_already_terminal() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    success(&h, 1);
    assert_eq!(
        m.cancel(h.task_id()).unwrap(),
        QueryCancelReceipt::AlreadyTerminal
    );
    assert!(!m.snapshot(h.task_id()).unwrap().cancel_requested);
}

#[test]
fn cancel_success_race_has_only_one_linearized_terminal() {
    for _ in 0..64 {
        let m = QueryTaskManager::default();
        let h = execute(&m, 1);
        let id = h.task_id().to_owned();
        let barrier = Arc::new(Barrier::new(2));
        let child_barrier = barrier.clone();
        let join = thread::spawn(move || {
            child_barrier.wait();
            success(&h, 1).status
        });
        barrier.wait();
        let receipt = m.cancel(&id).unwrap();
        let status = join.join().unwrap();
        assert!(matches!(
            (status, receipt),
            (QueryStatus::Succeeded, QueryCancelReceipt::AlreadyTerminal)
                | (QueryStatus::Cancelled, QueryCancelReceipt::Accepted)
        ));
        assert_eq!(m.snapshot(&id).unwrap().status, status);
    }
}

#[test]
fn accepted_cancel_before_resolve_does_not_cancel_other_shared_work() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    let mut other = admission(&m, 1).handle;
    m.cancel(other.task_id()).unwrap();
    assert!(matches!(
        other.resolve(identity(1)).unwrap(),
        QueryResolution::Stopped
    ));
    assert_eq!(
        fail(&other, QueryError::new("cancelled", "stopped")).status,
        QueryStatus::Cancelled
    );
    assert!(!h.cancel_token().is_cancel_requested());
    success(&h, 1);
}

#[test]
fn entry_deadline_includes_resolution_and_does_not_terminal_before_cleanup() {
    let m = QueryTaskManager::default();
    let mut c = clock();
    c.started = Instant::now() - Duration::from_secs(5);
    c.deadline = Instant::now() - Duration::from_secs(1);
    c.started_at_ms = 100;
    c.deadline_at_ms = 200;
    let mut h = m.begin(target(1), c).unwrap().handle;
    assert_eq!(h.check().unwrap_err().code, "query_timed_out");
    assert!(matches!(
        h.resolve(identity(1)).unwrap(),
        QueryResolution::Stopped
    ));
    let s = m.snapshot(h.task_id()).unwrap();
    assert_eq!(s.status, QueryStatus::Cancelling);
    assert_eq!(s.deadline_at_ms, 200);
    let terminal = fail(&h, QueryError::new("other", "must not override timeout"));
    assert_eq!(terminal.status, QueryStatus::TimedOut);
    assert_eq!(terminal.deadline_at_ms, 200);
}

#[test]
fn shared_deadline_takes_earliest_entry_and_rejoin_does_not_refresh() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    let mut c = clock();
    c.deadline = Instant::now() + Duration::from_secs(1);
    c.deadline_at_ms = 1234;
    let mut other = m.begin(target(1), c).unwrap().handle;
    other.resolve(identity(1)).unwrap();
    assert_eq!(h.deadline().unwrap(), c.deadline);
    m.join(other.task_id()).unwrap();
    m.touch_subscription(h.task_id(), &m.join(h.task_id()).unwrap().subscription_id)
        .unwrap();
    assert_eq!(h.deadline().unwrap(), c.deadline);
    m.tick_at(c.deadline + Duration::from_millis(1)).unwrap();
    assert_eq!(
        m.snapshot(h.task_id()).unwrap().stop_reason,
        Some(StopReason::Deadline)
    );
    assert_eq!(success(&h, 1).status, QueryStatus::TimedOut);
}

#[test]
fn user_cancel_reason_is_not_overwritten_by_later_timeout_or_shutdown() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    m.cancel(h.task_id()).unwrap();
    m.tick_at(h.deadline().unwrap() + Duration::from_secs(1))
        .unwrap();
    m.request_shutdown().unwrap();
    assert_eq!(success(&h, 1).status, QueryStatus::Cancelled);
}

#[test]
fn different_generation_root_state_receipt_or_binding_never_share() {
    for field in 0..6 {
        let m = QueryTaskManager::default();
        let _leader = execute(&m, 1);
        let mut changed = identity(1);
        match field {
            0 => changed.generation = Some(2),
            1 => changed.target.root = "F:/other-root".into(),
            2 => changed.state_sha256 = Some("a".repeat(64)),
            3 => changed.receipt_sha256 = Some("b".repeat(64)),
            4 => changed.binding_sha256 = Some("c".repeat(64)),
            _ => changed.workspace_fence = "replacement-directory".into(),
        }
        let mut h = admission(&m, 1).handle;
        assert!(matches!(
            h.resolve(changed).unwrap(),
            QueryResolution::Execute
        ));
        assert_eq!(m.active_count().unwrap(), 2);
    }
}

#[test]
fn final_identity_change_is_stale_and_result_is_unusable() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    let mut observed = identity(1);
    observed.generation = Some(2);
    let s = h
        .finish(
            Ok(json!({"healthy":true})),
            Some(observed),
            CleanupProof::no_worker_started(),
        )
        .unwrap();
    assert_eq!(s.status, QueryStatus::Stale);
    assert_eq!(s.validity, QueryValidity::Stale);
    assert!(!s.result_available);
    assert!(m.result(h.task_id()).unwrap().result.is_none());
}

#[test]
fn shutdown_rejects_admission_and_join_until_owners_reap() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    assert!(h.try_start().unwrap());
    h.attach_worker(worker(10)).unwrap();
    assert_eq!(m.request_shutdown().unwrap(), vec![h.task_id().to_owned()]);
    assert_eq!(
        m.begin(target(2), clock()).unwrap_err().code,
        "query_shutting_down"
    );
    assert_eq!(m.join(h.task_id()).unwrap_err().code, "query_shutting_down");
    assert_eq!(m.active_count().unwrap(), 1);
    h.cleanup_pending(QueryError::new("waiting_readers", "waiting"))
        .unwrap();
    assert!(!m.snapshot(h.task_id()).unwrap().status.is_terminal());
    assert_eq!(
        h.finish(Ok(json!({})), Some(identity(1)), reaped(10))
            .unwrap()
            .status,
        QueryStatus::Interrupted
    );
    assert_eq!(m.active_count().unwrap(), 0);
}

#[test]
fn cleanup_requires_child_job_stdin_and_both_joined_readers() {
    assert!(CleanupProof::reaped(worker(1), false, 0, readers()).is_err());
    assert!(CleanupProof::reaped(worker(1), true, 1, readers()).is_err());
    for missing in 0..3 {
        let mut r = readers();
        match missing {
            0 => r.stdin_closed = false,
            1 => r.stdout_reader_joined = false,
            _ => r.stderr_reader_joined = false,
        }
        assert_eq!(
            CleanupProof::reaped(worker(1), true, 0, r)
                .unwrap_err()
                .code,
            "query_readers_pending"
        );
    }
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    assert!(h.try_start().unwrap());
    h.attach_worker(worker(1)).unwrap();
    assert_eq!(
        h.finish(
            Ok(json!({})),
            Some(identity(1)),
            CleanupProof::no_worker_started()
        )
        .unwrap_err()
        .code,
        "query_cleanup_mismatch"
    );
    assert!(h
        .finish(Ok(json!({})), Some(identity(1)), reaped(2))
        .is_err());
    assert_eq!(m.active_count().unwrap(), 1);
    let s = h
        .finish(Ok(json!({})), Some(identity(1)), reaped(1))
        .unwrap();
    assert!(s.worker_reaped && s.readers_reaped);
}

#[test]
fn cancelled_spawn_race_can_register_real_owned_worker_then_reap() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    h.try_start().unwrap();
    m.cancel(h.task_id()).unwrap();
    h.attach_worker(worker(3)).unwrap();
    assert_eq!(
        h.finish(Ok(json!({})), Some(identity(1)), reaped(3))
            .unwrap()
            .status,
        QueryStatus::Cancelled
    );
}

#[test]
fn active_alias_is_never_evicted_when_alias_capacity_is_full() {
    let mut l = limits();
    l.max_aliases = 1;
    let m = QueryTaskManager::new(l).unwrap();
    let h = execute(&m, 1);
    let mut first = admission(&m, 1).handle;
    first.resolve(identity(1)).unwrap();
    let mut second = admission(&m, 1).handle;
    let error = second.resolve(identity(1)).unwrap_err();
    assert_eq!(error.code, "query_alias_capacity");
    fail(&second, error);
    m.tick_at(Instant::now() + Duration::from_secs(1)).unwrap();
    assert_eq!(
        m.snapshot(first.task_id()).unwrap().canonical_task_id,
        h.task_id()
    );
    assert!(!m.snapshot(h.task_id()).unwrap().status.is_terminal());
    success(&h, 1);
    let next = execute(&m, 2);
    let mut alias = admission(&m, 2).handle;
    alias.resolve(identity(2)).unwrap();
    assert!(m.snapshot(first.task_id()).is_err());
    success(&next, 2);
}

#[test]
fn events_history_and_results_are_bounded_without_dropping_active_task() {
    let mut l = limits();
    l.max_events = 3;
    l.max_terminal = 2;
    l.max_result_bytes = 32;
    l.max_total_result_bytes = 40;
    let m = QueryTaskManager::new(l).unwrap();
    let active = execute(&m, 99);
    for n in 1..=4 {
        let h = execute(&m, n);
        h.finish(
            Ok(json!({"payload":"1234567890"})),
            Some(identity(n)),
            CleanupProof::no_worker_started(),
        )
        .unwrap();
    }
    assert!(m.snapshot(active.task_id()).is_ok());
    let state = m.state().unwrap();
    assert!(
        state
            .tasks
            .values()
            .filter(|t| t.status.is_terminal())
            .count()
            <= 2
    );
    assert!(state.tasks.values().map(|t| t.result_bytes).sum::<usize>() <= 40);
    drop(state);
    for n in 1..10 {
        m.tick_at(Instant::now() + Duration::from_secs(n)).unwrap();
    }
    let events = m.events_since(active.task_id(), 0).unwrap();
    assert!(events.cursor_reset);
    assert!(events.events.is_empty());
    let seq = events.snapshot.event_seq;
    assert!(
        m.events_since(active.task_id(), seq + 1)
            .unwrap()
            .cursor_reset
    );
    assert!(
        m.events_since(active.task_id(), seq - 1)
            .unwrap()
            .events
            .len()
            <= 3
    );
}

#[test]
fn oversized_result_becomes_failed_not_oversized_retained_history() {
    let mut l = limits();
    l.max_result_bytes = 32;
    l.max_total_result_bytes = 64;
    let m = QueryTaskManager::new(l).unwrap();
    let h = execute(&m, 1);
    let s = h
        .finish(
            Ok(json!({"large":"x".repeat(33)})),
            Some(identity(1)),
            CleanupProof::no_worker_started(),
        )
        .unwrap();
    assert_eq!(s.status, QueryStatus::Failed);
    assert_eq!(s.error.unwrap().code, "query_result_too_large");
    assert!(m.result(h.task_id()).unwrap().result.is_none());
}

#[test]
fn subscriber_bounds_and_expiry_only_remove_subscriptions() {
    let mut l = limits();
    l.max_subscribers_per_task = 2;
    l.max_subscribers = 3;
    l.subscription_ttl = Duration::from_secs(1);
    let m = QueryTaskManager::new(l).unwrap();
    let a = admission(&m, 1);
    let b = m.join(&a.acceptance.task_id).unwrap();
    assert_eq!(
        m.join(&b.task_id).unwrap_err().code,
        "query_subscriber_capacity"
    );
    let c = admission(&m, 2);
    assert_eq!(
        m.begin(target(3), clock()).unwrap_err().code,
        "query_subscriber_capacity"
    );
    m.tick_at(Instant::now() + Duration::from_secs(2)).unwrap();
    assert_eq!(
        m.snapshot(&a.acceptance.task_id).unwrap().subscriber_count,
        0
    );
    assert!(!a.handle.cancel_token().is_cancel_requested());
    assert_eq!(m.active_count().unwrap(), 2);
    assert!(!m
        .leave(&c.acceptance.task_id, &c.acceptance.subscription_id)
        .unwrap());
}

#[test]
fn progress_is_utf8_bounded_redacted_and_heartbeat_does_not_increment_counts() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    h.try_start().unwrap();
    h.progress(
        QueryStage::Environment,
        QueryProgress {
            files: Some(4),
            bytes: Some(12),
            message: format!(
                "https://user:secret@host.test/a?token=private {}",
                "文".repeat(3000)
            ),
            ..Default::default()
        },
    )
    .unwrap();
    let before = m.snapshot(h.task_id()).unwrap();
    assert!(before.progress.message.len() <= MESSAGE_LIMIT);
    assert!(!before.progress.message.contains("secret"));
    assert!(!before.progress.message.contains("private"));
    assert_eq!(before.progress.total_files, None);
    m.tick_at(Instant::now() + Duration::from_secs(1)).unwrap();
    let after = m.snapshot(h.task_id()).unwrap();
    assert_eq!(before.progress, after.progress);
    assert!(after.event_seq > before.event_seq);
}

#[test]
fn terminal_history_is_not_reused_as_fresh_health_check() {
    let m = QueryTaskManager::default();
    let old = execute(&m, 1);
    success(&old, 1);
    let mut fresh = admission(&m, 1).handle;
    assert_ne!(fresh.task_id(), old.task_id());
    assert!(matches!(
        fresh.resolve(identity(1)).unwrap(),
        QueryResolution::Execute
    ));
    assert!(!m.snapshot(fresh.task_id()).unwrap().result_available);
}

#[test]
fn wrong_id_and_subscription_do_not_touch_other_tasks() {
    let m = QueryTaskManager::default();
    let a = admission(&m, 1);
    let b = admission(&m, 2);
    assert!(m.cancel("missing").is_err());
    assert!(m
        .leave(&a.acceptance.task_id, &b.acceptance.subscription_id)
        .is_err());
    assert!(!a.handle.cancel_token().is_cancel_requested());
    assert!(!b.handle.cancel_token().is_cancel_requested());
}

#[test]
fn progress_cannot_publish_complete_before_cleanup() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    assert_eq!(
        h.progress(QueryStage::Complete, QueryProgress::default())
            .unwrap_err()
            .code,
        "query_stage_invalid"
    );
    assert!(!m.snapshot(h.task_id()).unwrap().status.is_terminal());
}

#[test]
fn instance_recipe_lock_action_scope_and_rebuild_are_identity_keys() {
    for field in 0..6 {
        let m = QueryTaskManager::default();
        let _leader = execute(&m, 1);
        let mut changed = identity(1);
        match field {
            0 => changed.instance_id = Some("other-instance".into()),
            1 => changed.recipe_sha256 = "a".repeat(64),
            2 => changed.lock_sha256 = "b".repeat(64),
            3 => changed.target.action = QueryAction::PlanRepair,
            4 => changed.target.scope = QueryScope::FilesOnly,
            _ => changed.target.rebuild = true,
        }
        let mut h = m.begin(changed.target.clone(), clock()).unwrap().handle;
        assert!(matches!(
            h.resolve(changed).unwrap(),
            QueryResolution::Execute
        ));
        assert_eq!(m.active_count().unwrap(), 2);
    }
}

#[test]
fn queued_deadline_does_not_wait_for_scan_slot_or_refresh_on_try_start() {
    let m = QueryTaskManager::default();
    let first = execute(&m, 1);
    first.try_start().unwrap();
    let mut c = clock();
    c.deadline = Instant::now() + Duration::from_secs(1);
    c.deadline_at_ms = 3456;
    let mut second = m.begin(target(2), c).unwrap().handle;
    second.resolve(identity(2)).unwrap();
    assert!(!second.try_start().unwrap());
    m.tick_at(c.deadline + Duration::from_millis(1)).unwrap();
    assert_eq!(second.try_start().unwrap_err().code, "query_timed_out");
    assert_eq!(m.snapshot(second.task_id()).unwrap().deadline_at_ms, 3456);
    assert_eq!(success(&second, 2).status, QueryStatus::TimedOut);
    assert!(!first.cancel_token().is_cancel_requested());
    success(&first, 1);
}

#[test]
fn default_four_mib_limit_is_enforced_on_real_encoded_payload() {
    let m = QueryTaskManager::default();
    let h = execute(&m, 1);
    let s = h
        .finish(
            Ok(Value::String("x".repeat(4 * 1024 * 1024))),
            Some(identity(1)),
            CleanupProof::no_worker_started(),
        )
        .unwrap();
    assert_eq!(s.status, QueryStatus::Failed);
    assert_eq!(s.error.unwrap().code, "query_result_too_large");
    assert_eq!(
        m.state()
            .unwrap()
            .tasks
            .values()
            .map(|task| task.result_bytes)
            .sum::<usize>(),
        0
    );
}

#[test]
fn error_metadata_cannot_bypass_message_and_code_bounds() {
    let error = QueryError::new(&"x".repeat(10000), "字".repeat(10000));
    assert_eq!(error.code, "query_error");
    assert!(error.message.len() <= MESSAGE_LIMIT);
}

#[test]
fn backend_canonical_root_can_merge_spelling_alias_without_losing_request_id() {
    let m = QueryTaskManager::default();
    let leader = execute(&m, 1);
    let mut raw = target(1);
    raw.root = "f:\\CONTRACT-ROOT-1\\".into();
    let mut alias = m.begin(raw.clone(), clock()).unwrap().handle;
    alias.resolve(identity(1)).unwrap();
    let snapshot = m.snapshot(alias.task_id()).unwrap();
    assert_eq!(snapshot.target, raw);
    assert_eq!(snapshot.identity.unwrap().target.root, target(1).root);
    assert_eq!(snapshot.canonical_task_id, leader.task_id());
    assert_eq!(m.active_count().unwrap(), 1);
}
