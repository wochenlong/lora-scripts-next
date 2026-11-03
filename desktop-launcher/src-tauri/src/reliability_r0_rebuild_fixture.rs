//! CR-020 R0/R1 专属提交边界工厂；只调用正式事务步骤，不伪造健康证明或终态。
use super::*;

struct CancellationCheckpoint {
    transaction: String,
    checkpoint: &'static str,
    request: Option<Box<dyn FnOnce()>>,
    observation: Option<Value>,
}

thread_local! {
    static CANCELLATION_CHECKPOINT: std::cell::RefCell<Option<CancellationCheckpoint>> = const {
        std::cell::RefCell::new(None)
    };
}

pub(in crate::core) fn arm_cancellation_checkpoint(
    transaction: &str,
    checkpoint: &'static str,
    request: impl FnOnce() + 'static,
) {
    CANCELLATION_CHECKPOINT.with(|slot| {
        assert!(slot.borrow().is_none(), "取消 checkpoint 未清理");
        *slot.borrow_mut() = Some(CancellationCheckpoint {
            transaction: transaction.into(),
            checkpoint,
            request: Some(Box::new(request)),
            observation: None,
        });
    });
}

pub(super) fn cancellation_checkpoint(intent: &Intent, checkpoint: &str) {
    CANCELLATION_CHECKPOINT.with(|slot| {
        let mut slot = slot.borrow_mut();
        let Some(armed) = slot.as_mut() else { return };
        if armed.transaction != intent.transaction || armed.checkpoint != checkpoint {
            return;
        }
        let request = armed.request.take().expect("checkpoint 只能触发一次");
        armed.observation = Some(json!({
            "transaction":intent.transaction,"checkpoint":checkpoint,
            "in_memory_status":intent.status,
            "candidate_state_observed":intent.candidate_state.is_some(),
            "candidate_tree_observed":intent.candidate_tree_sha256.is_some(),
            "complete_commit_authority":intent.terminal_status.is_some() && intent.preservation_file.is_some(),
        }));
        request();
    });
}

pub(in crate::core) fn take_cancellation_checkpoint() -> Value {
    CANCELLATION_CHECKPOINT.with(|slot| {
        slot.borrow_mut()
            .take()
            .expect("未设置取消 checkpoint")
            .observation
            .expect("取消 checkpoint 未被正式恢复入口触发")
    })
}

pub(in crate::core) fn prepare_incomplete_phase(
    ctx: &WorkspaceMutation,
    release: &Release,
    transaction: &str,
    phase: &str,
) -> Result<()> {
    if !matches!(phase, "building" | "validating") {
        bail!("不支持的小夹具阶段");
    }
    let layout = ctx.layout();
    let mut intent: Intent =
        serde_json::from_slice(&read(layout, &intent_path(layout, transaction)?)?)?;
    validate(layout, release, &intent)?;
    let recipe = GuiRecipe::embedded()?;
    instances::rebuild_create(
        ctx,
        &intent.candidate_id,
        recipe.id(),
        RECIPE_SHA,
        transaction,
        &CancelToken::new(),
    )?;
    // 与正式 execute 的持久阶段转换相同；不生成健康证明或提交授权。
    intent.status = phase.into();
    store(layout, &intent)
}

pub(in crate::core) fn prepare_orphan_commit_boundary(
    ctx: &WorkspaceMutation,
    release: &Release,
    transaction: &str,
) -> Result<()> {
    let layout = ctx.layout();
    let mut intent: Intent =
        serde_json::from_slice(&read(layout, &intent_path(layout, transaction)?)?)?;
    validate(layout, release, &intent)?;
    let boundary: RebuildBoundary = serde_json::from_slice(&read(
        layout,
        &layout
            .root
            .join("backups")
            .join(transaction)
            .join("boundary.json"),
    )?)?;
    let recipe = GuiRecipe::embedded()?;
    let cancel = CancelToken::new();
    instances::rebuild_create(
        ctx,
        &intent.candidate_id,
        recipe.id(),
        RECIPE_SHA,
        transaction,
        &cancel,
    )?;
    prepare_commit(ctx, release, &mut intent, &boundary, false, &cancel)?;
    // 模拟进程在完整 committing 授权持久化后、finish 之前中断。
    assert_eq!(intent.status, "committing");
    assert_eq!(intent.terminal_status.as_deref(), Some("orphaned"));
    Ok(())
}
