#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod budgeted_body;
mod core;
mod download_budget;
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
mod source_integrity;
mod wheel_integrity;
use core::{Engine, Logger, Report};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

struct Runtime {
    engine: Arc<Mutex<Engine>>,
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
    let catalog = model::Catalog::embedded().map_err(|e| format!("{e:#}"))?;
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
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
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
                ManagedAction::RestoreRegistration { .. } | ManagedAction::RecoverRegistration => {
                    operations::OperationKind::Repair
                }
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
        let mut engine = runtime.lock().map_err(|_| "启动器状态锁异常".to_string())?;
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
async fn start_trainer(state: tauri::State<'_, Runtime>, root: String) -> Result<Report, String> {
    action(state, root, "start").await
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
async fn stop_trainer(state: tauri::State<'_, Runtime>) -> Result<(), String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        engine
            .lock()
            .map(|mut e| e.stop())
            .map_err(|_| "状态锁异常".to_string())
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
async fn get_download_budget(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<download_budget::BudgetSnapshot, String> {
    let root = if root.trim().is_empty() {
        state.default_root.clone()
    } else {
        PathBuf::from(root.trim())
    };
    tauri::async_runtime::spawn_blocking(move || {
        let catalog = model::Catalog::embedded().map_err(|error| format!("{error:#}"))?;
        let layout = model::Layout::new(&root, &catalog.releases()[0].id)
            .map_err(|error| format!("{error:#}"))?;
        download_budget::snapshot_with_receipt(&layout).map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}
#[tauri::command]
async fn save_download_budget(
    state: tauri::State<'_, Runtime>,
    root: String,
    expected_revision: Option<u64>,
    root_body_cap_bytes: u64,
) -> Result<download_budget::BudgetSnapshot, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有任务执行中，请稍后保存下载额度".to_string())?;
        engine
            .save_download_budget(&root, expected_revision, root_body_cap_bytes)
            .map_err(|error| format!("{error:#}"))
    })
    .await
    .map_err(|error| error.to_string())?
}
#[tauri::command]
async fn reconcile_download_budget(
    state: tauri::State<'_, Runtime>,
    root: String,
) -> Result<download_budget::BudgetSnapshot, String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let engine = engine
            .try_lock()
            .map_err(|_| "已有任务执行中，请稍后结清中断计账".to_string())?;
        engine
            .reconcile_download_budget(&root)
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
#[tauri::command]
async fn open_trainer(state: tauri::State<'_, Runtime>) -> Result<(), String> {
    let engine = state.engine.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let url = engine
            .lock()
            .map_err(|_| "状态锁异常".to_string())?
            .url()
            .map_err(|e| e.to_string())?;
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
        }
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
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
            if matches!(
                op.as_str(),
                "download-budget" | "set-download-budget" | "reconcile-download-budget"
            ) {
                let value = match op.as_str() {
                    "download-budget" => {
                        let catalog = model::Catalog::embedded()?;
                        let layout = model::Layout::new(&root, &catalog.releases()[0].id)?;
                        download_budget::snapshot_with_receipt(&layout)?
                    }
                    "set-download-budget" => {
                        let cap = args
                            .get(4)
                            .ok_or_else(|| anyhow::anyhow!("缺少非零累计正文额度（字节整数）"))?
                            .parse::<u64>()?;
                        let revision = args.get(5).ok_or_else(|| {
                            anyhow::anyhow!("缺少expected revision；首次启用请明确填new")
                        })?;
                        let revision = if revision == "new" {
                            None
                        } else {
                            Some(revision.parse::<u64>()?)
                        };
                        engine.save_download_budget(
                            root.to_str()
                                .ok_or_else(|| anyhow::anyhow!("根目录不是UTF-8"))?,
                            revision,
                            cap,
                        )?
                    }
                    _ => engine.reconcile_download_budget(
                        root.to_str()
                            .ok_or_else(|| anyhow::anyhow!("根目录不是UTF-8"))?,
                    )?,
                };
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
            app.manage(Runtime {
                engine: Arc::new(Mutex::new(Engine::new(root.clone(), log))),
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
            load_network_settings,
            save_network_settings,
            get_download_budget,
            save_download_budget,
            reconcile_download_budget,
            choose_directory,
            open_trainer
        ])
        .build(tauri::generate_context!())
        .expect("无法初始化桌面启动器")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = &event {
                if let Some(runtime) = app.try_state::<Runtime>() {
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
                    if let Ok(mut engine) = runtime.engine.try_lock() {
                        engine.stop();
                    }
                }
            }
        });
}
