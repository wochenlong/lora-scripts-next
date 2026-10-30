#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod core;
mod data_import;
mod download_body;
mod shell_update;
mod signed_catalog;
// 协议源码同时编译进独立helper；替换/回滚函数仅由helper调用。
mod gui_registration_integrity;
mod instances;
mod model;
mod network_policy;
mod operations;
mod python_integrity;
mod recipe;
#[cfg(test)]
mod recovery;
mod runtime_view;
#[allow(dead_code)]
mod shell_update_protocol;
mod source_integrity;
mod trial_ui;
mod wheel_integrity;
use core::{Engine, Lifecycle, Logger, Report, RuntimeSnapshot};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

struct Runtime {
    engine: Arc<Mutex<Engine>>,
    lifecycle: Arc<Lifecycle>,
    operations: Arc<operations::OperationManager>,
    default_root: PathBuf,
    workers: Arc<std::sync::atomic::AtomicUsize>,
    shutting_down: std::sync::atomic::AtomicBool,
    exit_ready: Arc<std::sync::atomic::AtomicBool>,
}

struct WorkerGuard(Arc<std::sync::atomic::AtomicUsize>);
impl Drop for WorkerGuard {
    fn drop(&mut self) {
        self.0.fetch_sub(1, std::sync::atomic::Ordering::AcqRel);
    }
}

// 操作控制与 Engine 分开持有，网络/子进程长操作不会阻塞取消和状态读取。
// 每次只执行一个后台操作；保留参数值以便审查，不为低频IPC增加间接分配。
#[allow(clippy::large_enum_variant)]
enum ManagedAction {
    Prefetch,
    Install,
    Repair {
        package: String,
        plan_sha256: String,
    },
    Recover,
    RepairSource,
    RepairBasePython {
        plan_sha256: String,
    },
    RecoverBasePython,
    RestoreRegistration {
        instance_id: String,
        plan_sha256: String,
    },
    RecoverRegistration,
    EngineControl {
        engine: String,
        action: String,
        plan: Option<serde_json::Value>,
    },
    DataControl {
        action: String,
        request: Option<data_import::ImportRequest>,
        binding: Option<data_import::BindingRequest>,
        plan: Option<String>,
        transaction: Option<String>,
    },
    GuiLifecycle {
        action: String,
        plan: Option<String>,
        transaction: Option<String>,
        instance: Option<String>,
    },
}

