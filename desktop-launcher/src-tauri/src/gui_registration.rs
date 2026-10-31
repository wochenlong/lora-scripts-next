//! 状态补登记：只读独立实体证明后精确提交缺失记录；不下载、不重建、不激活健康指针。
use crate::{
    gui_registration_integrity::{self, TrustedEnvironment},
    instances,
    model::{
        self, EnvironmentBinding, Layout, Registry, Release, ReleaseReceipt, WorkspaceMutation,
    },
    operations::CancelToken,
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
#[path = "gui_registration_records.rs"]
mod records;
static NEXT: AtomicU64 = AtomicU64::new(0);
const RECIPE_SHA: &str = "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba";
const MAX_RECORD: u64 = 32 * 1024 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Stamp {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Candidate {
    id: String,
    storage_version: u32,
    state: Option<Stamp>,
    generation: u64,
    status: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    release_id: String,
    root_absolute: PathBuf,
    registry: Option<Stamp>,
    receipt: Option<Stamp>,
    candidate: Candidate,
    proof: TrustedEnvironment,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    relative: PathBuf,
    old: Option<Stamp>,
    new: Stamp,
    old_snapshot: Option<String>,
    new_snapshot: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    transaction: String,
    release_id: String,
    root_absolute: PathBuf,
    status: String,
    plan: Plan,
    plan_sha256: String,
    records: Vec<Record>,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn stamp(bytes: &[u8]) -> Stamp {
    Stamp {
        bytes: bytes.len() as u64,
        sha256: hash(bytes),
    }
}
fn encoded<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn read(layout: &Layout, path: &Path) -> Result<Option<Vec<u8>>> {
    layout.guard_path(path)?;
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
        Ok(meta) => {
            if !meta.is_file() || meta.len() > MAX_RECORD {
                bail!("登记记录不是受限普通文件");
            }
            let bytes = fs::read(path)?;
            if bytes.len() as u64 != meta.len() {
                bail!("登记记录读取期间变化");
            }
            Ok(Some(bytes))
        }
    }
}
fn intent_path(layout: &Layout) -> Result<PathBuf> {
    let id = layout.release_dir.file_name().context("release缺失")?;
    let path = layout
        .root
        .join("state/gui-registration")
        .join(id)
        .with_extension("json");
    layout.guard_path(&path)?;
    Ok(path)
}
fn load_intent(layout: &Layout) -> Result<Option<Intent>> {
    let Some(bytes) = read(layout, &intent_path(layout)?)? else {
        return Ok(None);
    };
    let intent: Intent = serde_json::from_slice(&bytes)?;
    model::validate_component(&intent.transaction)?;
    if intent.schema_version != 1
        || intent.root_absolute != layout.root
        || intent.release_id
            != layout
                .release_dir
                .file_name()
                .context("release缺失")?
                .to_string_lossy()
        || !intent.transaction.starts_with("gui-registration-")
        || !matches!(intent.status.as_str(), "committing" | "committed")
        || intent.plan_sha256 != hash(&serde_json::to_vec(&intent.plan)?)
        || intent.records.len() > 3
        || intent.records.is_empty()
    {
        bail!("登记事务身份无效，保留原记录");
    }
    Ok(Some(intent))
}
pub(crate) fn assert_ready(root: &Path, release: &Release) -> Result<()> {
    let layout = Layout::new(root, &release.id)?;
    if let Some(intent) = load_intent(&layout)? {
        if intent.status != "committed" {
            bail!(
                "GUI补登记事务{}待恢复，禁止其它目标写入/启动",
                intent.transaction
            );
        }
    }
    Ok(())
}

fn candidates(layout: &Layout, release: &Release) -> Result<Vec<Candidate>> {
    let mut ids = BTreeSet::new();
    let mut result = Vec::new();
    let state_root = layout.root.join("state/instances");
    layout.guard_path(&state_root)?;
    if state_root.exists() {
        for entry in fs::read_dir(&state_root)? {
            let path = entry?.path();
            layout.guard_path(&path)?;
            if path.extension().is_none_or(|e| e != "json") {
                bail!("实例状态目录含未知文件，先保留诊断");
            }
            let id = path
                .file_stem()
                .and_then(|s| s.to_str())
                .context("实例状态名非UTF8")?;
            let bytes = read(layout, &path)?.context("实例状态消失")?;
            // 其它发布记录也必须可解析，不能默默忽略损坏状态。
            let value: Value = serde_json::from_slice(&bytes)?;
            let owner = value
                .get("release_id")
                .and_then(Value::as_str)
                .context("实例状态缺少release")?;
            if owner != release.id {
                continue;
            }
            let state = instances::load(layout, id)?;
            ids.insert((id.to_owned(), state.storage_version()));
            result.push(Candidate {
                id: id.into(),
                storage_version: state.storage_version(),
                state: Some(stamp(&bytes)),
                generation: state.generation(),
                status: if state.dirty() {
                    "dirty_or_pending"
                } else if instances::assert_usable(&state).is_ok() {
                    "clean"
                } else {
                    "stale_or_damaged"
                }
                .into(),
            });
        }
    }
    let compact = layout.root.join("e");
    layout.guard_path(&compact)?;
    if compact.exists() {
        for entry in fs::read_dir(&compact)? {
            let path = entry?.path();
            layout.guard_path(&path)?;
            let id = path
                .file_name()
                .and_then(|s| s.to_str())
                .context("实例名非UTF8")?;
            model::validate_environment_storage(id, 1)?;
            if !fs::symlink_metadata(&path)?.is_dir() {
                bail!("短路径实例容器含未知文件");
            }
            if !ids.contains(&(id.to_owned(), 1)) {
                // 有其它release状态或绑定的目录绝不能收养。
                let state_path = state_root.join(format!("{id}.json"));
                if state_path.exists() {
                    continue;
                }
                let registry = Registry::load(&layout.root)?;
                if registry.installed.iter().any(|i| {
                    i.release_id != release.id
                        && i.gui.as_ref().is_some_and(|b| b.instance_id == id)
                }) {
                    continue;
                }
                result.push(Candidate {
                    id: id.into(),
                    storage_version: 1,
                    state: None,
                    generation: registry
                        .gui_binding(&release.id)
                        .filter(|b| b.instance_id == id)
                        .map_or(0, |b| b.generation),
                    status: "missing_state".into(),
                });
            }
        }
    }
    let legacy = layout
        .root
        .join("environments")
        .join(&release.id)
        .join("instances");
    layout.guard_path(&legacy)?;
    if legacy.exists() {
        for entry in fs::read_dir(&legacy)? {
            let path = entry?.path();
            layout.guard_path(&path)?;
            let id = path
                .file_name()
                .and_then(|s| s.to_str())
                .context("旧实例名非UTF8")?;
            model::validate_environment_storage(id, 0)?;
            if !ids.contains(&(id.to_owned(), 0))
                && path.join("gui").is_dir()
                && !state_root.join(format!("{id}.json")).exists()
            {
                let generation = Registry::load(&layout.root)?
                    .gui_binding(&release.id)
                    .filter(|b| b.instance_id == id)
                    .map_or(0, |b| b.generation);
                result.push(Candidate {
                    id: id.into(),
                    storage_version: 0,
                    state: None,
                    generation,
                    status: "missing_state".into(),
                });
            }
        }
    }
    result.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(result)
}
fn plan(
    root: &Path,
    release: &Release,
    requested: Option<&str>,
    cancel: &CancelToken,
) -> Result<(Plan, Vec<Candidate>)> {
    let layout = Layout::new(root, &release.id)?;
    assert_ready(root, release)?;
    Registry::load(root)?.assert_base_python_ready()?;
    let registry = Registry::load(root)?;
    let recipe = GuiRecipe::embedded()?;
    if registry.gui_binding(&release.id).is_some_and(|binding| {
        binding.recipe_id != recipe.id || binding.recipe_sha256 != RECIPE_SHA
    }) {
        bail!("既有GUI binding配方身份不符，不重新解释");
    }
    if release.commit != recipe.source_commit
        || !recipe.matches_environment_recipe(&release.environment_recipe)
    {
        bail!("发布不匹配固定GUI配方");
    }
    let candidates = candidates(&layout, release)?;
    let selected = requested.map(str::to_owned).or_else(|| {
        registry
            .gui_binding(&release.id)
            .map(|b| b.instance_id.clone())
    });
    let candidate = if let Some(id) = selected {
        let matches: Vec<_> = candidates.iter().filter(|c| c.id == id).collect();
        if matches.len() != 1 {
            bail!("选定实例不存在或同ID跨存储命名空间歧义");
        }
        matches[0].clone()
    } else if candidates.len() == 1 {
        candidates[0].clone()
    } else {
        bail!("实例候选为{}个，请显式选择；不能猜测", candidates.len());
    };
    if !matches!(candidate.status.as_str(), "clean" | "missing_state") {
        bail!("选定实例{}，不能补登记", candidate.status);
    }
    if let Some(binding) = registry.gui_binding(&release.id) {
        if binding.instance_id != candidate.id
            || binding.storage_version != candidate.storage_version
        {
            bail!("补登记不切换既有绑定，请使用显式重建/回退");
        }
        if candidate.state.is_some() && binding.generation != candidate.generation {
            bail!("既有binding generation与实例不符，不覆盖不一致记录");
        }
    }
    let receipt = read(&layout, &layout.release_dir.join("release.json"))?;
    if receipt.is_some() && ReleaseReceipt::load(&layout.release_dir)?.release != *release {
        bail!("既有receipt身份不符，不覆盖");
    }
    crate::source_integrity::verify(&layout, release)?;
    crate::python_integrity::verify(&layout)?;
    let environment =
        model::environment_path(root, &release.id, &candidate.id, candidate.storage_version)?;
    let proof = gui_registration_integrity::verify(&layout, release, &environment, cancel)?;
    let plan = Plan {
        schema_version: 1,
        release_id: release.id.clone(),
        root_absolute: root.to_path_buf(),
        registry: read(&layout, &root.join("state/registry.json"))?
            .as_deref()
            .map(stamp),
        receipt: receipt.as_deref().map(stamp),
        candidate,
        proof,
    };
    Ok((plan, candidates))
}
pub(crate) fn preview(root: &Path, release: &Release, requested: Option<&str>) -> Result<Value> {
    let layout = Layout::new(root, &release.id)?;
    if let Some(intent) = load_intent(&layout)? {
        if intent.status != "committed" {
            return Ok(
                json!({"status":"pending","transaction":intent.transaction,"plan_sha256":intent.plan_sha256,"network_bytes":0}),
            );
        }
    }
    match plan(root, release, requested, &CancelToken::new()) {
        Ok((plan, candidates)) => Ok(
            json!({"status":"ready","plan_sha256":hash(&serde_json::to_vec(&plan)?),"plan":plan,"candidates":candidates,"network_bytes":0,
            "actions":["independent_integrity_verification","isolated_entry_probe","restore_missing_registration_records"]}),
        ),
        Err(error) => Ok(
            json!({"status":"blocked","reason":format!("{error:#}"),"candidates":candidates(&layout,release).ok(),"network_bytes":0}),
        ),
    }
}
fn snapshot(layout: &Layout, transaction: &str, name: &str, bytes: &[u8]) -> Result<()> {
    model::validate_component(name)?;
    let path = layout.root.join("backups").join(transaction).join(name);
    if path.exists() {
        if read(layout, &path)?.as_deref() != Some(bytes) {
            bail!("登记快照重名且内容不同");
        }
        return Ok(());
    }
    model::write_gui_transaction_bytes(&layout.root, transaction, &path, bytes)
}
fn saved(layout: &Layout, intent: &Intent, name: &str, expected: &Stamp) -> Result<Vec<u8>> {
    model::validate_component(name)?;
    let bytes = read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join(name),
    )?
    .context("登记快照缺失")?;
    if stamp(&bytes) != *expected {
        bail!("登记快照身份变化");
    }
    Ok(bytes)
}
fn add_record(
    layout: &Layout,
    transaction: &str,
    records: &mut Vec<Record>,
    relative: PathBuf,
    old: Option<Vec<u8>>,
    new: Vec<u8>,
) -> Result<()> {
    if old.as_ref() == Some(&new) {
        return Ok(());
    }
    let n = records.len();
    let old_name = old.as_ref().map(|_| format!("record-{n}-old.bin"));
    let new_name = format!("record-{n}-new.bin");
    if let (Some(name), Some(bytes)) = (&old_name, &old) {
        snapshot(layout, transaction, name, bytes)?;
    }
    snapshot(layout, transaction, &new_name, &new)?;
    records.push(Record {
        relative,
        old: old.as_deref().map(stamp),
        new: stamp(&new),
        old_snapshot: old_name,
        new_snapshot: new_name,
    });
    Ok(())
}

/// 调用方持同一lease。validator和entry_probe不得写生产profiles、环境、旧state或健康指针。
pub(crate) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected_plan: &str,
    requested: Option<&str>,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    cancel.check()?;
    let layout = ctx.layout();
    let (plan, _) = plan(&layout.root, release, requested, cancel)?;
    let plan_sha256 = hash(&serde_json::to_vec(&plan)?);
    if expected_plan != plan_sha256 {
        bail!("补登记计划已变化，请重新预览");
    }
    let transaction = format!(
        "gui-registration-{}-{}-{}",
        model::now(),
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let mut registry = Registry::load(&layout.root)?;
    let state_missing = plan.candidate.state.is_none();
    let mut state = if state_missing {
        instances::registration_candidate(
            ctx,
            &plan.candidate.id,
            plan.candidate.storage_version,
            &transaction,
            &GuiRecipe::embedded()?.id,
            RECIPE_SHA,
            plan.candidate.generation,
            &plan.proof,
            cancel,
        )?
    } else {
        let state = instances::load(layout, &plan.candidate.id)?;
        if state.recipe_sha256() != RECIPE_SHA || state.recipe_id() != GuiRecipe::embedded()?.id {
            bail!("实例配方身份不符");
        }
        state
    };
    instances::registration_revalidate(layout, &state, state_missing, cancel, |environment| {
        let proof = gui_registration_integrity::verify(layout, release, environment, cancel)?;
        if proof != plan.proof {
            bail!("可信环境闭包变化");
        }
        validator(environment)?;
        entry_probe(environment, &transaction)
    })?;
    // 入口探测完成后重新比较preview的全部状态输入，避免以新状态覆盖外来写入。
    if read(layout, &layout.root.join("state/registry.json"))?
        .as_deref()
        .map(stamp)
        != plan.registry
        || read(layout, &layout.release_dir.join("release.json"))?
            .as_deref()
            .map(stamp)
            != plan.receipt
    {
        bail!("验证期间登记输入变化");
    }
    let binding = EnvironmentBinding {
        instance_id: state.id().into(),
        storage_version: state.storage_version(),
        recipe_id: state.recipe_id().into(),
        recipe_sha256: state.recipe_sha256().into(),
        generation: state.generation(),
    };
    registry.schema_version = registry.schema_version.max(2);
    registry.record_installed(release)?;
    if registry.gui_binding(&release.id) != Some(&binding) {
        registry.bind_gui(&release.id, binding)?;
    }
    registry.validate()?;
    let mut records = Vec::new();
    let receipt_bytes = encoded(&ReleaseReceipt::new(release))?;
    if plan.receipt.is_none() {
        add_record(
            layout,
            &transaction,
            &mut records,
            layout
                .release_dir
                .join("release.json")
                .strip_prefix(&layout.root)?
                .to_path_buf(),
            None,
            receipt_bytes.clone(),
        )?;
    }
    if state_missing {
        if plan.receipt.is_none() {
            instances::registration_project_receipt(layout, &mut state, &receipt_bytes)?;
        }
        add_record(
            layout,
            &transaction,
            &mut records,
            Path::new("state/instances").join(format!("{}.json", state.id())),
            None,
            instances::registration_encoded(layout, &state)?,
        )?;
    }
    add_record(
        layout,
        &transaction,
        &mut records,
        PathBuf::from("state/registry.json"),
        read(layout, &layout.root.join("state/registry.json"))?,
        encoded(&registry)?,
    )?;
    if records.is_empty() {
        return Ok(json!({"status":"already_registered","network_bytes":0,"proof":plan.proof}));
    }
    let intent = Intent {
        schema_version: 1,
        transaction,
        release_id: release.id.clone(),
        root_absolute: layout.root.clone(),
        status: "committing".into(),
        plan,
        plan_sha256,
        records,
    };
    // durable intent是首个生产state写入；此前只有专属备份与隔离探测证据。
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
    Registry::load(&layout.root)?.assert_base_python_ready()?;
    cancel.check()?;
    records::validate_identity(layout, release, &intent)?;
    crate::source_integrity::verify(layout, release)?;
    crate::python_integrity::verify(layout)?;
    let proof = gui_registration_integrity::verify(
        layout,
        release,
        &intent.plan.proof.environment,
        cancel,
    )?;
    if proof != intent.plan.proof {
        bail!("登记恢复实体与原独立证明不同，保留事务");
    }
    let state_relative =
        Path::new("state/instances").join(format!("{}.json", intent.plan.candidate.id));
    let state = if let Some(record) = intent.records.iter().find(|r| r.relative == state_relative) {
        let state = instances::registration_decode(
            layout,
            &saved(layout, &intent, &record.new_snapshot, &record.new)?,
        )?;
        if record.old.is_some() || intent.plan.candidate.state.is_some() {
            bail!("补登记禁止替换既有实例状态");
        }
        instances::registration_assert_origin(
            &state,
            &intent.transaction,
            intent.plan.candidate.generation,
            &proof,
        )?;
        state
    } else {
        instances::load(layout, &intent.plan.candidate.id)?
    };
    let state_absent = read(layout, &layout.root.join(&state_relative))?.is_none();
    instances::registration_revalidate(layout, &state, state_absent, cancel, |environment| {
        validator(environment)?;
        entry_probe(environment, &intent.transaction)
    })?;
    // 验证所有记录的old/new二态后才写任一项；未知第三状态不覆盖。
    let allowed: BTreeSet<_> = [
        PathBuf::from("state/registry.json"),
        state_relative,
        layout
            .release_dir
            .join("release.json")
            .strip_prefix(&layout.root)?
            .to_path_buf(),
    ]
    .into_iter()
    .collect();
    records::validate_semantics(layout, release, &intent, &state)?;
    records::commit(layout, &intent, &allowed, cancel)?;
    instances::assert_usable(&state)?;
    let registry = Registry::load(&layout.root)?;
    let binding = registry
        .gui_binding(&release.id)
        .context("提交后缺少binding")?;
    if binding.instance_id != state.id()
        || binding.generation != state.generation()
        || binding.storage_version != state.storage_version()
    {
        bail!("提交后binding与实例不符，保持gate");
    }
    if ReleaseReceipt::load(&layout.release_dir)?.release != *release {
        bail!("提交后receipt身份不符");
    }
    intent.status = "committed".into();
    model::write_gui_transaction_json(
        &layout.root,
        &intent.transaction,
        &intent_path(layout)?,
        &intent,
    )?;
    Ok(
        json!({"status":"registered","transaction":intent.transaction,"plan_sha256":intent.plan_sha256,"proof":proof,"network_bytes":0,
        "history_inherited":false,"current_changed":false,"profiles_changed":false}),
    )
}
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let intent = load_intent(ctx.layout())?.context("没有待恢复补登记事务")?;
    if intent.status == "committed" {
        return Ok(
            json!({"status":"already_registered","transaction":intent.transaction,"network_bytes":0}),
        );
    }
    finish(ctx, release, intent, cancel, validator, entry_probe)
}
