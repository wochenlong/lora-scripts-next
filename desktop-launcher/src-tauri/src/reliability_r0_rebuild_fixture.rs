//! CR-020 R0/R1 专属提交边界工厂；只调用正式事务步骤，不伪造健康证明或终态。
use super::*;

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
