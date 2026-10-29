//! 版本化Ed25519清单、固定沙盒信任与可离线重验历史。刷新不激活、不修改安装绑定。
use crate::model::{self, Catalog, Layout, Registry, Release, WorkspaceMutation};
use anyhow::{bail, Context, Result};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

const SESSION_ID: &str = "signed-catalog-v1";
const PLATFORM: &str = "windows-x86_64";
const MAX_RECORD: u64 = 4 * 1024 * 1024;
const ROOT_ID: &str = "public-fixture-root-v1";
// RFC8032公开测试向量的公钥，仅在显式新沙盒会话内授信；不是生产身份。
const ROOT_HEX: &str = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
const FIXTURES: &str = include_str!("../../catalog/signed-fixtures-v1.json");
const ACTIONS: &[&str] = &[
    "download_source",
    "isolated_entry_probe",
    "uv_locked_sync",
    "uv_venv",
    "verify_environment",
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct SignedRelease {
    release: Release,
    published_at: u64,
    recipe_sha256: String,
    actions: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Rotation {
    key_id: String,
    public_key_hex: String,
}
/// canonical编码：本schema的字段顺序、紧凑UTF8 JSON；禁止未知字段/浮点数/非规范转义。
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Payload {
    schema_version: u32,
    encoding: String,
    channel: String,
    sequence: u64,
    issued_at: u64,
    expires_at: u64,
    platform: String,
    min_shell: String,
    profile_schema_version: u32,
    releases: Vec<SignedRelease>,
    rotations: Vec<Rotation>,
    revoked_keys: Vec<String>,
    revoked_releases: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Envelope {
    schema_version: u32,
    key_id: String,
    payload: String,
    signature_hex: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ShellPolicy {
    schema_version: u32,
    policy_id: String,
    channel: String,
    platform: String,
    action: String,
    current_relative: String,
    candidate_relative: String,
    max_bytes: u64,
    issued_at: u64,
    expires_at: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Session {
    schema_version: u32,
    root_absolute: PathBuf,
    fixture_id: String,
    shell_sha256: String,
    opened_at: u64,
    endpoint: String,
    root_key_id: String,
    root_public_key_hex: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Receipt {
    envelope_raw: String,
    payload_sha256: String,
    sequence: u64,
    accepted_at: u64,
    time_basis: String,
    trusted_keys_before: BTreeMap<String, String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct History {
    schema_version: u32,
    root_absolute: PathBuf,
    fixture_id: String,
    session_sha256: String,
    receipts: Vec<Receipt>,
}
#[derive(Default)]
struct Trust {
    keys: BTreeMap<String, String>,
    revoked_keys: BTreeSet<String>,
    revoked_releases: BTreeSet<String>,
    identities: BTreeMap<String, SignedRelease>,
    signers: BTreeMap<String, BTreeSet<String>>,
    sequence: u64,
    accepted_at: u64,
    latest: Option<Payload>,
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn shell_digest() -> Result<String> {
    use std::io::Read;
    static IDENTITY: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    if let Some(value) = IDENTITY.get() {
        return Ok(value.clone());
    }
    let path = std::env::current_exe()?;
    let length = fs::metadata(&path)?.len();
    if length > 1024 * 1024 * 1024 {
        bail!("壳文件超过摘要限额");
    }
    let mut file = fs::File::open(path)?;
    let mut hash = Sha256::new();
    let mut read_bytes = 0u64;
    let mut block = [0u8; 65536];
    loop {
        let count = file.read(&mut block)?;
        if count == 0 {
            break;
        }
        read_bytes += count as u64;
        if read_bytes > length {
            bail!("壳文件读取时变化");
        }
        hash.update(&block[..count]);
    }
    if read_bytes != length {
        bail!("壳文件读取时变化");
    }
    let value = format!("{:x}", hash.finalize());
    let _ = IDENTITY.set(value.clone());
    Ok(value)
}
fn scope(root: &Path) -> Result<Layout> {
    let catalog = Catalog::embedded()?;
    Layout::new(root, &catalog.releases.first().context("内置发布为空")?.id)
}
fn read(layout: &Layout, path: &Path) -> Result<Vec<u8>> {
    layout.guard_path(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > MAX_RECORD {
        bail!("可信记录不是限额普通文件");
    }
    let bytes = fs::read(path)?;
    if bytes.len() as u64 != meta.len() {
        bail!("可信记录读取时变化");
    }
    Ok(bytes)
}
fn decode_hex(value: &str, count: usize) -> Result<Vec<u8>> {
    if value.len() != count * 2
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        bail!("签名/公钥必须为固定长度小写hex");
    }
    (0..count)
        .map(|i| u8::from_str_radix(&value[i * 2..i * 2 + 2], 16).map_err(Into::into))
        .collect()
}
fn version(value: &str) -> Result<(u64, u64, u64)> {
    let numbers = value
        .split('.')
        .map(str::parse::<u64>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if numbers.len() != 3 {
        bail!("壳版本必须为三段数字");
    }
    Ok((numbers[0], numbers[1], numbers[2]))
}
fn sorted_unique(values: &[String]) -> bool {
    values.windows(2).all(|pair| pair[0] < pair[1])
}
fn key_revoked(trust: &Trust, id: &str) -> bool {
    trust.revoked_keys.contains(id)
        || trust.keys.get(id).is_some_and(|public| {
            trust
                .revoked_keys
                .iter()
                .any(|revoked| trust.keys.get(revoked) == Some(public))
        })
}
fn validate_payload(payload: &Payload) -> Result<()> {
    if payload.schema_version != 1
        || payload.encoding != "nt-catalog-json-v1"
        || payload.channel != "fixture"
        || payload.sequence == 0
        || payload.issued_at == 0
        || payload.expires_at <= payload.issued_at
        || payload.platform != PLATFORM
        || payload.profile_schema_version != model::PROFILE_SCHEMA_VERSION
        || version(&payload.min_shell)? > version(env!("CARGO_PKG_VERSION"))?
        || payload.releases.len() > 32
        || payload.rotations.len() > 8
        || payload.revoked_keys.len() > 32
        || payload.revoked_releases.len() > 128
        || !sorted_unique(&payload.revoked_keys)
        || !sorted_unique(&payload.revoked_releases)
        || !payload
            .releases
            .windows(2)
            .all(|w| w[0].release.id < w[1].release.id)
        || !payload
            .rotations
            .windows(2)
            .all(|w| w[0].key_id < w[1].key_id)
    {
        bail!("清单schema/平台/版本/时间/排序合同不支持");
    }
    let recipe = crate::recipe::GuiRecipe::embedded()?;
    for item in &payload.releases {
        item.release.validate()?;
        if item.published_at == 0
            || item.published_at > payload.issued_at
            || item.recipe_sha256
                != "8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090"
            || !recipe.matches_environment_recipe(&item.release.environment_recipe)
            || item.release.commit != recipe.source_commit
            || item.actions.is_empty()
            || !sorted_unique(&item.actions)
            || item
                .actions
                .iter()
                .any(|action| !ACTIONS.contains(&action.as_str()))
        {
            bail!("远端配方只能选择内置固定配方及已编译动作");
        }
    }
    for key in &payload.rotations {
        model::validate_component(&key.key_id)?;
        decode_hex(&key.public_key_hex, 32)?;
    }
    for id in &payload.revoked_keys {
        model::validate_component(id)?;
    }
    for id in &payload.revoked_releases {
        model::validate_release_id(id)?;
    }
    Ok(())
}
fn verify(raw: &str, trust: &Trust, accepted_at: u64) -> Result<(Envelope, Payload)> {
    if raw.len() as u64 > MAX_RECORD {
        bail!("清单响应超限");
    }
    let envelope: Envelope = serde_json::from_str(raw)?;
    if envelope.schema_version != 1 || key_revoked(trust, &envelope.key_id) {
        bail!("未知封套或已撤销签名key");
    }
    let key = trust
        .keys
        .get(&envelope.key_id)
        .context("签名key未受旧可信key授权")?;
    let signature = decode_hex(&envelope.signature_hex, 64)?;
    let public = decode_hex(key, 32)?;
    UnparsedPublicKey::new(&ED25519, public)
        .verify(envelope.payload.as_bytes(), &signature)
        .map_err(|_| anyhow::anyhow!("Ed25519签名无效"))?;
    let payload: Payload = serde_json::from_str(&envelope.payload)?;
    if serde_json::to_string(&payload)? != envelope.payload {
        bail!("payload不是规范编码");
    }
    validate_payload(&payload)?;
    if payload.sequence <= trust.sequence
        || accepted_at < payload.issued_at
        || accepted_at >= payload.expires_at
        || accepted_at < trust.accepted_at
    {
        bail!("清单重放、过期、尚未生效或系统时钟回退");
    }
    Ok((envelope, payload))
}
fn advance(trust: &mut Trust, payload: &Payload, accepted_at: u64, signer: &str) -> Result<()> {
    for key in &payload.rotations {
        if key_revoked(trust, &key.key_id)
            || payload.revoked_keys.contains(&key.key_id)
            || trust
                .revoked_keys
                .iter()
                .chain(payload.revoked_keys.iter())
                .any(|id| trust.keys.get(id) == Some(&key.public_key_hex))
            || trust
                .keys
                .get(&key.key_id)
                .is_some_and(|old| *old != key.public_key_hex)
        {
            bail!("轮换不能替换或复活既有key身份");
        }
        trust
            .keys
            .insert(key.key_id.clone(), key.public_key_hex.clone());
    }
    for item in &payload.releases {
        if trust
            .identities
            .get(&item.release.id)
            .is_some_and(|old| old != item)
        {
            bail!("相同release ID不可重新定义资产/配方/发布日期");
        }
        trust
            .identities
            .insert(item.release.id.clone(), item.clone());
        trust
            .signers
            .entry(item.release.id.clone())
            .or_default()
            .insert(signer.into());
    }
    trust
        .revoked_keys
        .extend(payload.revoked_keys.iter().cloned());
    trust
        .revoked_releases
        .extend(payload.revoked_releases.iter().cloned());
    trust.sequence = payload.sequence;
    trust.accepted_at = accepted_at;
    trust.latest = Some(payload.clone());
    Ok(())
}
fn session(layout: &Layout) -> Result<Option<(Session, Vec<u8>)>> {
    let path = layout.root.join("state/signed-catalog-session.json");
    layout.guard_path(&path)?;
    if !path.exists() {
        return Ok(None);
    }
    let bytes = read(layout, &path)?;
    let session: Session = serde_json::from_slice(&bytes)?;
    if session.schema_version != 1
        || session.root_absolute != layout.root
        || session.fixture_id != SESSION_ID
        || session.root_key_id != ROOT_ID
        || session.root_public_key_hex != ROOT_HEX
        || session.endpoint != "embedded://signed-catalog-v1"
        || session.opened_at == 0
        || session.shell_sha256 != shell_digest()?
    {
        bail!("沙盒会话与固定根/端点/本包身份不符");
    }
    Ok(Some((session, bytes)))
}
fn load(layout: &Layout) -> Result<Option<(History, Trust)>> {
    let Some((session, session_bytes)) = session(layout)? else {
        if layout.root.join("state/signed-catalog.json").exists() {
            bail!("普通根拒绝外来测试信任历史");
        }
        return Ok(None);
    };
    let path = layout.root.join("state/signed-catalog.json");
    layout.guard_path(&path)?;
    let history: History = if path.exists() {
        serde_json::from_slice(&read(layout, &path)?)?
    } else {
        History {
            schema_version: 1,
            root_absolute: layout.root.clone(),
            fixture_id: session.fixture_id,
            session_sha256: digest(&session_bytes),
            receipts: vec![],
        }
    };
    if history.schema_version != 1
        || history.root_absolute != layout.root
        || history.fixture_id != SESSION_ID
        || history.session_sha256 != digest(&session_bytes)
        || history.receipts.len() > 64
    {
        bail!("可信历史schema/根/会话/限额不符");
    }
    let mut trust = Trust {
        keys: BTreeMap::from([(ROOT_ID.into(), ROOT_HEX.into())]),
        ..Trust::default()
    };
    for receipt in &history.receipts {
        if receipt.time_basis != "system_clock"
            || receipt.accepted_at < session.opened_at
            || receipt.trusted_keys_before != trust.keys
        {
            bail!("历史时间依据或轮换链断联");
        }
        let (envelope, payload) = verify(&receipt.envelope_raw, &trust, receipt.accepted_at)?;
        if receipt.payload_sha256 != digest(envelope.payload.as_bytes())
            || receipt.sequence != payload.sequence
        {
            bail!("历史payload摘要/序号断联");
        }
        advance(&mut trust, &payload, receipt.accepted_at, &envelope.key_id)?;
    }
    Ok(Some((history, trust)))
}
/// 仅新工作区可显式打开同包固定测试信任；配置只能在创建时写入。
pub(crate) fn open_fixture_session(ctx: &WorkspaceMutation, fixture_id: &str) -> Result<Value> {
    let layout = ctx.layout();
    if fixture_id != SESSION_ID {
        bail!("未知固定测试会话ID");
    }
    if session(layout)?.is_some() || layout.root.join("state/signed-catalog.json").exists() {
        bail!("测试会话必须从新工作区开始，不能改写信任根");
    }
    let registry = Registry::load(&layout.root)?;
    if !registry.installed.is_empty()
        || registry.current.is_some()
        || registry.base_python_pending.is_some()
    {
        bail!("已有安装/绑定不能切换为测试信任");
    }
    for name in [
        "releases",
        "environments",
        "e",
        "state/instances",
        "backups",
        "run",
        "cache",
        "tools",
        "python",
        "staging",
    ] {
        let path = layout.root.join(name);
        layout.guard_path(&path)?;
        if path.exists() && fs::read_dir(&path)?.next().is_some() {
            bail!("测试会话需要新隔离空根：{name}");
        }
    }
    let allowed_root = [
        ".launcher-workspace",
        ".launcher-lock",
        "state",
        "releases",
        "environments",
        "e",
        "profiles",
        "tools",
        "python",
        "cache",
        "staging",
        "backups",
        "run",
    ];
    for entry in fs::read_dir(&layout.root)? {
        let entry = entry?;
        layout.guard_path(&entry.path())?;
        if !allowed_root.iter().any(|name| entry.file_name() == *name) {
            bail!("新沙盒根含未知已有资料");
        }
    }
    for entry in fs::read_dir(layout.root.join("state"))? {
        let entry = entry?;
        layout.guard_path(&entry.path())?;
        if entry.file_name() != "registry.json" {
            bail!("已有状态不能改为测试会话");
        }
    }
    for entry in fs::read_dir(layout.root.join("profiles"))? {
        if entry?.file_name() != "default" {
            bail!("已有profile不能改为测试会话");
        }
    }
    for entry in fs::read_dir(&layout.profile)? {
        let entry = entry?;
        layout.guard_path(&entry.path())?;
        if entry.file_name() == "profile.json" {
            let actual = model::Profile::load(&entry.path())?;
            if serde_json::to_value(actual)? != serde_json::to_value(model::Profile::default())? {
                bail!("测试会话需要默认新profile");
            }
        } else if !model::PROFILE_DIRECTORIES
            .iter()
            .any(|name| entry.file_name() == *name)
            || fs::read_dir(entry.path())?.next().is_some()
        {
            bail!("已有用户资料不能改为测试会话");
        }
    }
    let session = Session {
        schema_version: 1,
        root_absolute: layout.root.clone(),
        fixture_id: fixture_id.into(),
        shell_sha256: shell_digest()?,
        opened_at: model::now(),
        endpoint: "embedded://signed-catalog-v1".into(),
        root_key_id: ROOT_ID.into(),
        root_public_key_hex: ROOT_HEX.into(),
    };
    model::write_json_atomic(
        &layout.root.join("state/signed-catalog-session.json"),
        &session,
    )?;
    status(&layout.root)
}
fn accept(ctx: &WorkspaceMutation, raw: &str, now: u64) -> Result<Value> {
    let layout = ctx.layout();
    let (mut history, mut trust) =
        load(layout)?.context("普通模式不接受测试资产；生产签名渠道尚未配置")?;
    let (envelope, payload) = verify(raw, &trust, now)?;
    let receipt = Receipt {
        envelope_raw: raw.into(),
        payload_sha256: digest(envelope.payload.as_bytes()),
        sequence: payload.sequence,
        accepted_at: now,
        time_basis: "system_clock".into(),
        trusted_keys_before: trust.keys.clone(),
    };
    advance(&mut trust, &payload, now, &envelope.key_id)?;
    history.receipts.push(receipt);
    let encoded = serde_json::to_vec_pretty(&history)?;
    if history.receipts.len() > 64 || encoded.len() as u64 + 1 > MAX_RECORD {
        bail!("可信历史达到只增不覆盖限额");
    }
    model::write_json_atomic(&layout.root.join("state/signed-catalog.json"), &history)?;
    Ok(
        json!({"status":"accepted","sequence":trust.sequence,"releases":payload.releases,"current_changed":false,"time_basis":"system_clock","fixture":true}),
    )
}
/// 固定case只用于显式沙盒；UI不能传响应字节、公钥、URL或命令。
pub(crate) fn refresh(ctx: &WorkspaceMutation, fixture_case: Option<&str>) -> Result<Value> {
    let Some(name) = fixture_case else {
        return Ok(
            json!({"status":"embedded_only","reason":"生产签名公钥及发布渠道尚未配置","current_changed":false}),
        );
    };
    if session(ctx.layout())?.is_none() {
        bail!("普通根拒绝测试清单");
    }
    let values: BTreeMap<String, Envelope> = serde_json::from_str(FIXTURES)?;
    let raw = if name == "tampered" {
        let mut value = values.get("valid-v1").context("固定夹具丢失")?.clone();
        value.payload.push(' ');
        serde_json::to_string(&value)?
    } else {
        serde_json::to_string(values.get(name).context("未知固定清单case")?)?
    };
    accept(ctx, &raw, model::now())
}
pub(crate) fn catalog(root: &Path) -> Result<Vec<Release>> {
    let Some((_, trust)) = load(&scope(root)?)? else {
        return Ok(vec![]);
    };
    Ok(trust
        .latest
        .as_ref()
        .into_iter()
        .flat_map(|p| p.releases.iter())
        .filter(|r| !trust.revoked_releases.contains(&r.release.id))
        .filter(|r| {
            trust
                .signers
                .get(&r.release.id)
                .is_some_and(|keys| keys.iter().any(|key| !key_revoked(&trust, key)))
        })
        .map(|r| r.release.clone())
        .collect())
}
pub(crate) fn authorize(root: &Path, release_id: &str, purpose: &str) -> Result<Value> {
    authorize_at(root, release_id, purpose, model::now())
}
fn authorize_at(root: &Path, release_id: &str, purpose: &str, now: u64) -> Result<Value> {
    if !matches!(purpose, "install" | "activate" | "rollback" | "repair") {
        bail!("未知可信操作目的");
    }
    let loaded = load(&scope(root)?)?;
    if let Some((_, trust)) = &loaded {
        if trust.revoked_releases.contains(release_id) {
            bail!("发布已被可信安全撤销，保留资料并禁止安装/激活/回退/修复");
        }
        if let Some(item) = trust.identities.get(release_id) {
            if trust
                .signers
                .get(release_id)
                .is_none_or(|keys| keys.iter().all(|key| key_revoked(trust, key)))
            {
                bail!("该发布的签名key已全部撤销，禁止继续使用其授权");
            }
            if purpose == "install" {
                let latest = trust.latest.as_ref().context("缺少当前清单")?;
                if now < trust.accepted_at
                    || now >= latest.expires_at
                    || !latest.releases.iter().any(|r| r.release.id == release_id)
                {
                    bail!("过期/下架清单不能授权新安装，既有离线使用保留");
                }
            }
            return Ok(
                json!({"status":"trusted","source":"signed_fixture","release":item.release,"purpose":purpose,"sequence":trust.sequence}),
            );
        }
    }
    let catalog = Catalog::embedded()?;
    let release = catalog.release(release_id)?;
    Ok(
        json!({"status":"trusted","source":"embedded","release":release,"purpose":purpose,"shell_version":env!("CARGO_PKG_VERSION"),"catalog_sha256":digest(include_bytes!("../../catalog/releases.json"))}),
    )
}
pub(crate) fn history(root: &Path) -> Result<Value> {
    let Some((history, trust)) = load(&scope(root)?)? else {
        return Ok(json!({"status":"embedded_only","receipts":[],"production_ready":false}));
    };
    Ok(
        json!({"status":"verified_offline","fixture":true,"sequence":trust.sequence,"receipts":history.receipts,"revoked_releases":trust.revoked_releases,"retained_key_ids":trust.keys.keys().collect::<Vec<_>>(),"production_ready":false}),
    )
}
pub(crate) fn status(root: &Path) -> Result<Value> {
    let loaded = load(&scope(root)?)?;
    Ok(match loaded {
        None => {
            json!({"status":"embedded_only","production_ready":false,"fixture_session":false,"fixture_id":SESSION_ID,"available_cases":[],"reason":"生产签名公钥及发布渠道尚未配置"})
        }
        Some((history, trust)) => {
            json!({"status":"fixture_ready","production_ready":false,"fixture_session":true,"fixture_id":SESSION_ID,"sequence":trust.sequence,"accepted_at":trust.accepted_at,"receipt_count":history.receipts.len(),"available_cases":["valid-v1","rotate-v2","revoke-v3","expired","wrong-platform","tampered","replay"]})
        }
    })
}

/// 同SHA自复制仅验证沙盒helper事务；不授权生产壳升级或任意候选。
#[cfg(test)]
pub(crate) fn authorize_shell(root: &Path, asset_sha: &str, asset_bytes: u64) -> Result<Value> {
    verify_shell_fixture(root, asset_sha, asset_sha, asset_bytes)
}
pub(crate) fn verify_shell_fixture(
    root: &Path,
    old_sha: &str,
    candidate_sha: &str,
    bytes: u64,
) -> Result<Value> {
    let layout = scope(root)?;
    let (session, _) = session(&layout)?.context("生产shell签名资产尚未配置，拒绝自更新")?;
    let (history, trust) = load(&layout)?.context("沙盒信任历史缺失")?;
    if trust.sequence == 0 || key_revoked(&trust, ROOT_ID) {
        bail!("未接受固定可信清单或policy签名key已撤销");
    }
    decode_hex(old_sha, 32)?;
    decode_hex(candidate_sha, 32)?;
    let own_bytes = fs::metadata(std::env::current_exe()?)?.len();
    if old_sha != candidate_sha
        || candidate_sha != session.shell_sha256
        || bytes != own_bytes
        || bytes == 0
    {
        bail!("沙盒policy仅允许本交付壳的精确同SHA同字节自复制");
    }
    let fixtures: BTreeMap<String, Envelope> = serde_json::from_str(FIXTURES)?;
    let envelope = fixtures
        .get("shell-self-copy-policy")
        .context("固定shell policy缺失")?;
    if envelope.schema_version != 1 || envelope.key_id != ROOT_ID {
        bail!("shell policy信任根无效");
    }
    let signature = decode_hex(&envelope.signature_hex, 64)?;
    UnparsedPublicKey::new(&ED25519, decode_hex(ROOT_HEX, 32)?)
        .verify(envelope.payload.as_bytes(), &signature)
        .map_err(|_| anyhow::anyhow!("shell policy Ed25519签名无效"))?;
    let policy: ShellPolicy = serde_json::from_str(&envelope.payload)?;
    if serde_json::to_string(&policy)? != envelope.payload
        || policy.schema_version != 1
        || policy.policy_id != "current-shell-self-copy-v1"
        || policy.channel != "fixture"
        || policy.platform != PLATFORM
        || policy.action != "replace_shell_self_copy"
        || policy.current_relative != "shell-fixture/current/NextTrainerLauncher.exe"
        || policy.candidate_relative != "shell-fixture/candidate/NextTrainerLauncher.exe"
        || policy.max_bytes != 1024 * 1024 * 1024
        || bytes > policy.max_bytes
        || model::now() < policy.issued_at
        || model::now() >= policy.expires_at
    {
        bail!("shell固定policy字段/时间/路径合同不符");
    }
    Ok(
        json!({"status":"trusted_fixture","production_update":false,"policy":policy,"policy_envelope_raw":serde_json::to_string(envelope)?,"policy_payload_sha256":digest(envelope.payload.as_bytes()),"session":session,"history":history,"old_sha256":old_sha,"candidate_sha256":candidate_sha,"bytes":bytes}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture {
        ctx: WorkspaceMutation,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-signed-catalog-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let release = Catalog::embedded().unwrap().releases[0].id.clone();
            Self {
                ctx: WorkspaceMutation::acquire(&root, &release).unwrap(),
            }
        }
        fn root(&self) -> &Path {
            &self.ctx.layout().root
        }
        fn enable(&self) {
            open_fixture_session(&self.ctx, SESSION_ID).unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let root = self.root();
            if root.parent() == Some(std::env::temp_dir().as_path())
                && root
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-signed-catalog-")
            {
                let _ = fs::remove_dir_all(root);
            }
        }
    }
    #[test]
    fn signed_catalog_fixture_requires_fresh_explicit_session_and_fixed_ids() {
        let f = Fixture::new();
        assert_eq!(status(f.root()).unwrap()["status"], "embedded_only");
        assert!(refresh(&f.ctx, Some("valid-v1")).is_err());
        assert!(!f.root().join("state/signed-catalog.json").exists());
        assert!(open_fixture_session(&f.ctx, "https://foreign/key").is_err());
        fs::write(
            f.root().join("profiles/default/user_data/existing.txt"),
            b"do not adopt",
        )
        .unwrap();
        assert!(open_fixture_session(&f.ctx, SESSION_ID).is_err());
        assert_eq!(
            fs::read(f.root().join("profiles/default/user_data/existing.txt")).unwrap(),
            b"do not adopt"
        );
        fs::remove_file(f.root().join("profiles/default/user_data/existing.txt")).unwrap();
        f.enable();
        assert!(open_fixture_session(&f.ctx, SESSION_ID).is_err());
        assert!(refresh(&f.ctx, Some("foreign-case")).is_err());
    }
    #[test]
    fn signed_catalog_rotation_rejection_offline_expiry_and_revocation_preserve_registry() {
        let f = Fixture::new();
        f.enable();
        Registry::default().store(f.root()).unwrap();
        let registry = fs::read(f.root().join("state/registry.json")).unwrap();
        assert!(refresh(&f.ctx, Some("rotate-v2")).is_err());
        assert_eq!(refresh(&f.ctx, Some("valid-v1")).unwrap()["sequence"], 1);
        let id = catalog(f.root()).unwrap()[0].id.clone();
        assert_eq!(refresh(&f.ctx, Some("rotate-v2")).unwrap()["sequence"], 2);
        let accepted = fs::read(f.root().join("state/signed-catalog.json")).unwrap();
        for invalid in ["tampered", "expired", "wrong-platform", "replay"] {
            assert!(refresh(&f.ctx, Some(invalid)).is_err(), "case={invalid}");
            assert_eq!(
                fs::read(f.root().join("state/signed-catalog.json")).unwrap(),
                accepted
            );
        }
        assert_eq!(history(f.root()).unwrap()["status"], "verified_offline");
        assert!(authorize_at(f.root(), &id, "rollback", 1893456001).is_ok());
        assert!(authorize_at(f.root(), &id, "install", 1893456001).is_err());
        assert_eq!(refresh(&f.ctx, Some("revoke-v3")).unwrap()["sequence"], 3);
        for purpose in ["install", "activate", "rollback", "repair"] {
            assert!(authorize(f.root(), &id, purpose).is_err());
        }
        assert!(catalog(f.root()).unwrap().is_empty());
        assert_eq!(
            fs::read(f.root().join("state/registry.json")).unwrap(),
            registry
        );
    }
    #[test]
    fn signed_catalog_unknown_history_and_changed_session_refuse_without_overwrite() {
        let f = Fixture::new();
        f.enable();
        refresh(&f.ctx, Some("valid-v1")).unwrap();
        let path = f.root().join("state/signed-catalog.json");
        let good = fs::read(&path).unwrap();
        let mut unknown: Value = serde_json::from_slice(&good).unwrap();
        unknown["schema_version"] = 99.into();
        let unknown = serde_json::to_vec(&unknown).unwrap();
        fs::write(&path, &unknown).unwrap();
        assert!(refresh(&f.ctx, Some("rotate-v2")).is_err());
        assert_eq!(fs::read(&path).unwrap(), unknown);
        fs::write(&path, good).unwrap();
        let session_path = f.root().join("state/signed-catalog-session.json");
        let mut unknown: Value = serde_json::from_slice(&fs::read(&session_path).unwrap()).unwrap();
        unknown["root_public_key_hex"] = "a".repeat(64).into();
        fs::write(&session_path, serde_json::to_vec(&unknown).unwrap()).unwrap();
        assert!(status(f.root()).is_err());
    }
    #[test]
    fn signed_catalog_shell_policy_only_authorizes_exact_self_copy_in_explicit_session() {
        let f = Fixture::new();
        let sha = shell_digest().unwrap();
        let bytes = fs::metadata(std::env::current_exe().unwrap())
            .unwrap()
            .len();
        assert!(authorize_shell(f.root(), &sha, bytes).is_err());
        f.enable();
        assert!(authorize_shell(f.root(), &sha, bytes).is_err());
        refresh(&f.ctx, Some("valid-v1")).unwrap();
        let proof = authorize_shell(f.root(), &sha, bytes).unwrap();
        assert_eq!(proof["policy"]["action"], "replace_shell_self_copy");
        assert!(verify_shell_fixture(f.root(), &sha, &"a".repeat(64), bytes).is_err());
        assert!(authorize_shell(f.root(), &sha, bytes + 1).is_err());
    }
}
