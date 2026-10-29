//! 补登记多记录提交：先完整预检全部old/new状态，再发布任一记录。
use super::{read, saved, stamp, Intent};
use crate::{
    instances,
    model::{self, EnvironmentBinding, Layout, Registry, Release, ReleaseReceipt},
    operations::CancelToken,
};
use anyhow::{bail, Context, Result};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

/// 恢复前绑定所有身份与快照语义，必须在运行任何环境解释器之前调用。
pub(super) fn validate_identity(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    let plan = &intent.plan;
    let candidate = &plan.candidate;
    let recipe = crate::recipe::GuiRecipe::embedded()?;
    if plan.schema_version != 1
        || plan.root_absolute != layout.root
        || plan.release_id != release.id
        || intent.root_absolute != layout.root
        || intent.release_id != release.id
        || plan.proof.recipe_sha256 != super::RECIPE_SHA
        || plan.proof.trusted_index_sha256
            != crate::gui_registration_integrity::trusted_index_sha256()
        || plan.proof.files == 0
        || plan.proof.bytes == 0
    {
        bail!("补登记恢复计划schema或信任根身份无效");
    }
    let environment = model::environment_path(
        &layout.root,
        &release.id,
        &candidate.id,
        candidate.storage_version,
    )?;
    if environment != plan.proof.environment {
        bail!("补登记proof环境与候选路径断联");
    }
    if !matches!(
        (candidate.status.as_str(), candidate.state.is_some()),
        ("clean", true) | ("missing_state", false)
    ) {
        bail!("补登记候选状态合同无效");
    }
    let registry_path = Path::new("state/registry.json");
    let state_path = Path::new("state/instances").join(format!("{}.json", candidate.id));
    let receipt_path = layout
        .release_dir
        .join("release.json")
        .strip_prefix(&layout.root)?
        .to_path_buf();
    let allowed = BTreeSet::from([
        registry_path.to_path_buf(),
        state_path.clone(),
        receipt_path.clone(),
    ]);
    validate(layout, intent, &allowed)?;
    let original_registry =
        if let Some(record) = intent.records.iter().find(|r| r.relative == registry_path) {
            if record.old != plan.registry {
                bail!("registry快照与预览输入断联");
            }
            if let Some(old) = &record.old {
                serde_json::from_slice::<Registry>(&saved(
                    layout,
                    intent,
                    record.old_snapshot.as_ref().context("旧registry快照缺失")?,
                    old,
                )?)?
            } else {
                Registry::default()
            }
        } else {
            let bytes = read(layout, &layout.root.join(registry_path))?;
            if bytes.as_deref().map(stamp) != plan.registry {
                bail!("未改registry与原计划输入不同");
            }
            Registry::load(&layout.root)?
        };
    original_registry.validate()?;
    original_registry.assert_base_python_ready()?;
    if let Some(binding) = original_registry.gui_binding(&release.id) {
        if binding.instance_id != candidate.id
            || binding.storage_version != candidate.storage_version
            || binding.recipe_id != recipe.id
            || binding.recipe_sha256 != super::RECIPE_SHA
            || binding.generation != candidate.generation
        {
            bail!("恢复不能切换或重新解释既有binding");
        }
    } else if candidate.state.is_none() && candidate.generation != 0 {
        bail!("无旧状态或binding不能追认历史generation");
    }
    let candidate_state = if candidate.state.is_none() {
        let record = intent
            .records
            .iter()
            .find(|r| r.relative == state_path)
            .context("缺失state恢复计划未含新state记录")?;
        if record.old.is_some() {
            bail!("补登记禁止覆盖既有state");
        }
        let state = instances::registration_decode(
            layout,
            &saved(layout, intent, &record.new_snapshot, &record.new)?,
        )?;
        instances::registration_assert_origin(
            &state,
            &intent.transaction,
            candidate.generation,
            &plan.proof,
        )?;
        state
    } else {
        if intent.records.iter().any(|r| r.relative == state_path) {
            bail!("补登记禁止改写既有clean state");
        }
        let bytes = read(layout, &layout.root.join(&state_path))?.context("原clean state已丢失")?;
        if Some(stamp(&bytes)) != candidate.state {
            bail!("原clean state身份变化");
        }
        instances::registration_decode(layout, &bytes)?
    };
    if candidate_state.id() != candidate.id
        || candidate_state.storage_version() != candidate.storage_version
        || candidate_state.release_id() != release.id
        || candidate_state.recipe_id() != recipe.id
        || candidate_state.recipe_sha256() != super::RECIPE_SHA
        || instances::path(&candidate_state)? != environment
        || candidate_state.dirty()
        || (candidate.state.is_some() && candidate_state.generation() != candidate.generation)
    {
        bail!("补登记实例状态与proof/配方/epoch断联");
    }
    if let Some(record) = intent.records.iter().find(|r| r.relative == receipt_path) {
        if plan.receipt.is_some() || record.old.is_some() {
            bail!("禁止替换既有receipt");
        }
    } else {
        let bytes = read(layout, &layout.root.join(&receipt_path))?;
        if bytes.as_deref().map(stamp) != plan.receipt || plan.receipt.is_none() {
            bail!("receipt恢复计划缺项或输入变化");
        }
        let receipt: ReleaseReceipt =
            serde_json::from_slice(bytes.as_deref().context("receipt缺失")?)?;
        validate_receipt(&receipt, release)?;
    }
    validate_semantics(layout, release, intent, &candidate_state)
}
fn validate_receipt(receipt: &ReleaseReceipt, release: &Release) -> Result<()> {
    if receipt.schema_version != model::SCHEMA_VERSION || receipt.release != *release {
        bail!("登记receipt schema或发布身份不符");
    }
    receipt.release.validate()
}

