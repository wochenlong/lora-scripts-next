//! 独立只读壳试运行入口；不创建Runtime，不注册产品变更命令。
use crate::shell_update_protocol as protocol;
use std::{path::PathBuf, sync::Mutex};
struct Trial {
    directory: PathBuf,
    request: protocol::TrialRequest,
    rendered: Mutex<bool>,
    recovery: Mutex<bool>,
}
#[tauri::command]
fn trial_context(state: tauri::State<'_, Trial>) -> protocol::TrialRequest {
    state.request.clone()
}
fn confirm(state: &Trial, token: &str, rendered: bool) -> Result<(), String> {
    if token != state.request.token {
        return Err("试运行令牌不符".into());
    }
    if rendered {
        *state.rendered.lock().map_err(|_| "渲染状态锁异常")? = true;
    } else {
        *state.recovery.lock().map_err(|_| "恢复入口状态锁异常")? = true;
    }
    let rendered = *state.rendered.lock().map_err(|_| "渲染状态锁异常")?;
    let recovery = *state.recovery.lock().map_err(|_| "恢复入口状态锁异常")?;
    if rendered && recovery {
        protocol::write_trial_ack(&state.directory, token, true, true)
            .map_err(|e| format!("{e:#}"))?;
    }
    Ok(())
}
#[tauri::command]
fn trial_rendered(state: tauri::State<'_, Trial>, token: String) -> Result<(), String> {
    confirm(&state, &token, true)
}
#[tauri::command]
fn trial_recovery_available(state: tauri::State<'_, Trial>, token: String) -> Result<(), String> {
    confirm(&state, &token, false)
}
#[tauri::command]
fn trial_poll(
    app: tauri::AppHandle,
    state: tauri::State<'_, Trial>,
) -> Result<Option<protocol::TrialResult>, String> {
    let result = protocol::trial_result(&state.directory).map_err(|e| format!("{e:#}"))?;
    if result.is_some() {
        app.exit(0);
    }
    Ok(result)
}
pub fn run(directory: PathBuf) -> anyhow::Result<()> {
    let request = protocol::trial_context(&directory)?;
    let mut context = tauri::generate_context!();
    for window in &mut context.config_mut().app.windows {
        window.url = tauri::WebviewUrl::App("index.html?shell-trial=1".into());
    }
    tauri::Builder::default()
        .manage(Trial {
            directory,
            request,
            rendered: Mutex::new(false),
            recovery: Mutex::new(false),
        })
        .invoke_handler(tauri::generate_handler![
            trial_context,
            trial_rendered,
            trial_recovery_available,
            trial_poll
        ])
        .run(context)?;
    Ok(())
}
