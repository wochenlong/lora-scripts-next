//! 同一release的显式实例回退；历史由已提交重建intent证明，仅复验clean旧实例后0B切回。
use crate::{
    gui_registration_integrity::{self, TrustedEnvironment},
    instances,
    model::{self, EnvironmentBinding, Layout, Registry, Release, WorkspaceMutation},
    operations::CancelToken,
    query_tasks::QueryStage,
    scan_observation,
};
use anyhow::{bail, Context, Result};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Identity {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    root_absolute: PathBuf,
    release_id: String,
    history_transaction: String,
    history_identity: Identity,
    old_registry: Identity,
    current_binding: EnvironmentBinding,
    target_binding: EnvironmentBinding,
    target_state: Identity,
    proof: TrustedEnvironment,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    root_absolute: PathBuf,
    release_id: String,
    transaction: String,
    status: String,
    plan: Plan,
    plan_sha256: String,
    new_registry: Identity,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn identity(bytes: &[u8]) -> Identity {
    Identity {
        bytes: bytes.len() as u64,
        sha256: hash(bytes),
    }
}
fn check_control(cancel: Option<&CancelToken>) -> Result<()> {
    scan_observation::check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    Ok(())
}
// 只读结果先保存再判权威停止原因；不把Operation token放进共享写入/保全作用域。
fn readonly<T>(cancel: Option<&CancelToken>, work: impl FnOnce() -> Result<T>) -> Result<T> {
    check_control(cancel)?;
    let result = work();
    check_control(cancel)?;
    result
}
fn decode<T: DeserializeOwned>(bytes: &[u8], cancel: Option<&CancelToken>) -> Result<T> {
    readonly(cancel, || Ok(serde_json::from_slice(bytes)?))
}
fn read(layout: &Layout, path: &Path, cancel: Option<&CancelToken>) -> Result<Vec<u8>> {
    readonly(cancel, || {
        scan_observation::checkpoint(QueryStage::Receipt, 0, 0)?;
        readonly(cancel, || layout.guard_path(path))?;
        let meta = readonly(cancel, || Ok(fs::symlink_metadata(path)?))?;
        if !meta.is_file() || meta.len() > 32 * 1024 * 1024 {
            bail!("实例回退记录不是受限普通文件");
        }
        let bytes = match cancel {
            Some(cancel) => {
                scan_observation::read_file_controlled(path, QueryStage::Receipt, cancel)?
            }
            None => scan_observation::read_file(path, QueryStage::Receipt)?,
        };
        if bytes.len() as u64 != meta.len() {
            bail!("实例回退记录读取变化");
        }
        Ok(bytes)
    })
}
fn encoded<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn intent_path(layout: &Layout) -> Result<PathBuf> {
    let path = layout
        .root
        .join("state/gui-binding-switch")
        .join(layout.release_dir.file_name().context("release缺失")?)
        .with_extension("json");
    layout.guard_path(&path)?;
    Ok(path)
}
fn saved(
    layout: &Layout,
    intent: &Intent,
    name: &str,
    expected: &Identity,
    cancel: Option<&CancelToken>,
) -> Result<Vec<u8>> {
    readonly(cancel, || {
        let bytes = read(
            layout,
            &layout
                .root
                .join("backups")
                .join(&intent.transaction)
                .join(name),
            cancel,
        )?;
        if identity(&bytes) != *expected {
            bail!("实例回退快照身份不符");
        }
        Ok(bytes)
    })
}
fn history(
    layout: &Layout,
    release: &Release,
    transaction: &str,
    cancel: Option<&CancelToken>,
) -> Result<(Identity, EnvironmentBinding)> {
    readonly(cancel, || {
        let bytes =
            super::gui_rebuild::verified_history_with_cancel(layout, release, transaction, cancel)?;
        let value: Value = decode(&bytes, cancel)?;
        let binding: EnvironmentBinding = readonly(cancel, || {
            Ok(serde_json::from_value(
                value
                    .get("plan")
                    .and_then(|p| p.get("old_binding"))
                    .context("历史缺少old binding")?
                    .clone(),
            )?)
        })?;
        readonly(cancel, || binding.validate())?;
        Ok((identity(&bytes), binding))
    })
}
#[cfg(test)]
pub(crate) fn assert_ready(root: &Path, release: &Release) -> Result<()> {
    assert_ready_with_cancel(root, release, None)
}
pub(crate) fn assert_ready_with_cancel(
    root: &Path,
    release: &Release,
    cancel: Option<&CancelToken>,
) -> Result<()> {
    readonly(cancel, || {
        let layout = Layout::new(root, &release.id)?;
        let path = intent_path(&layout)?;
        if !path.exists() {
            return Ok(());
        }
        let intent: Intent = decode(&read(&layout, &path, cancel)?, cancel)?;
        readonly(cancel, || validate_shape(&layout, release, &intent))?;
        if intent.status != "committed" {
            bail!("GUI实例回退事务{}待恢复", intent.transaction);
        }
        validate_history_authority(&layout, release, &intent, cancel)?;
        Ok(())
    })
}
/// 全根回退门；只有调用者明确给出的合法目标事务可以处于 pending。
#[cfg(test)]
pub(crate) fn assert_all_ready(root: &Path, recovery: Option<(&Release, &str)>) -> Result<()> {
    assert_all_ready_with_cancel(root, recovery, None)
}
pub(crate) fn assert_all_ready_with_cancel(
    root: &Path,
    recovery: Option<(&Release, &str)>,
    cancel: Option<&CancelToken>,
) -> Result<()> {
    readonly(cancel, || {
        let catalog = model::Catalog::embedded()?;
        let scope = Layout::new(
            root,
            &catalog.releases().first().context("发布目录为空")?.id,
        )?;
        let mut matched = false;
        if let Some((_, transaction)) = recovery {
            model::validate_component(transaction)?;
            if !transaction.starts_with("gui-rebuild-rollback-") {
                bail!("实例回退恢复事务类型不符");
            }
        }
        let base = root.join("state/gui-binding-switch");
        scope.guard_path(&base)?;
        if base.exists() {
            for entry in fs::read_dir(&base)? {
                check_control(cancel)?;
                scan_observation::checkpoint(QueryStage::Receipt, 0, 0)?;
                let path = entry?.path();
                scope.guard_path(&path)?;
                if path.extension().is_none_or(|value| value != "json") {
                    bail!("实例回退容器含未知文件");
                }
                let release_id = path
                    .file_stem()
                    .and_then(|v| v.to_str())
                    .context("实例回退文件名无效")?;
                let owner = catalog.release(release_id)?;
                let layout = Layout::new(root, &owner.id)?;
                let intent: Intent = decode(&read(&layout, &path, cancel)?, cancel)?;
                readonly(cancel, || validate_shape(&layout, owner, &intent))?;
                let is_target = recovery.is_some_and(|(release, transaction)| {
                    release.id == owner.id && transaction == intent.transaction
                });
                if is_target {
                    if matched {
                        bail!("实例回退恢复目标不唯一");
                    }
                    validate_semantics(&layout, owner, &intent, cancel)?;
                    matched = true;
                } else if intent.status != "committed" {
                    bail!("GUI实例回退事务{}待恢复", intent.transaction);
                } else {
                    validate_history_authority(&layout, owner, &intent, cancel)?;
                }
            }
        }
        if recovery.is_some() && !matched {
            bail!("实例回退恢复事务ID或发布版本不符");
        }
        Ok(())
    })
}

#[cfg(test)]
pub(crate) fn pending(root: &Path, release: &Release) -> Result<Option<Value>> {
    pending_with_cancel(root, release, None)
}
pub(crate) fn pending_with_cancel(
    root: &Path,
    release: &Release,
    cancel: Option<&CancelToken>,
) -> Result<Option<Value>> {
    readonly(cancel, || {
        let layout = Layout::new(root, &release.id)?;
        let path = intent_path(&layout)?;
        if !path.exists() {
            return Ok(None);
        }
        let intent: Intent = decode(&read(&layout, &path, cancel)?, cancel)?;
        readonly(cancel, || validate_shape(&layout, release, &intent))?;
        Ok((intent.status != "committed").then(
        || json!({"kind":"binding_switch","transaction":intent.transaction,"status":intent.status}),
    ))
    })
}
fn plan(
    root: &Path,
    release: &Release,
    history_transaction: &str,
    cancel: &CancelToken,
) -> Result<Plan> {
    readonly(Some(cancel), || {
        let layout = Layout::new(root, &release.id)?;
        assert_ready_with_cancel(root, release, Some(cancel))?;
        super::gui_rebuild::assert_ready_with_cancel(root, release, Some(cancel))?;
        readonly(Some(cancel), || {
            Registry::load(root)?.assert_base_python_ready()
        })?;
        let (history_identity, target_binding) =
            history(&layout, release, history_transaction, Some(cancel))?;
        let registry = readonly(Some(cancel), || Registry::load(root))?;
        let current_binding = registry
            .gui_binding(&release.id)
            .context("缺少当前GUI绑定")?
            .clone();
        if target_binding == current_binding {
            bail!("目标已是当前绑定");
        }
        let state = instances::load_controlled(&layout, &target_binding.instance_id, cancel)?;
        instances::assert_usable_controlled(&state, cancel)?;
        if state.release_id() != release.id
            || state.storage_version() != target_binding.storage_version
            || state.recipe_id() != target_binding.recipe_id
            || state.recipe_sha256() != target_binding.recipe_sha256
            || state.generation() != target_binding.generation
        {
            bail!("历史实例已改变generation/配方，不能追认旧健康");
        }
        crate::source_integrity::verify_controlled(&layout, release, cancel)?;
        crate::python_integrity::verify_controlled(&layout, cancel)?;
        let proof = gui_registration_integrity::verify(
            &layout,
            release,
            &instances::path(&state)?,
            cancel,
        )?;
        Ok(Plan {
            schema_version: 1,
            root_absolute: root.to_path_buf(),
            release_id: release.id.clone(),
            history_transaction: history_transaction.into(),
            history_identity,
            old_registry: identity(&read(
                &layout,
                &root.join("state/registry.json"),
                Some(cancel),
            )?),
            current_binding,
            target_binding: target_binding.clone(),
            target_state: identity(&read(
                &layout,
                &root
                    .join("state/instances")
                    .join(format!("{}.json", target_binding.instance_id)),
                Some(cancel),
            )?),
            proof,
        })
    })
}
pub(crate) fn preview(root: &Path, release: &Release, history_transaction: &str) -> Result<Value> {
    match plan(root, release, history_transaction, &CancelToken::new()) {
        Ok(plan) => Ok(
            json!({"status":"ready","plan_sha256":hash(&serde_json::to_vec(&plan)?),"plan":plan,"network_bytes":0}),
        ),
        Err(error) => {
            check_control(None)?;
            Ok(json!({"status":"blocked","reason":format!("{error:#}"),"network_bytes":0}))
        }
    }
}
fn validate_shape(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    model::validate_component(&intent.transaction)?;
    if intent.schema_version != 1
        || !intent.transaction.starts_with("gui-rebuild-rollback-")
        || intent.root_absolute != layout.root
        || intent.release_id != release.id
        || intent.plan.schema_version != 1
        || intent.plan.root_absolute != layout.root
        || intent.plan.release_id != release.id
        || intent.plan_sha256 != hash(&serde_json::to_vec(&intent.plan)?)
        || !matches!(intent.status.as_str(), "committing" | "committed")
    {
        bail!("实例回退intent身份/schema无效");
    }
    Ok(())
}
/// 历史授权只校验原始计划、history及备份，不要求当前绑定仍停在历史二态。
fn validate_history_authority(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    cancel: Option<&CancelToken>,
) -> Result<(Registry, Vec<u8>)> {
    readonly(cancel, || {
        readonly(cancel, || validate_shape(layout, release, intent))?;
        let plan = &intent.plan;
        plan.current_binding.validate()?;
        plan.target_binding.validate()?;
        let (history_identity, target) =
            history(layout, release, &plan.history_transaction, cancel)?;
        if history_identity != plan.history_identity || target != plan.target_binding {
            bail!("实例回退历史身份变化");
        }
        let old: Registry = decode(
            &saved(
                layout,
                intent,
                "registry-old.json",
                &plan.old_registry,
                cancel,
            )?,
            cancel,
        )?;
        readonly(cancel, || old.validate())?;
        old.assert_base_python_ready()?;
        if old.gui_binding(&release.id) != Some(&plan.current_binding) {
            bail!("实例回退旧binding与快照不符");
        }
        if plan.proof.environment
            != model::environment_path(
                &layout.root,
                &release.id,
                &target.instance_id,
                target.storage_version,
            )?
            || plan.proof.recipe_sha256 != target.recipe_sha256
            || plan.proof.trusted_index_sha256 != gui_registration_integrity::trusted_index_sha256()
        {
            bail!("实例回退历史证明与目标身份不符");
        }
        let desired_bytes = saved(
            layout,
            intent,
            "registry-new.json",
            &intent.new_registry,
            cancel,
        )?;
        let desired: Registry = decode(&desired_bytes, cancel)?;
        readonly(cancel, || desired.validate())?;
        let mut expected = old;
        expected.bind_gui(&release.id, target)?;
        if desired != expected {
            bail!("实例回退不能修改健康/其它registry字段");
        }
        Ok((desired, desired_bytes))
    })
}
fn validate_semantics(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    cancel: Option<&CancelToken>,
) -> Result<(Registry, Vec<u8>, instances::InstanceState)> {
    readonly(cancel, || {
        readonly(cancel, || validate_shape(layout, release, intent))?;
        if intent.status == "committed"
            && identity(&read(
                layout,
                &layout.root.join("state/registry.json"),
                cancel,
            )?) != intent.new_registry
        {
            bail!("实例回退终态与当前 registry 不一致");
        }
        let (desired, desired_bytes) = validate_history_authority(layout, release, intent, cancel)?;
        let plan = &intent.plan;
        let target = &plan.target_binding;
        let state = match cancel {
            Some(cancel) => instances::load_controlled(layout, &target.instance_id, cancel)?,
            None => instances::load(layout, &target.instance_id)?,
        };
        if state.dirty()
            || state.release_id() != release.id
            || state.generation() != target.generation
            || state.storage_version() != target.storage_version
            || state.recipe_id() != target.recipe_id
            || state.recipe_sha256() != target.recipe_sha256
            || instances::path(&state)? != plan.proof.environment
        {
            bail!("实例回退候选不匹配已证明的历史clean实例");
        }
        if identity(&read(
            layout,
            &layout
                .root
                .join("state/instances")
                .join(format!("{}.json", state.id())),
            cancel,
        )?) != plan.target_state
        {
            bail!("实例回退目标state变化");
        }
        let current = identity(&read(
            layout,
            &layout.root.join("state/registry.json"),
            cancel,
        )?);
        if current != plan.old_registry && current != intent.new_registry {
            bail!("实例回退registry处于未知第三状态");
        }
        Ok((desired, desired_bytes, state))
    })
}
pub(crate) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    history_transaction: &str,
    expected: &str,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    check_control(Some(cancel))?;
    let layout = ctx.layout();
    let plan = plan(&layout.root, release, history_transaction, cancel)?;
    let plan_sha256 = hash(&serde_json::to_vec(&plan)?);
    if plan_sha256 != expected {
        bail!("实例回退预览已变化");
    }
    let transaction = format!(
        "gui-rebuild-rollback-{}-{}-{}",
        model::now(),
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let state = instances::load_controlled(layout, &plan.target_binding.instance_id, cancel)?;
    instances::registration_revalidate(layout, &state, false, cancel, |environment| {
        let proof = gui_registration_integrity::verify(layout, release, environment, cancel)?;
        if proof != plan.proof {
            bail!("实例回退目标闭包变化");
        }
        validator(environment)?;
        entry_probe(environment, &transaction)
    })?;
    let old_bytes = read(
        layout,
        &layout.root.join("state/registry.json"),
        Some(cancel),
    )?;
    if identity(&old_bytes) != plan.old_registry {
        bail!("实例回退验证期间registry变化");
    }
    let mut registry: Registry = decode(&old_bytes, Some(cancel))?;
    registry.bind_gui(&release.id, plan.target_binding.clone())?;
    let new_bytes = encoded(&registry)?;
    for (name, bytes) in [
        ("registry-old.json", old_bytes.as_slice()),
        ("registry-new.json", new_bytes.as_slice()),
    ] {
        model::write_gui_transaction_bytes(
            &layout.root,
            &transaction,
            &layout.root.join("backups").join(&transaction).join(name),
            bytes,
        )?;
    }
    let intent = Intent {
        schema_version: 1,
        root_absolute: layout.root.clone(),
        release_id: release.id.clone(),
        transaction,
        status: "committing".into(),
        plan,
        plan_sha256,
        new_registry: identity(&new_bytes),
    };
    model::write_gui_transaction_json(
        &layout.root,
        &intent.transaction,
        &intent_path(layout)?,
        &intent,
    )?;
    finish(ctx, release, intent, cancel, validator, entry_probe)
}
fn finish(
    ctx: &WorkspaceMutation,
    release: &Release,
    intent: Intent,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let layout = ctx.layout();
    let (_, _, state) = validate_semantics(layout, release, &intent, Some(cancel))?;
    crate::source_integrity::verify_controlled(layout, release, cancel)?;
    crate::python_integrity::verify_controlled(layout, cancel)?;
    let proof =
        gui_registration_integrity::verify(layout, release, &instances::path(&state)?, cancel)?;
    if proof != intent.plan.proof {
        bail!("实例回退证明变化");
    }
    instances::registration_revalidate(layout, &state, false, cancel, |environment| {
        validator(environment)?;
        entry_probe(environment, &intent.transaction)
    })?;
    commit_validated_binding(layout, release, intent, cancel)
}

// 前面的独立可信闭包与运行探针不可省略；本函数收口门前保护和短原子写入。
fn commit_validated_binding(
    layout: &Layout,
    release: &Release,
    mut intent: Intent,
    cancel: &CancelToken,
) -> Result<Value> {
    let (_, bytes, state) = validate_semantics(layout, release, &intent, Some(cancel))?;
    // 完整字节保护在仍可取消的门前完成；绑定切换不会修改实例state或generation。
    instances::assert_usable_controlled(&state, cancel)?;
    validate_semantics(layout, release, &intent, Some(cancel))?;
    // 完整复验与语义检查仍可取消；最终写入门和取消请求共享同一个CAS状态。
    cancel.enter_commit()?;
    model::write_gui_transaction_bytes(
        &layout.root,
        &intent.transaction,
        &layout.root.join("state/registry.json"),
        &bytes,
    )?;
    intent.status = "committed".into();
    model::write_gui_transaction_json(
        &layout.root,
        &intent.transaction,
        &intent_path(layout)?,
        &intent,
    )?;
    Ok(
        json!({"status":"rolled_back","transaction":intent.transaction,"binding":intent.plan.target_binding,"network_bytes":0,"current_changed":false,"healthy_inherited":false}),
    )
}
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    transaction: &str,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    check_control(Some(cancel))?;
    let intent: Intent = decode(
        &read(ctx.layout(), &intent_path(ctx.layout())?, Some(cancel))?,
        Some(cancel),
    )?;
    if intent.transaction != transaction {
        bail!("实例回退恢复事务ID不符");
    }
    validate_semantics(ctx.layout(), release, &intent, Some(cancel))?;
    if intent.status == "committed" {
        return Ok(
            json!({"status":"rolled_back","transaction":intent.transaction,"network_bytes":0}),
        );
    }
    finish(ctx, release, intent, cancel, validator, entry_probe)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn binding_read_cancellation_precedes_invalid_records_without_leaking_to_fresh_reads() {
        let release = model::Catalog::embedded().unwrap().releases[0].clone();
        let root = std::env::temp_dir().join(format!(
            "nt-binding-read-cancel-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        let layout = ctx.layout();
        Registry::default().store(&root).unwrap();
        let registry_before = fs::read(root.join("state/registry.json")).unwrap();
        let path = intent_path(layout).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        let original = b"invalid intent kept for diagnosis";
        fs::write(&path, original).unwrap();
        let cancel = CancelToken::new();
        assert_eq!(cancel.request(), crate::operations::CancelReceipt::Accepted);
        for error in [
            read(layout, &path, Some(&cancel)).unwrap_err(),
            read(layout, &root.join("missing-record.json"), Some(&cancel)).unwrap_err(),
            decode::<Intent>(original, Some(&cancel)).unwrap_err(),
            assert_ready_with_cancel(&root, &release, Some(&cancel)).unwrap_err(),
            assert_all_ready_with_cancel(&root, None, Some(&cancel)).unwrap_err(),
            pending_with_cancel(&root, &release, Some(&cancel)).unwrap_err(),
            plan(&root, &release, "missing-history", &cancel).unwrap_err(),
            recover(
                &ctx,
                &release,
                "gui-rebuild-rollback-missing",
                &cancel,
                |_| panic!("预取消不得进入runtime验证"),
                |_, _| panic!("预取消不得执行入口探测"),
            )
            .unwrap_err(),
        ] {
            assert!(error
                .downcast_ref::<crate::operations::Cancelled>()
                .is_some());
        }
        assert_eq!(read(layout, &path, None).unwrap(), original);
        assert_eq!(
            read(layout, &path, Some(&CancelToken::new())).unwrap(),
            original
        );
        // 普通wrapper仍报告原始坏记录，不继承先前Operation的取消状态。
        for error in [
            assert_ready(&root, &release).unwrap_err(),
            assert_all_ready(&root, None).unwrap_err(),
            pending(&root, &release).unwrap_err(),
        ] {
            assert!(error
                .downcast_ref::<crate::operations::Cancelled>()
                .is_none());
        }
        assert_eq!(fs::read(&path).unwrap(), original);
        assert_eq!(
            fs::read(root.join("state/registry.json")).unwrap(),
            registry_before
        );
        // 保留独占小夹具中的原始坏记录和registry，供统一执行合同后核对。
    }

    #[test]
    fn binding_readonly_stop_after_work_overrides_work_error_without_ambient_token() {
        let cancel = CancelToken::new();
        let error = readonly::<()>(Some(&cancel), || {
            assert_eq!(cancel.request(), crate::operations::CancelReceipt::Accepted);
            bail!("原始语义错误不能覆盖权威取消");
        })
        .unwrap_err();
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        assert_eq!(readonly(None, || Ok(17)).unwrap(), 17);
        assert_eq!(readonly(Some(&CancelToken::new()), || Ok(23)).unwrap(), 23);
        let original = readonly::<()>(None, || bail!("原始语义错误")).unwrap_err();
        assert_eq!(original.to_string(), "原始语义错误");
    }

    #[test]
    fn rollback_commit_plan_requires_exact_history_target_and_two_registry_states() {
        let release = model::Catalog::embedded().unwrap().releases[0].clone();
        let recipe = crate::recipe::GuiRecipe::embedded().unwrap();
        let root = std::env::temp_dir().join(format!(
            "nt-binding-switch-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        let layout = ctx.layout();
        let cancel = CancelToken::new();
        let mut old = Registry {
            schema_version: 2,
            ..Registry::default()
        };
        old.record_installed(&release).unwrap();
        old.store(&root).unwrap();
        let create = |id| {
            let state = instances::create_controlled(
                &ctx,
                id,
                recipe.id(),
                "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba",
                &cancel,
            )
            .unwrap();
            fs::write(
                instances::path(&state).unwrap().join("contract.bin"),
                b"small real byte scan",
            )
            .unwrap();
            instances::validate_new_controlled(&ctx, &state, &[], &cancel, |_| Ok(())).unwrap()
        };
        let target = create("g1111111111111111");
        let binding = |s: &instances::InstanceState| EnvironmentBinding {
            instance_id: s.id().into(),
            storage_version: s.storage_version(),
            recipe_id: s.recipe_id().into(),
            recipe_sha256: s.recipe_sha256().into(),
            generation: s.generation(),
        };
        old.bind_gui(&release.id, binding(&target)).unwrap();
        old.store(&root).unwrap();
        let boundary = instances::rebuild_observe_boundary(layout, &cancel).unwrap();
        let candidate = create("g2222222222222222");
        let mut current = old.clone();
        current.record_installed(&release).unwrap();
        current.bind_gui(&release.id, binding(&candidate)).unwrap();
        current.store(&root).unwrap();
        let history_tx = "gui-rebuild-switch-history-fixture";
        let old_bytes = encoded(&old).unwrap();
        let current_bytes = encoded(&current).unwrap();
        let boundary_sha = instances::rebuild_boundary_sha(&boundary).unwrap();
        #[derive(Serialize)]
        struct HistoryPlan {
            schema_version: u32,
            root_absolute: PathBuf,
            release_id: String,
            registry: Identity,
            boundary_sha256: String,
            old_binding: Option<EnvironmentBinding>,
            missing_wheels: Vec<String>,
            estimated_network_bytes: u64,
        }
        let rebuild_plan = HistoryPlan {
            schema_version: 1,
            root_absolute: root.clone(),
            release_id: release.id.clone(),
            registry: identity(&old_bytes),
            boundary_sha256: boundary_sha.clone(),
            old_binding: Some(binding(&target)),
            missing_wheels: vec![],
            estimated_network_bytes: 0,
        };
        let proof = |environment| TrustedEnvironment {
            environment,
            recipe_sha256: target.recipe_sha256().into(),
            trusted_index_sha256: gui_registration_integrity::trusted_index_sha256().into(),
            files: 0,
            bytes: 0,
            closure_sha256: "a".repeat(64),
        };
        let history = json!({"schema_version":1,"transaction":history_tx,"root_absolute":root,"release_id":release.id,"candidate_id":candidate.id(),"status":"committed","plan_sha256":hash(&serde_json::to_vec(&rebuild_plan).unwrap()),"plan":rebuild_plan,"boundary_sha256":boundary_sha,"old_registry":identity(&old_bytes),"candidate_state":null,"candidate_tree_sha256":null,"proof":proof(instances::path(&candidate).unwrap()),"new_registry":identity(&current_bytes),"preservation_file":null,"preservation_sha256":null,"terminal_status":"committed","failure":null});
        for (name, bytes) in [
            ("registry-old.json", old_bytes),
            ("registry-new.json", current_bytes.clone()),
            ("boundary.json", encoded(&boundary).unwrap()),
        ] {
            model::write_gui_transaction_bytes(
                &root,
                history_tx,
                &root.join("backups").join(history_tx).join(name),
                &bytes,
            )
            .unwrap();
        }
        model::write_gui_transaction_json(
            &root,
            history_tx,
            &root
                .join("state/gui-rebuild")
                .join(format!("{history_tx}.json")),
            &history,
        )
        .unwrap();
        let history_bytes =
            super::super::gui_rebuild::verified_history(layout, &release, history_tx).unwrap();
        let mut desired = current.clone();
        desired.bind_gui(&release.id, binding(&target)).unwrap();
        let desired_bytes = encoded(&desired).unwrap();
        let plan = Plan {
            schema_version: 1,
            root_absolute: root.clone(),
            release_id: release.id.clone(),
            history_transaction: history_tx.into(),
            history_identity: identity(&history_bytes),
            old_registry: identity(&current_bytes),
            current_binding: binding(&candidate),
            target_binding: binding(&target),
            target_state: identity(
                &read(
                    layout,
                    &root
                        .join("state/instances")
                        .join(format!("{}.json", target.id())),
                    None,
                )
                .unwrap(),
            ),
            proof: proof(instances::path(&target).unwrap()),
        };
        let tx = "gui-rebuild-rollback-closure-fixture";
        for (name, bytes) in [
            ("registry-old.json", current_bytes.clone()),
            ("registry-new.json", desired_bytes.clone()),
        ] {
            model::write_gui_transaction_bytes(
                &root,
                tx,
                &root.join("backups").join(tx).join(name),
                &bytes,
            )
            .unwrap();
        }
        let intent = Intent {
            schema_version: 1,
            root_absolute: root.clone(),
            release_id: release.id.clone(),
            transaction: tx.into(),
            status: "committing".into(),
            plan_sha256: hash(&serde_json::to_vec(&plan).unwrap()),
            plan,
            new_registry: identity(&desired_bytes),
        };
        assert!(validate_semantics(layout, &release, &intent, None).is_ok());
        // 合成proof只验证收口合同；正式生产finish仍先执行独立验证及真实运行探针。
        // 在最后一次真实环境hash中取消，必须仍可接受，不能先进入提交门。
        let cancelled = CancelToken::new();
        let hook_cancel = cancelled.clone();
        let target_file = instances::path(&target).unwrap().join("contract.bin");
        let current_before = fs::read(root.join("state/registry.json")).unwrap();
        let intent_file = intent_path(layout).unwrap();
        let result = crate::instances::reliability_r4_scan_tests::with_read_hook(
            move |path, _| {
                if path == target_file {
                    assert_eq!(
                        hook_cancel.request(),
                        crate::operations::CancelReceipt::Accepted
                    );
                }
            },
            || commit_validated_binding(layout, &release, intent.clone(), &cancelled),
        );
        assert!(result
            .unwrap_err()
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        assert_eq!(
            fs::read(root.join("state/registry.json")).unwrap(),
            current_before
        );
        assert!(!intent_file.exists());
        let commit_cancel = CancelToken::new();
        let committed =
            commit_validated_binding(layout, &release, intent.clone(), &commit_cancel).unwrap();
        assert_eq!(committed["status"], "rolled_back");
        assert_eq!(
            commit_cancel.request(),
            crate::operations::CancelReceipt::CommitInProgress
        );
        assert_eq!(
            fs::read(root.join("state/registry.json")).unwrap(),
            desired_bytes
        );
        // 下面原有授权/第三状态拒绝案从未提交的控制状态继续，避免新增history改变门的目标。
        fs::remove_file(intent_file).unwrap();
        fs::write(root.join("state/registry.json"), &desired_bytes).unwrap();
        assert!(validate_semantics(layout, &release, &intent, None).is_ok());
        let mut third = desired.clone();
        third.current = Some(release.id.clone());
        third.store(&root).unwrap();
        assert!(validate_semantics(layout, &release, &intent, None).is_err());
        // 静态授权允许后续合法 registry 切换；该合成proof仅证明合同，不授健康。
        let mut historical = intent.clone();
        historical.status = "committed".into();
        model::write_gui_transaction_json(&root, tx, &intent_path(layout).unwrap(), &historical)
            .unwrap();
        validate_history_authority(layout, &release, &historical, None).unwrap();
        assert_all_ready(&root, None).unwrap();
        assert!(validate_semantics(layout, &release, &historical, None).is_err());
        let new_backup = root.join("backups").join(tx).join("registry-new.json");
        let saved_new = fs::read(&new_backup).unwrap();
        fs::write(&new_backup, b"corrupt historical backup").unwrap();
        assert!(assert_all_ready(&root, None).is_err());
        drop(ctx);
        let before = fs::read(root.join("state/registry.json")).unwrap();
        let manager = crate::operations::OperationManager::default();
        let operation = manager
            .start(
                "r1-bad-nontarget-terminal",
                crate::operations::OperationKind::Repair,
            )
            .unwrap();
        let mut engine = super::super::Engine::new(root.clone(), std::sync::Arc::new(|_| {}));
        let error = engine
            .gui_lifecycle_operation(
                &root,
                &release.id,
                "recover_preserved",
                None,
                None,
                Some(target.id()),
                &operation,
            )
            .unwrap_err();
        assert!(format!("{error:#}").contains("快照身份不符"));
        assert_eq!(fs::read(root.join("state/registry.json")).unwrap(), before);
        assert!(!root
            .join("state/operations/r1-bad-nontarget-terminal.json")
            .exists());
        fs::write(new_backup, saved_new).unwrap();
        let ctx = WorkspaceMutation::acquire_existing(&root, &release.id).unwrap();
        let layout = ctx.layout();
        fs::write(root.join("state/registry.json"), current_bytes).unwrap();
        let target_path = root
            .join("state/instances")
            .join(format!("{}.json", target.id()));
        let mut stale: Value = serde_json::from_slice(&fs::read(&target_path).unwrap()).unwrap();
        stale["generation"] = 2.into();
        stale["validated_generation"] = 2.into();
        fs::write(target_path, encoded(&stale).unwrap()).unwrap();
        assert!(validate_semantics(layout, &release, &intent, None).is_err());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }
}
