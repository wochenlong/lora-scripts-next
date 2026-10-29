#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod core;
mod model;
mod operations;
#[cfg(test)]
mod recovery;
mod runtime_view;
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
#[tauri::command]
async fn prefetch_release(
    state: tauri::State<'_, Runtime>,
    root: String,
    release_id: String,
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
    catalog.release(&release_id).map_err(|e| format!("{e:#}"))?;
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
        .start(&id, operations::OperationKind::Download)
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
            engine.prefetch_release(&root, &release_id, &handle)
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
            eprintln!("{e:#}");
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