async fn begin_release_operation(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    action: ManagedAction,
) -> Result<operations::OperationSnapshot, String> {
    state
        .workers
        .fetch_add(1, std::sync::atomic::Ordering::AcqRel);
    let worker_guard = WorkerGuard(state.workers.clone());
    if state
        .shutting_down
        .load(std::sync::atomic::Ordering::Acquire)
    {
        return Err("启动器正在退出，请重新打开后操作".into());
    }
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
    let catalog = model::Catalog::for_workspace(&root).map_err(|e| format!("{e:#}"))?;
    let release = catalog.release(&release_id).map_err(|e| format!("{e:#}"))?;
    if !matches!(
        action,
        ManagedAction::Prefetch
            | ManagedAction::RepairBasePython { .. }
            | ManagedAction::RecoverBasePython
    ) && release.environment_recipe != "gui-cp310-win-x64-v1"
    {
        return Err("该历史版本尚未提供固定安装配方，请选择已适配版本".into());
    }
    let purpose = if matches!(action, ManagedAction::Install | ManagedAction::Prefetch) {
        "install"
    } else {
        "repair"
    };
    signed_catalog::authorize(&root, &release_id, purpose).map_err(|e| format!("{e:#}"))?;
    model::Layout::new(&root, &release_id).map_err(|e| format!("{e:#}"))?;
    static NEXT_OPERATION: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let serial = NEXT_OPERATION.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let id = format!("download-{}-{}-{serial}", model::now(), std::process::id());
    let handle = state
        .operations
        .start(
            &id,
            match &action {
                ManagedAction::Prefetch => operations::OperationKind::Download,
                ManagedAction::Install => operations::OperationKind::Execute,
                ManagedAction::Repair { .. }
                | ManagedAction::Recover
                | ManagedAction::RepairSource
                | ManagedAction::RepairBasePython { .. }
                | ManagedAction::RecoverBasePython => operations::OperationKind::Repair,
                ManagedAction::EngineControl { .. } => operations::OperationKind::Repair,
                ManagedAction::DataControl { .. } => operations::OperationKind::Repair,
                ManagedAction::RestoreRegistration { .. }
                | ManagedAction::RecoverRegistration
                | ManagedAction::GuiLifecycle { .. } => operations::OperationKind::Repair,
            },
        )
        .map_err(|e| format!("{e:#}"))?;
    if state
        .shutting_down
        .load(std::sync::atomic::Ordering::Acquire)
    {
        let _ = handle.finish(operations::OperationStatus::Cancelled, None);
        return Err("启动器正在退出，请重新打开后操作".into());
    }
    let initial = state
        .operations
        .snapshot(&id)
        .map_err(|e| format!("{e:#}"))?;
    let engine = state.engine.clone();
    let manager = state.operations.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _worker_guard = worker_guard;
        let result = (|| -> anyhow::Result<()> {
            handle.cancel_token().check()?;
            let mut engine = engine
                .try_lock()
                .map_err(|_| anyhow::anyhow!("已有安装或运行检查正在执行，请稍后重试"))?;
            match action {
                ManagedAction::Install => {
                    engine.install_release_operation(&root, &release_id, &handle)
                }
                ManagedAction::Prefetch => engine.prefetch_release(&root, &release_id, &handle),
                ManagedAction::Repair {
                    package,
                    plan_sha256,
                } => {
                    engine.repair_gui_operation(&root, &release_id, &package, &plan_sha256, &handle)
                }
                ManagedAction::Recover => engine.recover_gui_operation(&root, &release_id, &handle),
                ManagedAction::RepairSource => {
                    engine.repair_source_operation(&root, &release_id, &handle)
                }
                ManagedAction::RepairBasePython { plan_sha256 } => engine
                    .repair_base_python_operation(&root, &release_id, Some(&plan_sha256), &handle),
                ManagedAction::RecoverBasePython => {
                    engine.repair_base_python_operation(&root, &release_id, None, &handle)
                }
                ManagedAction::RestoreRegistration {
                    instance_id,
                    plan_sha256,
                } => engine.restore_gui_registration_operation(
                    &root,
                    &release_id,
                    Some((&instance_id, &plan_sha256)),
                    &handle,
                ),
                ManagedAction::RecoverRegistration => {
                    engine.restore_gui_registration_operation(&root, &release_id, None, &handle)
                }
                ManagedAction::EngineControl {
                    engine: target,
                    action,
                    plan,
                } => engine.engine_operation(
                    &root,
                    &release_id,
                    &target,
                    &action,
                    plan.as_ref(),
                    &handle,
                ),
                ManagedAction::DataControl {
                    action,
                    request,
                    binding,
                    plan,
                    transaction,
                } => engine.data_operation(
                    &root,
                    &release_id,
                    &action,
                    request.as_ref(),
                    binding.as_ref(),
                    plan.as_deref(),
                    transaction.as_deref(),
                    &handle,
                ),
                ManagedAction::GuiLifecycle {
                    action,
                    plan,
                    transaction,
                    instance,
                } => engine.gui_lifecycle_operation(
                    &root,
                    &release_id,
                    &action,
                    plan.as_deref(),
                    transaction.as_deref(),
                    instance.as_deref(),
                    &handle,
                ),
            }
        })();
        // 未能取得 lease 等早期错误只保存在本进程；不能越过 lease 写工作区。
        if manager
            .snapshot(&id)
            .is_ok_and(|s| s.status == operations::OperationStatus::Running)
        {
            let (status, error) = match result {
                Ok(()) => (operations::OperationStatus::Succeeded, None),
                Err(e) if e.downcast_ref::<operations::Cancelled>().is_some() => {
                    (operations::OperationStatus::Cancelled, None)
                }
                Err(e) => (
                    operations::OperationStatus::Failed,
                    Some(operations::OperationError {
                        code: "operation_start_failed".into(),
                        message: format!("{e:#}"),
                    }),
                ),
            };
            let _ = handle.finish(status, error);
        }
    });
    Ok(initial)
}

