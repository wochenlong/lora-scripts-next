//! 同一release的显式实例回退；历史由已提交重建intent证明，仅复验clean旧实例后0B切回。
use crate::{
    gui_registration_integrity::{self, TrustedEnvironment},
    instances,
    model::{self, EnvironmentBinding, Layout, Registry, Release, WorkspaceMutation},
    operations::CancelToken,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
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
fn read(layout: &Layout, path: &Path) -> Result<Vec<u8>> {
    layout.guard_path(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > 32 * 1024 * 1024 {
        bail!("实例回退记录不是受限普通文件");
    }
    let bytes = fs::read(path)?;
    if bytes.len() as u64 != meta.len() {
        bail!("实例回退记录读取变化");
    }
    Ok(bytes)
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
fn saved(layout: &Layout, intent: &Intent, name: &str, expected: &Identity) -> Result<Vec<u8>> {
    let bytes = read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join(name),
    )?;
    if identity(&bytes) != *expected {
        bail!("实例回退快照身份不符");
    }
    Ok(bytes)
}
fn history(
    layout: &Layout,
    release: &Release,
    transaction: &str,
) -> Result<(Identity, EnvironmentBinding)> {
    let bytes = super::gui_rebuild::verified_history(layout, release, transaction)?;
    let value: Value = serde_json::from_slice(&bytes)?;
    let binding: EnvironmentBinding = serde_json::from_value(
        value
            .get("plan")
            .and_then(|p| p.get("old_binding"))
            .context("历史缺少old binding")?
            .clone(),
    )?;
    binding.validate()?;
    Ok((identity(&bytes), binding))
}
pub(crate) fn assert_ready(root: &Path, release: &Release) -> Result<()> {
    let layout = Layout::new(root, &release.id)?;
    let path = intent_path(&layout)?;
    if !path.exists() {
        return Ok(());
    }
    let intent: Intent = serde_json::from_slice(&read(&layout, &path)?)?;
    validate_shape(&layout, release, &intent)?;
    if intent.status != "committed" {
        bail!("GUI实例回退事务{}待恢复", intent.transaction);
    }
    Ok(())
}
pub(crate) fn pending(root: &Path, release: &Release) -> Result<Option<Value>> {
    let layout = Layout::new(root, &release.id)?;
    let path = intent_path(&layout)?;
    if !path.exists() {
        return Ok(None);
    }
    let intent: Intent = serde_json::from_slice(&read(&layout, &path)?)?;
    validate_shape(&layout, release, &intent)?;
    Ok((intent.status != "committed").then(
        || json!({"kind":"binding_switch","transaction":intent.transaction,"status":intent.status}),
    ))
}
fn plan(
    root: &Path,
    release: &Release,
    history_transaction: &str,
    cancel: &CancelToken,
) -> Result<Plan> {
    let layout = Layout::new(root, &release.id)?;
    assert_ready(root, release)?;
    super::gui_rebuild::assert_ready(root, release)?;
    Registry::load(root)?.assert_base_python_ready()?;
    let (history_identity, target_binding) = history(&layout, release, history_transaction)?;
    let registry = Registry::load(root)?;
    let current_binding = registry
        .gui_binding(&release.id)
        .context("缺少当前GUI绑定")?
        .clone();
    if target_binding == current_binding {
        bail!("目标已是当前绑定");
    }
    let state = instances::load(&layout, &target_binding.instance_id)?;
    instances::assert_usable(&state)?;
    if state.release_id() != release.id
        || state.storage_version() != target_binding.storage_version
        || state.recipe_id() != target_binding.recipe_id
        || state.recipe_sha256() != target_binding.recipe_sha256
        || state.generation() != target_binding.generation
    {
        bail!("历史实例已改变generation/配方，不能追认旧健康");
    }
    crate::source_integrity::verify(&layout, release)?;
    crate::python_integrity::verify(&layout)?;
    let proof =
        gui_registration_integrity::verify(&layout, release, &instances::path(&state)?, cancel)?;
    Ok(Plan {
        schema_version: 1,
        root_absolute: root.to_path_buf(),
        release_id: release.id.clone(),
        history_transaction: history_transaction.into(),
        history_identity,
        old_registry: identity(&read(&layout, &root.join("state/registry.json"))?),
        current_binding,
        target_binding: target_binding.clone(),
        target_state: identity(&read(
            &layout,
            &root
                .join("state/instances")
                .join(format!("{}.json", target_binding.instance_id)),
        )?),
        proof,
    })
}
pub(crate) fn preview(root: &Path, release: &Release, history_transaction: &str) -> Result<Value> {
    match plan(root, release, history_transaction, &CancelToken::new()) {
        Ok(plan) => Ok(
            json!({"status":"ready","plan_sha256":hash(&serde_json::to_vec(&plan)?),"plan":plan,"network_bytes":0}),
        ),
        Err(error) => {
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
fn validate_semantics(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
) -> Result<(Registry, Vec<u8>, instances::InstanceState)> {
    validate_shape(layout, release, intent)?;
    let plan = &intent.plan;
    let (history_identity, target) = history(layout, release, &plan.history_transaction)?;
    if history_identity != plan.history_identity || target != plan.target_binding {
        bail!("实例回退历史身份变化");
    }
    let old: Registry = serde_json::from_slice(&saved(
        layout,
        intent,
        "registry-old.json",
        &plan.old_registry,
    )?)?;
    old.validate()?;
    old.assert_base_python_ready()?;
    if old.gui_binding(&release.id) != Some(&plan.current_binding) {
        bail!("实例回退旧binding与快照不符");
    }
    let state = instances::load(layout, &target.instance_id)?;
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
    )?) != plan.target_state
    {
        bail!("实例回退目标state变化");
    }
    let desired_bytes = saved(layout, intent, "registry-new.json", &intent.new_registry)?;
    let desired: Registry = serde_json::from_slice(&desired_bytes)?;
    desired.validate()?;
    let mut expected = old;
    expected.bind_gui(&release.id, target)?;
    if desired != expected {
        bail!("实例回退不能修改健康/其它registry字段");
    }
    let current = identity(&read(layout, &layout.root.join("state/registry.json"))?);
    if current != plan.old_registry && current != intent.new_registry {
        bail!("实例回退registry处于未知第三状态");
    }
    Ok((desired, desired_bytes, state))
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
    let state = instances::load(layout, &plan.target_binding.instance_id)?;
    instances::registration_revalidate(layout, &state, false, cancel, |environment| {
        let proof = gui_registration_integrity::verify(layout, release, environment, cancel)?;
        if proof != plan.proof {
            bail!("实例回退目标闭包变化");
        }
        validator(environment)?;
        entry_probe(environment, &transaction)
    })?;
    let old_bytes = read(layout, &layout.root.join("state/registry.json"))?;
    if identity(&old_bytes) != plan.old_registry {
        bail!("实例回退验证期间registry变化");
    }
    let mut registry: Registry = serde_json::from_slice(&old_bytes)?;
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
    mut intent: Intent,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let layout = ctx.layout();
    let (_, bytes, state) = validate_semantics(layout, release, &intent)?;
    crate::source_integrity::verify(layout, release)?;
    crate::python_integrity::verify(layout)?;
    let proof =
        gui_registration_integrity::verify(layout, release, &instances::path(&state)?, cancel)?;
    if proof != intent.plan.proof {
        bail!("实例回退证明变化");
    }
    instances::registration_revalidate(layout, &state, false, cancel, |environment| {
        validator(environment)?;
        entry_probe(environment, &intent.transaction)
    })?;
    validate_semantics(layout, release, &intent)?;
    model::write_gui_transaction_bytes(
        &layout.root,
        &intent.transaction,
        &layout.root.join("state/registry.json"),
        &bytes,
    )?;
    instances::assert_usable(&state)?;
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
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let intent: Intent = serde_json::from_slice(&read(ctx.layout(), &intent_path(ctx.layout())?)?)?;
    validate_shape(ctx.layout(), release, &intent)?;
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
                "8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090",
                &cancel,
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
        assert!(validate_semantics(layout, &release, &intent).is_ok());
        fs::write(root.join("state/registry.json"), &desired_bytes).unwrap();
        assert!(validate_semantics(layout, &release, &intent).is_ok());
        let mut third = desired.clone();
        third.current = Some(release.id.clone());
        third.store(&root).unwrap();
        assert!(validate_semantics(layout, &release, &intent).is_err());
        fs::write(root.join("state/registry.json"), current_bytes).unwrap();
        let target_path = root
            .join("state/instances")
            .join(format!("{}.json", target.id()));
        let mut stale: Value = serde_json::from_slice(&fs::read(&target_path).unwrap()).unwrap();
        stale["generation"] = 2.into();
        stale["validated_generation"] = 2.into();
        fs::write(target_path, encoded(&stale).unwrap()).unwrap();
        assert!(validate_semantics(layout, &release, &intent).is_err());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }
}
