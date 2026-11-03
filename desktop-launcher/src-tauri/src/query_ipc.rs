//! 受理只做有界内存工作；目录、清单及完整性读取全部交给后台执行者。
use crate::{core, log_store, query_tasks::*, Runtime, WorkerGuard};
use std::{
    path::PathBuf,
    sync::{atomic::Ordering, Arc},
    time::Duration,
};
use tauri::Manager;

#[tauri::command]
#[allow(clippy::too_many_arguments)] // Tauri按顶层字段绑定既有JSON请求；合并参数会改变IPC契约。
pub(crate) fn begin_engine_query(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    engine_id: String,
    action: String,
    rebuild: bool,
    scope: String,
    timeout_seconds: Option<u64>,
) -> Result<QueryAcceptance, String> {
    let clock = QueryClock::start(Duration::from_secs(timeout_seconds.unwrap_or(1800)))
        .map_err(|e| e.to_string())?;
    if state.shutting_down.load(Ordering::Acquire) {
        return Err("启动器正在退出".into());
    }
    let action = match action.as_str() {
        "capabilities" => QueryAction::Capabilities,
        "recipe" => QueryAction::Recipe,
        "inspect_readonly" => QueryAction::InspectReadonly,
        "plan_install" => QueryAction::PlanInstall,
        "plan_repair" => QueryAction::PlanRepair,
        _ => return Err("不支持的检查动作".into()),
    };
    let scope = match scope.as_str() {
        "full" => QueryScope::Full,
        "files_only" => QueryScope::FilesOnly,
        "plan" => QueryScope::Plan,
        _ => return Err("不支持的检查范围".into()),
    };
    let root = if root.trim().is_empty() {
        state.default_root.to_string_lossy().into_owned()
    } else {
        root.trim().to_owned()
    };
    let target = QueryTarget {
        root,
        release_id,
        engine_id,
        action,
        rebuild,
        scope,
    };
    admit(&state, target, clock)
}

#[tauri::command]
pub(crate) fn begin_gui_rebuild_preview(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    timeout_seconds: Option<u64>,
) -> Result<QueryAcceptance, String> {
    let clock = QueryClock::start(Duration::from_secs(timeout_seconds.unwrap_or(1800)))
        .map_err(|e| e.to_string())?;
    if state.shutting_down.load(Ordering::Acquire) {
        return Err("启动器正在退出".into());
    }
    let root = if root.trim().is_empty() {
        state.default_root.to_string_lossy().into_owned()
    } else {
        root.trim().to_owned()
    };
    admit(
        &state,
        QueryTarget {
            root,
            release_id,
            engine_id: "gui".into(),
            action: QueryAction::GuiRebuildPreview,
            rebuild: true,
            scope: QueryScope::Plan,
        },
        clock,
    )
}

#[tauri::command]
pub(crate) fn begin_legacy_environment_repair_preview(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    timeout_seconds: Option<u64>,
) -> Result<QueryAcceptance, String> {
    let clock = QueryClock::start(Duration::from_secs(timeout_seconds.unwrap_or(360)))
        .map_err(|e| e.to_string())?;
    if state.shutting_down.load(Ordering::Acquire) {
        return Err("启动器正在退出".into());
    }
    let root = if root.trim().is_empty() {
        state.default_root.to_string_lossy().into_owned()
    } else {
        root.trim().to_owned()
    };
    admit(
        &state,
        QueryTarget {
            root,
            release_id,
            engine_id: "gui".into(),
            action: QueryAction::LegacyEnvironmentRepairPreview,
            rebuild: false,
            scope: QueryScope::Plan,
        },
        clock,
    )
}

fn admit(
    state: &Runtime,
    target: QueryTarget,
    clock: QueryClock,
) -> Result<QueryAcceptance, String> {
    let admission = state
        .queries
        .begin(target.clone(), clock)
        .map_err(|e| e.to_string())?;
    let logs = state.logs.clone();
    state.workers.fetch_add(1, Ordering::AcqRel);
    let guard = WorkerGuard(state.workers.clone());
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = guard;
        let _context = log_store::bind(log_store::Context::workspace(
            &PathBuf::from(&target.root),
            "environment",
        ));
        let log: core::Logger = Arc::new(move |line| {
            logs.record_current(&line);
        });
        core::run_engine_query(admission.handle, target, log);
    });
    Ok(admission.acceptance)
}

#[tauri::command]
pub(crate) fn engine_query_snapshot(
    state: tauri::State<'_, Runtime>,
    task_id: String,
    subscription_id: Option<String>,
) -> Result<QuerySnapshot, String> {
    if let Some(subscription) = subscription_id {
        state
            .queries
            .touch_subscription(&task_id, &subscription)
            .map_err(|e| e.to_string())?;
    }
    state.queries.snapshot(&task_id).map_err(|e| e.to_string())
}
#[tauri::command]
pub(crate) fn engine_query_events(
    state: tauri::State<'_, Runtime>,
    task_id: String,
    after_seq: u64,
) -> Result<QueryEvents, String> {
    state
        .queries
        .events_since(&task_id, after_seq)
        .map_err(|e| e.to_string())
}
#[tauri::command]
pub(crate) fn engine_query_result(
    state: tauri::State<'_, Runtime>,
    task_id: String,
) -> Result<QueryResult, String> {
    state.queries.result(&task_id).map_err(|e| e.to_string())
}
#[tauri::command]
pub(crate) fn join_engine_query(
    state: tauri::State<'_, Runtime>,
    task_id: String,
) -> Result<QueryAcceptance, String> {
    state.queries.join(&task_id).map_err(|e| e.to_string())
}
#[tauri::command]
pub(crate) fn leave_engine_query(
    state: tauri::State<'_, Runtime>,
    task_id: String,
    subscription_id: String,
) -> Result<bool, String> {
    state
        .queries
        .leave(&task_id, &subscription_id)
        .map_err(|e| e.to_string())
}
#[tauri::command]
pub(crate) fn cancel_engine_query(
    state: tauri::State<'_, Runtime>,
    task_id: String,
) -> Result<QueryCancelReceipt, String> {
    state.queries.cancel(&task_id).map_err(|e| e.to_string())
}

pub(crate) fn start_watchdog(app: tauri::AppHandle) {
    std::thread::spawn(move || loop {
        {
            let state = app.state::<Runtime>();
            if state.query_watchdog_stop.load(Ordering::Acquire) {
                break;
            }
            if let Err(error) = state.queries.tick() {
                state
                    .logs
                    .record_current(&format!("[ERROR] 检查状态维护失败：{error}"));
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    });
}