#[tauri::command]
async fn prefetch_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::Prefetch).await
}
#[tauri::command]
#[allow(clippy::too_many_arguments)]
async fn shell_control(
    app: tauri::AppHandle,
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    action: String,
    mode: Option<String>,
    plan_sha256: Option<String>,
    transaction: Option<String>,
) -> Result<serde_json::Value, String> {
    let shared = state.engine.clone();
    let should_exit = action == "launch";
    let result =
        tauri::async_runtime::spawn_blocking(move || -> anyhow::Result<serde_json::Value> {
            let mut engine = shared
                .try_lock()
                .map_err(|_| anyhow::anyhow!("已有操作正在执行"))?;
            let root = engine.resolve(&root)?;
            match action.as_str() {
                "status" => shell_update::status(&root),
                "preview" => Ok(serde_json::to_value(shell_update::preview(
                    &root,
                    mode.as_deref().unwrap_or("normal"),
                )?)?),
                "launch" => {
                    if engine.inspect(&root)?.running {
                        anyhow::bail!("请先停止训练器");
                    }
                    let ctx = model::WorkspaceMutation::acquire(&root, &release_id)?;
                    shell_update::launch(
                        &ctx,
                        mode.as_deref().unwrap_or("normal"),
                        plan_sha256
                            .as_deref()
                            .ok_or_else(|| anyhow::anyhow!("缺少更新计划摘要"))?,
                    )
                }
                "recover" => {
                    if engine.inspect(&root)?.running {
                        anyhow::bail!("请先停止训练器");
                    }
                    shell_update::launch_recovery(
                        &root,
                        transaction
                            .as_deref()
                            .ok_or_else(|| anyhow::anyhow!("缺少更新事务"))?,
                    )
                }
                _ => anyhow::bail!("未知壳更新动作"),
            }
        })
        .await
        .map_err(|e| e.to_string())?
        .map_err(|e| format!("{e:#}"))?;
    if should_exit {
        app.exit(0);
    }
    Ok(result)
}
#[tauri::command]
async fn catalog_control(
    state: tauri::State<'_, Runtime>,
    root: String,
    action: String,
    fixture_case: Option<String>,
) -> Result<serde_json::Value, String> {
    let shared = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut engine = shared
            .try_lock()
            .map_err(|_| "已有操作正在执行".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        engine
            .catalog_control(&root, &action, fixture_case.as_deref())
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn preview_data_import(
    state: tauri::State<'_, Runtime>,
    root: String,
    request: data_import::ImportRequest,
) -> Result<serde_json::Value, String> {
    let shared = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = shared
            .try_lock()
            .map_err(|_| "已有操作正在执行".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        engine
            .preview_data_import(&root, &request)
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn apply_data_import(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    request: data_import::ImportRequest,
    plan_sha256: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::DataControl {
            action: "import".into(),
            request: Some(request),
            binding: None,
            plan: Some(plan_sha256),
            transaction: None,
        },
    )
    .await
}
#[tauri::command]
async fn preview_profile_binding(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    profile_id: String,
    rollback: bool,
) -> Result<data_import::BindingPlan, String> {
    let shared = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = shared
            .try_lock()
            .map_err(|_| "已有操作正在执行".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        engine
            .preview_profile_binding(&root, &release_id, &profile_id, rollback)
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn apply_profile_binding(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    request: data_import::BindingRequest,
    plan_sha256: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::DataControl {
            action: "binding".into(),
            request: None,
            binding: Some(request),
            plan: Some(plan_sha256),
            transaction: None,
        },
    )
    .await
}
#[tauri::command]
async fn recover_data_operation(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    kind: String,
    transaction: Option<String>,
) -> Result<operations::OperationSnapshot, String> {
    let action = match kind.as_str() {
        "import" => "recover_import",
        "binding" => "recover_binding",
        _ => return Err("未知资料恢复种类".into()),
    };
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::DataControl {
            action: action.into(),
            request: None,
            binding: None,
            plan: None,
            transaction,
        },
    )
    .await
}
#[tauri::command]
async fn query_engine_control(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    engine_id: String,
    action: String,
    rebuild: bool,
) -> Result<serde_json::Value, String> {
    let shared = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = shared
            .try_lock()
            .map_err(|_| "已有操作正在执行".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        engine
            .engine_query(&root, &release_id, &engine_id, &action, rebuild)
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn apply_engine_control(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    engine_id: String,
    action: String,
    plan: Option<serde_json::Value>,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::EngineControl {
            engine: engine_id,
            action,
            plan,
        },
    )
    .await
}
#[tauri::command]
async fn preview_gui_lifecycle(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    action: String,
    transaction: Option<String>,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有操作进行中".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        engine
            .preview_gui_lifecycle(&root, &release_id, &action, transaction.as_deref())
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn apply_gui_lifecycle(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    action: String,
    plan: Option<String>,
    transaction: Option<String>,
    instance: Option<String>,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::GuiLifecycle {
            action,
            plan,
            transaction,
            instance,
        },
    )
    .await
}
#[tauri::command]
async fn preview_gui_registration(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    instance_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有任务执行中，请稍后检查登记".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        engine
            .preview_gui_registration(&root, &release_id, instance_id.as_deref())
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}
#[tauri::command]
async fn restore_gui_registration(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    instance_id: String,
    plan_sha256: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::RestoreRegistration {
            instance_id,
            plan_sha256,
        },
    )
    .await
}
#[tauri::command]
async fn recover_gui_registration(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::RecoverRegistration).await
}
#[tauri::command]
async fn install_managed_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::Install).await
}

