#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#[allow(dead_code)] // 同一纯协议也由主壳编译；helper不调用UI侧准备和握手写入口。
#[path = "../../src-tauri/src/shell_update_protocol.rs"]
mod protocol;

fn run() -> anyhow::Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 || (args[0] != "apply" && args[0] != "recover") {
        anyhow::bail!(
            "用法：next-trainer-updater apply|recover <绝对事务目录>；不支持任意URL、命令或进程名"
        );
    }
    let tx = std::path::PathBuf::from(&args[1]);
    let intent = protocol::helper_apply(&tx, args[0] == "recover")?;
    println!(
        "{}",
        serde_json::json!({"transaction":intent.transaction,"status":intent.status,"production_update":false})
    );
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error:#}");
        std::process::exit(1);
    }
}
