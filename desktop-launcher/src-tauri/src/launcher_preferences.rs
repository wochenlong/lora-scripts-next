//! 壳偏好独立于训练器工作区；收起窗口不触碰服务或后台操作。
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

pub(crate) const TRAY_ID: &str = "next-trainer-launcher";

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
pub enum Language {
    #[default]
    #[serde(rename = "zh-CN")]
    Chinese,
    #[serde(rename = "en-US")]
    English,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct LauncherPreferences {
    pub close_to_tray: bool,
    pub language: Language,
}

impl Default for LauncherPreferences {
    fn default() -> Self {
        Self {
            close_to_tray: true,
            language: Language::Chinese,
        }
    }
}

pub struct PreferencesState {
    path: PathBuf,
    value: Arc<Mutex<LauncherPreferences>>,
}

impl PreferencesState {
    pub fn open(data: &Path) -> Result<Self> {
        crate::model::validate_storage_directory(data)?;
        let path = data.join("launcher-preferences.json");
        let preferences = match std::fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes).context("无法读取启动器偏好")?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                LauncherPreferences::default()
            }
            Err(error) => return Err(error.into()),
        };
        Ok(Self {
            path,
            value: Arc::new(Mutex::new(preferences)),
        })
    }

    pub fn snapshot(&self) -> Result<LauncherPreferences> {
        self.value
            .lock()
            .map(|value| value.clone())
            .map_err(|_| anyhow::anyhow!("启动器偏好锁异常"))
    }

    pub fn close_to_tray(&self) -> bool {
        self.snapshot()
            .map(|value| value.close_to_tray)
            .unwrap_or(false)
    }
}

#[tauri::command]
pub fn load_launcher_preferences(
    state: tauri::State<'_, PreferencesState>,
) -> Result<LauncherPreferences, String> {
    state.snapshot().map_err(|error| format!("{error:#}"))
}

#[tauri::command]
pub async fn save_launcher_preferences(
    app: tauri::AppHandle,
    state: tauri::State<'_, PreferencesState>,
    preferences: LauncherPreferences,
) -> Result<LauncherPreferences, String> {
    let path = state.path.clone();
    let value = state.value.clone();
    let saved = tauri::async_runtime::spawn_blocking(move || -> Result<LauncherPreferences> {
        let mut current = value
            .lock()
            .map_err(|_| anyhow::anyhow!("启动器偏好锁异常"))?;
        // 原子替换成功后才切换内存行为，写入失败保留已保存的设置。
        crate::model::write_json_atomic(&path, &preferences)?;
        *current = preferences.clone();
        Ok(preferences)
    })
    .await
    .map_err(|error| error.to_string())?
    .map_err(|error| format!("{error:#}"))?;
    if let Err(error) = refresh_tray(&app, saved.language) {
        eprintln!("无法刷新托盘菜单：{error:#}");
    }
    Ok(saved)
}

#[tauri::command]
pub fn request_launcher_exit(app: tauri::AppHandle) {
    // 与安装器/更新器退出共用 RunEvent 的取消任务、停止服务和等待收尾。
    app.exit(0);
}

/// 原生验收只读状态；图标位置来自当前进程自己的 TrayIcon，便于精确恢复窗口。
#[tauri::command]
pub fn launcher_window_status(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let window = app.get_webview_window("main").ok_or("主窗口不存在")?;
    let tray = app.tray_by_id(TRAY_ID);
    let tray_rect = tray
        .as_ref()
        .map(|tray| tray.rect())
        .transpose()
        .map_err(|error| error.to_string())?
        .flatten();
    Ok(serde_json::json!({
        "visible": window.is_visible().map_err(|error| error.to_string())?,
        "is_minimized": window.is_minimized().map_err(|error| error.to_string())?,
        "tray_ready": tray.is_some(),
        "tray_rect": tray_rect,
    }))
}

fn restore_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn tray_menu(app: &tauri::AppHandle, language: Language) -> tauri::Result<Menu<tauri::Wry>> {
    let (show, quit) = match language {
        Language::Chinese => ("显示主窗口", "退出启动器"),
        Language::English => ("Show main window", "Quit launcher"),
    };
    let show = MenuItem::with_id(app, "launcher-show", show, true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "launcher-quit", quit, true, None::<&str>)?;
    Menu::with_items(app, &[&show, &separator, &quit])
}

fn refresh_tray(app: &tauri::AppHandle, language: Language) -> Result<()> {
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        tray.set_menu(Some(tray_menu(app, language)?))?;
        tray.set_tooltip(Some(match language {
            Language::Chinese => "Next Trainer 启动器",
            Language::English => "Next Trainer Launcher",
        }))?;
    }
    Ok(())
}

pub fn setup(app: &tauri::AppHandle, data: &Path) -> Result<Option<String>> {
    let state = PreferencesState::open(data)?;
    let preferences = state.snapshot()?;
    app.manage(state);
    // 托盘不可用时保留主窗口和普通退出；不能因可选系统能力阻断启动。
    Ok(match setup_tray(app, &preferences) {
        Ok(()) => None,
        Err(error) => {
            // 包括已创建图标之后的菜单/提示初始化失败，统一回到普通关闭。
            drop(app.remove_tray_by_id(TRAY_ID));
            Some(format!("{error:#}"))
        }
    })
}

fn setup_tray(app: &tauri::AppHandle, preferences: &LauncherPreferences) -> Result<()> {
    let menu = tray_menu(app, preferences.language)?;
    let icon = app
        .default_window_icon()
        .cloned()
        .context("启动器缺少托盘图标")?;
    TrayIconBuilder::with_id(TRAY_ID)
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "launcher-show" => restore_window(app),
            "launcher-quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } | TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                }
            ) {
                restore_window(tray.app_handle());
            }
        })
        .build(app)?;
    refresh_tray(app, preferences.language)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_install_defaults_to_chinese_and_close_to_tray() {
        let preferences: LauncherPreferences = serde_json::from_str("{}").unwrap();
        assert!(preferences.close_to_tray);
        assert_eq!(preferences.language, Language::Chinese);
        assert!(serde_json::from_str::<LauncherPreferences>(r#"{"language":"de-DE"}"#).is_err());
    }

    #[test]
    fn saved_preferences_survive_reopen() {
        let data = std::env::temp_dir().join(format!(
            "next-trainer-preferences-{}-{}",
            std::process::id(),
            crate::model::now()
        ));
        assert!(!data.exists());
        let store = PreferencesState::open(&data).unwrap();
        assert_eq!(store.snapshot().unwrap(), LauncherPreferences::default());
        let preferences = LauncherPreferences {
            close_to_tray: false,
            language: Language::English,
        };
        crate::model::write_json_atomic(&store.path, &preferences).unwrap();
        let reopened = PreferencesState::open(&data).unwrap();
        assert_eq!(reopened.snapshot().unwrap(), preferences);
        // 此目录由本测试新建，删除前再次证明它位于系统临时目录下。
        assert_eq!(data.parent(), Some(std::env::temp_dir().as_path()));
        std::fs::remove_file(&store.path).unwrap();
        std::fs::remove_dir(data).unwrap();
    }
}