#[tauri::command]
async fn diagnose_gui(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine.lock().map_err(|_| "启动器状态锁异常".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        engine
            .diagnose_gui(&root, &release_id)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn plan_gui_repair(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    package: String,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine.lock().map_err(|_| "启动器状态锁异常".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        engine
            .plan_gui_repair(&root, &release_id, &package)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn repair_gui_package(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    package: String,
    plan_sha256: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::Repair {
            package,
            plan_sha256,
        },
    )
    .await
}

#[tauri::command]
async fn recover_gui_repair(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::Recover).await
}

#[tauri::command]
async fn preview_source_repair(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine.lock().map_err(|_| "启动器状态锁异常".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        engine
            .preview_source_repair(&root, &release_id)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn repair_managed_source(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::RepairSource).await
}

#[tauri::command]
async fn preview_base_python_repair(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有安装或检查正在执行，请稍后重试".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        engine
            .preview_base_python_repair(&root)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}

#[tauri::command]
async fn repair_base_python(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
    plan_sha256: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(
        state,
        root,
        release_id,
        ManagedAction::RepairBasePython { plan_sha256 },
    )
    .await
}

#[tauri::command]
async fn recover_base_python(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<operations::OperationSnapshot, String> {
    begin_release_operation(state, root, release_id, ManagedAction::RecoverBasePython).await
}

#[tauri::command]
fn operation_snapshot(
    state: tauri::State<'_, Runtime>,
    operation_id: String,
) -> Result<operations::OperationSnapshot, String> {
    state
        .operations
        .snapshot(&operation_id)
        .map_err(|e| format!("{e:#}"))
}
#[tauri::command]
fn operation_events(
    state: tauri::State<'_, Runtime>,
    operation_id: String,
    after_seq: u64,
) -> Result<Vec<operations::OperationEvent>, String> {
    state
        .operations
        .events_since(&operation_id, after_seq)
        .map_err(|e| format!("{e:#}"))
}
#[tauri::command]
fn cancel_operation(
    state: tauri::State<'_, Runtime>,
    operation_id: String,
) -> Result<operations::CancelReceipt, String> {
    state
        .operations
        .cancel(&operation_id)
        .map_err(|e| format!("{e:#}"))
}
#[tauri::command]
fn operation_history(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<Vec<operations::OperationSnapshot>, String> {
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
    let catalog = model::Catalog::embedded().map_err(|e| format!("{e:#}"))?;
    let layout =
        model::Layout::new(&root, &catalog.releases()[0].id).map_err(|e| format!("{e:#}"))?;
    let mut history = operations::load_snapshots(&layout).map_err(|e| format!("{e:#}"))?;
    for snapshot in &mut history {
        if let Ok(current) = state.operations.snapshot(&snapshot.id) {
            *snapshot = current;
        }
    }
    Ok(history)
}

async fn action(
    state: tauri::State<'_, Runtime>,
    root: String,
    op: &'static str,
) -> Result<Report, String> {
    let runtime = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut engine = runtime
            .try_lock()
            .map_err(|_| "已有安装、检查或启停操作正在执行".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        match op {
            "inspect" => engine.inspect(&root),
            "bootstrap" => engine.bootstrap(&root),
            "restore" => engine.restore(&root),
            "install" => engine.install_environment(&root),
            "start" => engine.start(&root),
            _ => unreachable!(),
        }
        .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn inspect(state: tauri::State<'_, Runtime>, root: String) -> Result<Report, String> {
    action(state, root, "inspect").await
}
#[tauri::command]
async fn bootstrap(state: tauri::State<'_, Runtime>, root: String) -> Result<Report, String> {
    action(state, root, "bootstrap").await
}
#[tauri::command]
async fn restore_trainer(state: tauri::State<'_, Runtime>, root: String) -> Result<Report, String> {
    action(state, root, "restore").await
}
#[tauri::command]
async fn install_environment(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<Report, String> {
    action(state, root, "install").await
}
#[tauri::command]
async fn start_trainer(
    state: tauri::State<'_, Runtime>,
    root: String,
    run_id: Option<String>,
) -> Result<Report, String> {
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
    if !root.is_absolute() || root.parent().is_none() {
        return Err("工作区必须为独立绝对目录".into());
    }
    let lifecycle = state.lifecycle.clone();
    // Reserve before scheduling slow work. A targeted stop arriving even before
    // this IPC is processed is remembered by begin_requested's tombstone.
    let run = lifecycle
        .begin_requested(&root, run_id.as_deref())
        .map_err(|e| format!("{e:#}"))?;
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut engine = match engine.try_lock() {
            Ok(engine) => engine,
            Err(_) => {
                lifecycle.fail_start(&run, "已有安装或完整检查正在执行，请完成后重试");
                return Err("已有安装或完整检查正在执行，请完成后重试".into());
            }
        };
        engine
            .start_reserved(&root, &run)
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}

async fn version_action(
    state: tauri::State<'_, Runtime>,
    root: String,
    id: String,
    operation: &'static str,
) -> Result<Report, String> {
    let runtime = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut engine = runtime.lock().map_err(|_| "启动器状态锁异常".to_string())?;
        let root = engine.resolve(&root).map_err(|e| format!("{e:#}"))?;
        match operation {
            "install" => engine.install_release(&root, &id),
            "select" => engine.select_release(&root, &id),
            "rollback" => engine.rollback_release(&root),
            "remove" => engine.remove_release(&root, &id),
            _ => unreachable!(),
        }
        .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn install_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<Report, String> {
    version_action(state, root, release_id, "install").await
}
#[tauri::command]
async fn select_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<Report, String> {
    version_action(state, root, release_id, "select").await
}
#[tauri::command]
async fn rollback_release(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<Report, String> {
    version_action(state, root, String::new(), "rollback").await
}
#[tauri::command]
async fn remove_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
) -> Result<Report, String> {
    version_action(state, root, release_id, "remove").await
}
#[tauri::command]
fn runtime_status(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<RuntimeSnapshot, String> {
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
    if !root.is_absolute() || root.parent().is_none() {
        return Err("工作区必须为独立绝对目录".into());
    }
    Ok(state.lifecycle.snapshot(&root))
}
#[tauri::command]
async fn stop_trainer(
    state: tauri::State<'_, Runtime>,
    run_id: Option<String>,
) -> Result<RuntimeSnapshot, String> {
    let lifecycle = state.lifecycle.clone();
    // Publish cancellation/stopping before waiting for the sole process owner.
    lifecycle.request_stop_for(run_id.as_deref());
    tauri::async_runtime::spawn_blocking(move || {
        lifecycle
            .stop_for(run_id.as_deref())
            .map_err(|e| format!("{e:#}"))
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn load_network_settings(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有任务执行中，请稍后读取网络设置".to_string())?;
        let root = engine
            .resolve(&root)
            .map_err(|error| format!("{error:#}"))?;
        let settings =
            network_policy::load_settings(&root).map_err(|error| format!("{error:#}"))?;
        let policy = network_policy::for_root(&root).map_err(|error| format!("{error:#}"))?;
        Ok(serde_json::json!({ "settings": settings, "diagnostic": policy.diagnostic(None) }))
    })
    .await
    .map_err(|error| error.to_string())?
}
#[tauri::command]
async fn save_network_settings(
    state: tauri::State<'_, Runtime>,
    root: String,
    settings: network_policy::Settings,
) -> Result<serde_json::Value, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有任务执行中，请稍后保存网络设置".to_string())?;
        engine
            .save_network_settings(&root, &settings)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}
#[tauri::command]
async fn choose_directory(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        Ok(app
            .dialog()
            .file()
            .set_title("选择空目录或正式启动器已有安装目录")
            .blocking_pick_folder()
            .map(|p| p.to_string()))
    })
    .await
    .map_err(|e| e.to_string())?
}
fn open_browser(url: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let system = std::env::var_os("SystemRoot").ok_or("缺少 SystemRoot")?;
        std::process::Command::new(PathBuf::from(system).join("System32/rundll32.exe"))
            .arg("url.dll,FileProtocolHandler")
            .arg(url)
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = url;
        Err("当前开发包仅支持 Windows 打开浏览器".into())
    }
}

#[tauri::command]
fn open_project_link(target: String) -> Result<(), String> {
    // 只接受固定目标名，前端不能传入任意 URL 或本地可执行文件。
    let url = match target.as_str() {
        "project" => "https://github.com/wochenlong/lora-scripts-next",
        "issues" => "https://github.com/wochenlong/lora-scripts-next/issues",
        "license" => "https://github.com/wochenlong/lora-scripts-next/blob/main/LICENSE",
        _ => return Err("未知项目链接".into()),
    };
    open_browser(url)
}

#[tauri::command]
async fn open_trainer(state: tauri::State<'_, Runtime>) -> Result<(), String> {
    let lifecycle = state.lifecycle.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let url = lifecycle.url().map_err(|e| e.to_string())?;
        open_browser(&url)
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
    if std::env::args().nth(1).as_deref() == Some("--shell-trial") {
        let result = std::env::args()
            .nth(2)
            .map(PathBuf::from)
            .ok_or_else(|| anyhow::anyhow!("缺少只读试运行事务目录"))
            .and_then(trial_ui::run);
        if let Err(error) = result {
            eprintln!("{error:#}");
            std::process::exit(1);
        }
        return;
    }
    // The same core is callable for reproducible recovery/health diagnostics without a WebView.
    let args: Vec<String> = std::env::args().collect();
    if args
        .get(1)
        .is_some_and(|a| a == "--probe" || a == "--manage")
    {
        let result = (|| -> anyhow::Result<()> {
            let op = args.get(2).ok_or_else(|| {
                anyhow::anyhow!("--probe inspect|bootstrap|restore|install|smoke <absolute-root>")
            })?;
            let root = PathBuf::from(
                args.get(3)
                    .ok_or_else(|| anyhow::anyhow!("需要绝对工作区路径"))?,
            );
            let (log, _) = core::logger();
            let mut engine = Engine::new(root.clone(), log);
            let root = engine.resolve(&root.to_string_lossy())?;
            if op == "engine-fixture-smoke" {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&engine.engine_fixture_smoke(&root)?)?
                );
                return Ok(());
            }
            if matches!(
                op.as_str(),
                "diagnose-gui" | "plan-gui-repair" | "preview-source-repair"
            ) {
                let id = args
                    .get(4)
                    .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?;
                let value = if op == "preview-source-repair" {
                    engine.preview_source_repair(&root, id)?
                } else if op == "diagnose-gui" {
                    engine.diagnose_gui(&root, id)?
                } else {
                    engine.plan_gui_repair(
                        &root,
                        id,
                        args.get(5).ok_or_else(|| anyhow::anyhow!("缺少包名称"))?,
                    )?
                };
                println!("{}", serde_json::to_string_pretty(&value)?);
                return Ok(());
            }
            if op == "preview-base-python" {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&engine.preview_base_python_repair(&root)?)?
                );
                return Ok(());
            }
            if op == "preview-gui-registration" {
                let release = args
                    .get(4)
                    .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?;
                let value = engine.preview_gui_registration(
                    &root,
                    release,
                    args.get(5).map(String::as_str),
                )?;
                println!("{}", serde_json::to_string_pretty(&value)?);
                return Ok(());
            }
            let report = match op.as_str() {
                "inspect" => engine.inspect(&root)?,
                "bootstrap" => engine.bootstrap(&root)?,
                "restore" => engine.restore(&root)?,
                "install" => engine.install_environment(&root)?,
                "prefetch" => {
                    let manager = operations::OperationManager::default();
                    let id = format!("cli-download-{}-{}", model::now(), std::process::id());
                    let operation = manager.start(&id, operations::OperationKind::Download)?;
                    engine.prefetch_release(
                        &root,
                        args.get(4)
                            .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?,
                        &operation,
                    )?;
                    engine.inspect(&root)?
                }
                "install-release" => engine.install_release(
                    &root,
                    args.get(4)
                        .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?,
                )?,
                "repair-gui-package"
                | "recover-gui-repair"
                | "repair-managed-source"
                | "repair-base-python"
                | "recover-base-python"
                | "restore-gui-registration"
                | "recover-gui-registration" => {
                    let manager = operations::OperationManager::default();
                    let id = format!("cli-repair-{}-{}", model::now(), std::process::id());
                    let operation = manager.start(&id, operations::OperationKind::Repair)?;
                    let release = args
                        .get(4)
                        .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?;
                    if op == "restore-gui-registration" || op == "recover-gui-registration" {
                        let reviewed = if op == "restore-gui-registration" {
                            Some((
                                args.get(5)
                                    .ok_or_else(|| anyhow::anyhow!("缺少明确实例ID"))?
                                    .as_str(),
                                args.get(6)
                                    .ok_or_else(|| anyhow::anyhow!("缺少已审核plan SHA256"))?
                                    .as_str(),
                            ))
                        } else {
                            None
                        };
                        engine.restore_gui_registration_operation(
                            &root, release, reviewed, &operation,
                        )?;
                    } else if op == "repair-base-python" || op == "recover-base-python" {
                        let plan = if op == "repair-base-python" {
                            Some(
                                args.get(5)
                                    .ok_or_else(|| anyhow::anyhow!("缺少已审核 plan SHA256"))?
                                    .as_str(),
                            )
                        } else {
                            None
                        };
                        engine.repair_base_python_operation(&root, release, plan, &operation)?;
                    } else if op == "repair-managed-source" {
                        engine.repair_source_operation(&root, release, &operation)?;
                    } else if op == "recover-gui-repair" {
                        engine.recover_gui_operation(&root, release, &operation)?;
                    } else {
                        engine.repair_gui_operation(
                            &root,
                            release,
                            args.get(5).ok_or_else(|| anyhow::anyhow!("缺少包名称"))?,
                            args.get(6)
                                .ok_or_else(|| anyhow::anyhow!("缺少已审核 plan SHA256"))?,
                            &operation,
                        )?;
                    }
                    engine.inspect(&root)?
                }
                "select" => engine.select_release(
                    &root,
                    args.get(4)
                        .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?,
                )?,
                "rollback" => engine.rollback_release(&root)?,
                "remove" => engine.remove_release(
                    &root,
                    args.get(4)
                        .ok_or_else(|| anyhow::anyhow!("缺少 release ID"))?,
                )?,
                "smoke" => {
                    let r = engine.start(&root)?;
                    engine.stop();
                    r
                }
                _ => anyhow::bail!("未知 probe 操作"),
            };
            println!("{}", serde_json::to_string_pretty(&report)?);
            Ok(())
        })();
        if let Err(e) = result {
            eprintln!("{}", network_policy::redact(&format!("{e:#}")));
            std::process::exit(1);
        }
        return;
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let log: Logger = Arc::new(move |line| {
                let _ = handle.emit("launcher:log", line);
            });
            let root = app
                .path()
                .app_local_data_dir()?
                .join("installations/default");
            let engine = Engine::new(root.clone(), log);
            let lifecycle = engine.lifecycle.clone();
            let handle = app.handle().clone();
            lifecycle.set_listener(Arc::new(move |snapshot| {
                let _ = handle.emit("launcher:runtime", snapshot);
            }));
            app.manage(Runtime {
                engine: Arc::new(Mutex::new(engine)),
                lifecycle,
                operations: Arc::new(operations::OperationManager::default()),
                default_root: root,
                workers: Arc::new(std::sync::atomic::AtomicUsize::new(0)),
                shutting_down: std::sync::atomic::AtomicBool::new(false),
                exit_ready: Arc::new(std::sync::atomic::AtomicBool::new(false)),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            prefetch_release,
            install_managed_release,
            diagnose_gui,
            plan_gui_repair,
            repair_gui_package,
            recover_gui_repair,
            preview_source_repair,
            repair_managed_source,
            preview_base_python_repair,
            repair_base_python,
            recover_base_python,
            preview_gui_lifecycle,
            apply_gui_lifecycle,
            query_engine_control,
            apply_engine_control,
            catalog_control,
            shell_control,
            preview_data_import,
            apply_data_import,
            preview_profile_binding,
            apply_profile_binding,
            recover_data_operation,
            preview_gui_registration,
            restore_gui_registration,
            recover_gui_registration,
            operation_snapshot,
            operation_events,
            cancel_operation,
            operation_history,
            inspect,
            bootstrap,
            restore_trainer,
            install_environment,
            start_trainer,
            install_release,
            select_release,
            rollback_release,
            remove_release,
            stop_trainer,
            runtime_status,
            load_network_settings,
            save_network_settings,
            choose_directory,
            open_trainer,
            open_project_link
        ])
        .build(tauri::generate_context!())
        .expect("无法初始化桌面启动器")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = &event {
                if let Some(runtime) = app.try_state::<Runtime>() {
                    runtime.lifecycle.request_stop();
                    let first = !runtime
                        .shutting_down
                        .swap(true, std::sync::atomic::Ordering::AcqRel);
                    if !runtime
                        .exit_ready
                        .load(std::sync::atomic::Ordering::Acquire)
                        && runtime.workers.load(std::sync::atomic::Ordering::Acquire) > 0
                    {
                        api.prevent_exit();
                        let _ = runtime.operations.cancel_running();
                        if first {
                            let workers = runtime.workers.clone();
                            let exit_ready = runtime.exit_ready.clone();
                            let app = app.clone();
                            std::thread::spawn(move || {
                                let deadline =
                                    std::time::Instant::now() + std::time::Duration::from_secs(5);
                                while workers.load(std::sync::atomic::Ordering::Acquire) > 0
                                    && std::time::Instant::now() < deadline
                                {
                                    std::thread::sleep(std::time::Duration::from_millis(20));
                                }
                                exit_ready.store(true, std::sync::atomic::Ordering::Release);
                                app.exit(0);
                            });
                        }
                    }
                }
            }
            if matches!(event, tauri::RunEvent::Exit) {
                if let Some(runtime) = app.try_state::<Runtime>() {
                    let _ = runtime.operations.cancel_running();
                    let _ = runtime.lifecycle.stop();
                }
            }
        });
}