pub(super) fn validate(
    layout: &Layout,
    intent: &Intent,
    allowed: &BTreeSet<PathBuf>,
) -> Result<()> {
    let mut seen = BTreeSet::new();
    for record in &intent.records {
        if !allowed.contains(&record.relative) || !seen.insert(&record.relative) {
            bail!("登记事务出现未知或重复目标");
        }
        let current = read(layout, &layout.root.join(&record.relative))?
            .as_deref()
            .map(stamp);
        if current != record.old && current != Some(record.new.clone()) {
            bail!("登记目标处于未知第三状态，保留旧记录/事务");
        }
        if let Some(expected) = &record.old {
            saved(
                layout,
                intent,
                record.old_snapshot.as_ref().context("缺少old快照")?,
                expected,
            )?;
        }
        saved(layout, intent, &record.new_snapshot, &record.new)?;
    }
    Ok(())
}
pub(super) fn validate_semantics(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    state: &instances::InstanceState,
) -> Result<()> {
    let registry_record = intent
        .records
        .iter()
        .find(|r| r.relative == Path::new("state/registry.json"));
    if let Some(record) = registry_record {
        let mut expected_registry: Registry = if let Some(old) = &record.old {
            serde_json::from_slice(&saved(
                layout,
                intent,
                record.old_snapshot.as_ref().context("registry旧快照缺失")?,
                old,
            )?)?
        } else {
            Registry::default()
        };
        expected_registry.validate()?;
        expected_registry.assert_base_python_ready()?;
        if record.old != intent.plan.registry {
            bail!("registry旧状态不匹配预览输入");
        }
        expected_registry.schema_version = expected_registry.schema_version.max(2);
        expected_registry.record_installed(release)?;
        let binding = EnvironmentBinding {
            instance_id: state.id().into(),
            storage_version: state.storage_version(),
            recipe_id: state.recipe_id().into(),
            recipe_sha256: state.recipe_sha256().into(),
            generation: state.generation(),
        };
        if expected_registry.gui_binding(&release.id) != Some(&binding) {
            expected_registry.bind_gui(&release.id, binding)?;
        }
        let desired: Registry =
            serde_json::from_slice(&saved(layout, intent, &record.new_snapshot, &record.new)?)?;
        desired.validate()?;
        if desired != expected_registry {
            bail!("登记intent试图改变未授权registry字段");
        }
    } else {
        let current = Registry::load(&layout.root)?;
        let mut expected = current.clone();
        expected.schema_version = expected.schema_version.max(2);
        expected.record_installed(release)?;
        let binding = EnvironmentBinding {
            instance_id: state.id().into(),
            storage_version: state.storage_version(),
            recipe_id: state.recipe_id().into(),
            recipe_sha256: state.recipe_sha256().into(),
            generation: state.generation(),
        };
        if expected.gui_binding(&release.id) != Some(&binding) {
            expected.bind_gui(&release.id, binding)?;
        }
        if current != expected {
            bail!("登记intent遗漏必要registry提交，禁止部分写入");
        }
    }
    for record in &intent.records {
        if record.relative
            == layout
                .release_dir
                .join("release.json")
                .strip_prefix(&layout.root)?
        {
            if record.old.is_some() || intent.plan.receipt.is_some() {
                bail!("补登记禁止替换既有receipt");
            }
            let receipt: ReleaseReceipt =
                serde_json::from_slice(&saved(layout, intent, &record.new_snapshot, &record.new)?)?;
            validate_receipt(&receipt, release)?;
        }
    }
    Ok(())
}
pub(super) fn commit(
    layout: &Layout,
    intent: &Intent,
    allowed: &BTreeSet<PathBuf>,
    cancel: &CancelToken,
) -> Result<()> {
    validate(layout, intent, allowed)?;
    for record in &intent.records {
        cancel.check()?;
        let target = layout.root.join(&record.relative);
        let current = read(layout, &target)?.as_deref().map(stamp);
        if current == Some(record.new.clone()) {
            continue;
        }
        if current != record.old {
            bail!("登记目标提交前变化");
        }
        model::write_gui_transaction_bytes(
            &layout.root,
            &intent.transaction,
            &target,
            &saved(layout, intent, &record.new_snapshot, &record.new)?,
        )?;
    }
    Ok(())
}

#[cfg(test)]
#[path = "gui_registration_records_tests.rs"]
mod tests;
