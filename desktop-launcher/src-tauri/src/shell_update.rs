//! 壳更新主进程协调。候选来源固定为当前交付包，只在显式签名沙盒会话中启用。
use crate::{
    data_import,
    model::{Registry, WorkspaceMutation},
    shell_update_protocol as protocol, signed_catalog,
};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

pub fn preview(root: &Path, trial_mode: &str) -> Result<protocol::Plan> {
    if !matches!(trial_mode, "normal" | "reject") {
        bail!("未知内置trial动作");
    }
    protocol::assert_ready(root)?;
    data_import::assert_binding_ready(root)?;
    Registry::load(root)?.assert_base_python_ready()?;
    let own = std::env::current_exe()?;
    let asset = protocol::identity(&own, 1024 * 1024 * 1024)?;
    let proof =
        signed_catalog::verify_shell_fixture(root, &asset.sha256, &asset.sha256, asset.bytes)?;
    protocol::verify_fixture_proof(root, &proof, &asset)?;
    let mut plan = protocol::Plan {
        schema_version: 1,
        authorized_at: protocol::now(),
        root_absolute: root.into(),
        current_relative: PathBuf::from(protocol::CURRENT),
        candidate_relative: PathBuf::from(protocol::CANDIDATE),
        asset,
        controls: protocol::capture_controls(root, true)?,
        trust_proof: proof,
        trial_mode: trial_mode.into(),
        plan_sha256: String::new(),
    };
    // 授权时间用于恢复，不属于用户可变预览输入；同一会话时间固定，计划摘要可在下一秒执行。
    plan.authorized_at = plan.trust_proof["history"]["receipts"]
        .as_array()
        .and_then(|v| v.last())
        .and_then(|v| v["accepted_at"].as_u64())
        .context("缺少壳fixture可信接受时间")?;
    protocol::seal_plan(&mut plan)?;
    Ok(plan)
}
fn helper() -> Result<(PathBuf, protocol::Identity)> {
    let sha = option_env!("NEXT_TRAINER_UPDATER_SHA256")
        .context("当前开发包未锁定独立helper，请先构建分发候选")?;
    let bytes = option_env!("NEXT_TRAINER_UPDATER_BYTES")
        .context("当前开发包缺少helper大小身份")?
        .parse::<u64>()?;
    let path = std::env::current_exe()?
        .parent()
        .context("壳目录缺失")?
        .join("next-trainer-updater.exe");
    protocol::regular(&path)?;
    let expected = protocol::Identity {
        bytes,
        sha256: sha.into(),
    };
    if protocol::identity(&path, 64 * 1024 * 1024)? != expected {
        bail!("独立helper不符合本包编译锁定身份");
    }
    Ok((path, expected))
}
/// 调用层须停完受管服务/变更worker，持同一workspace lease；返回后应退出主壳。
pub fn launch(ctx: &WorkspaceMutation, trial_mode: &str, expected_sha: &str) -> Result<Value> {
    let root = &ctx.layout().root;
    let plan = preview(root, trial_mode)?;
    if plan.plan_sha256 != expected_sha {
        bail!("壳更新计划变化，请重新预览");
    }
    let (helper, helper_identity) = helper()?;
    let parent = protocol::process_identity(std::process::id())?.context("无法锁定主壳进程身份")?;
    let tx = protocol::prepare(root, &plan, parent, &std::env::current_exe()?)?;
    let mut command = Command::new(&helper);
    command
        .arg("apply")
        .arg(&tx)
        .current_dir(&tx)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let child = command
        .spawn()
        .context("独立helper启动失败；已保留可恢复事务")?;
    Ok(
        json!({"schema_version":1,"transaction_dir":tx,"helper_pid":child.id(),"helper_identity":helper_identity,"status":"waiting_for_parent_exit","production_update":false,"required_action":"exit_launcher"}),
    )
}
pub fn launch_recovery(root: &Path, transaction: &str) -> Result<Value> {
    crate::model::validate_component(transaction)?;
    if !transaction.starts_with("shell-update-") {
        bail!("壳恢复事务ID无效");
    }
    let tx = root.join("updates/shell").join(transaction);
    protocol::owned(root, &tx)?;
    let intent = protocol::load_intent(&tx)?;
    if intent.plan.root_absolute != root {
        bail!("壳恢复根身份不符");
    }
    let (helper, identity) = helper()?;
    let mut command = Command::new(helper);
    command
        .arg("recover")
        .arg(&tx)
        .current_dir(&tx)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let child = command.spawn()?;
    Ok(
        json!({"transaction_dir":tx,"helper_pid":child.id(),"helper_identity":identity,"status":"recovering","production_update":false}),
    )
}
pub fn status(root: &Path) -> Result<Value> {
    let path = root.join("updates/shell/active.json");
    protocol::owned(root, &path)?;
    if !path.exists() {
        return Ok(
            json!({"status":"unavailable","production_update":false,"reason":"生产壳签名资产尚未配置；同包fixture须先打开显式新沙盒会话"}),
        );
    }
    let value: Value = serde_json::from_slice(&std::fs::read(&path)?)?;
    let transaction = value["transaction"].as_str().context("壳活动事务ID缺失")?;
    crate::model::validate_component(transaction)?;
    let intent = protocol::load_intent(&root.join("updates/shell").join(transaction))?;
    Ok(
        json!({"status":intent.status,"transaction":intent.transaction,"failure":intent.failure,"asset":intent.plan.asset,"production_update":false,"migration_status":if intent.status=="committed"{Some(protocol::migration_status(&root.join("updates/shell").join(transaction))?)}else{None}}),
    )
}
