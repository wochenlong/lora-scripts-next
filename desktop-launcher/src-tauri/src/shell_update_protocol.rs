//! 主壳与独立helper共用的有界协议。只支持显式沙盒内的同SHA自复制；生产更新默认拒绝。
use anyhow::{bail, Context, Result};
use fs2::FileExt;
use ring::{
    rand::{SecureRandom, SystemRandom},
    signature::{UnparsedPublicKey, ED25519},
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub const CURRENT: &str = "shell-fixture/current/NextTrainerLauncher.exe";
pub const CANDIDATE: &str = "shell-fixture/candidate/NextTrainerLauncher.exe";
const ROOT_KEY_ID: &str = "public-fixture-root-v1";
const ROOT_KEY: &str = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
const MAX_CONTROL: u64 = 32 * 1024 * 1024;
const MAX_CONTROLS: u64 = 512 * 1024 * 1024;
const MAX_SHELL: u64 = 1024 * 1024 * 1024;
const MAX_NODES: usize = 20_000;
static NEXT: AtomicU64 = AtomicU64::new(0);

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn digest(value: &impl Serialize) -> Result<String> {
    Ok(hash(&serde_json::to_vec(value)?))
}
fn hex(value: &str, count: usize) -> Result<Vec<u8>> {
    if value.len() != count * 2
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        bail!("更新身份hex格式无效");
    }
    (0..count)
        .map(|i| Ok(u8::from_str_radix(&value[i * 2..i * 2 + 2], 16)?))
        .collect()
}
fn component(name: &str) -> Result<()> {
    if name.is_empty()
        || name == "."
        || name == ".."
        || name.len() > 180
        || name.ends_with('.')
        || name.ends_with(' ')
        || name.chars().any(|c| c < ' ' || "<>:\"/\\|?*".contains(c))
    {
        bail!("更新路径组件无效");
    }
    let stem = name
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    if ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"].contains(&stem.as_str())
        || ["COM", "LPT"].iter().any(|p| {
            stem.strip_prefix(p).is_some_and(|s| {
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "¹", "²", "³"].contains(&s)
            })
        })
    {
        bail!("更新路径包含保留名称");
    }
    Ok(())
}
pub fn regular(path: &Path) -> Result<()> {
    if !path.is_absolute() {
        bail!("更新路径必须绝对");
    }
    let mut current = PathBuf::new();
    for part in path.components() {
        match part {
            Component::Normal(name) => component(name.to_str().context("更新路径非Unicode")?)?,
            Component::ParentDir | Component::CurDir => bail!("更新路径包含跳转"),
            _ => (),
        }
        current.push(part);
        match fs::symlink_metadata(&current) {
            Ok(info) => {
                #[cfg(windows)]
                let linked = {
                    use std::os::windows::fs::MetadataExt;
                    info.file_attributes() & 0x400 != 0
                };
                #[cfg(not(windows))]
                let linked = info.file_type().is_symlink();
                if linked || info.file_type().is_symlink() {
                    bail!("更新不接受reparse或符号链接");
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() {
        bail!("更新清单空路径");
    }
    for part in path.components() {
        let Component::Normal(name) = part else {
            bail!("更新清单不得含绝对路径或跳转");
        };
        component(name.to_str().context("更新清单非Unicode")?)?;
    }
    Ok(())
}
pub fn owned(root: &Path, path: &Path) -> Result<()> {
    regular(root)?;
    if !path.starts_with(root) {
        bail!("更新实体超出固定根");
    }
    regular(path)
}
fn read(path: &Path, limit: u64) -> Result<Vec<u8>> {
    regular(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > limit {
        bail!("更新控制实体不是有界普通文件");
    }
    let mut data = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut data)?;
    if data.len() as u64 > limit {
        bail!("更新控制读取期间超限");
    }
    Ok(data)
}
fn encoded(value: &impl Serialize) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
pub fn write_json(root: &Path, path: &Path, value: &impl Serialize) -> Result<()> {
    atomic_bytes(root, path, &encoded(value)?)
}
fn replace(from: &Path, to: &Path) -> Result<()> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        #[link(name = "kernel32")]
        extern "system" {
            fn MoveFileExW(old: *const u16, new: *const u16, flags: u32) -> i32;
        }
        let from: Vec<u16> = from.as_os_str().encode_wide().chain(Some(0)).collect();
        let to: Vec<u16> = to.as_os_str().encode_wide().chain(Some(0)).collect();
        if unsafe { MoveFileExW(from.as_ptr(), to.as_ptr(), 0x1 | 0x8) } == 0 {
            return Err(std::io::Error::last_os_error()).context("壳文件原子替换失败");
        }
    }
    #[cfg(not(windows))]
    {
        fs::rename(from, to)?;
        File::open(to.parent().context("原子目标缺少父目录")?)?.sync_all()?;
    }
    Ok(())
}
fn atomic_bytes(root: &Path, path: &Path, bytes: &[u8]) -> Result<()> {
    owned(root, path)?;
    let parent = path.parent().context("控制文件无父目录")?;
    fs::create_dir_all(parent)?;
    owned(root, parent)?;
    let tmp = parent.join(format!(
        ".shell-write-{}-{}.tmp",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    owned(root, &tmp)?;
    let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    replace(&tmp, path)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub bytes: u64,
    pub sha256: String,
}
pub fn identity(path: &Path, limit: u64) -> Result<Identity> {
    regular(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() > limit {
        bail!("更新资产不是有界普通文件");
    }
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut length = 0;
    let mut block = [0u8; 65536];
    loop {
        let count = file.read(&mut block)?;
        if count == 0 {
            break;
        }
        length += count as u64;
        if length > metadata.len() {
            bail!("更新资产读取期间增长");
        }
        hasher.update(&block[..count]);
    }
    if length != metadata.len() {
        bail!("更新资产读取期间变化");
    }
    Ok(Identity {
        bytes: length,
        sha256: format!("{:x}", hasher.finalize()),
    })
}
fn copy_new(root: &Path, source: &Path, target: &Path, expected: &Identity) -> Result<()> {
    owned(root, target)?;
    if identity(source, MAX_SHELL)? != *expected {
        bail!("待复制资产身份变化");
    }
    fs::create_dir_all(target.parent().context("复制目标无父目录")?)?;
    owned(root, target)?;
    let input = File::open(source)?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    std::io::copy(&mut input.take(expected.bytes + 1), &mut output)?;
    output.sync_all()?;
    drop(output);
    if identity(target, MAX_SHELL)? != *expected {
        bail!("复制资产身份变化，保留未完成文件");
    }
    Ok(())
}
fn atomic_copy(
    root: &Path,
    tx: &Path,
    source: &Path,
    target: &Path,
    expected: &Identity,
) -> Result<()> {
    let swap = tx.join("swap");
    owned(root, &swap)?;
    fs::create_dir_all(&swap)?;
    let tmp = swap.join(format!(
        "swap-{}-{}.part",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    copy_new(root, source, &tmp, expected)?;
    owned(root, target)?;
    fs::create_dir_all(target.parent().context("更新目标无父目录")?)?;
    replace(&tmp, target)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ControlSnapshot {
    pub schema_version: u32,
    pub files: BTreeMap<PathBuf, Identity>,
    pub total_bytes: u64,
}
fn control_paths(root: &Path) -> Result<BTreeSet<PathBuf>> {
    regular(root)?;
    let mut result = BTreeSet::new();
    let mut seen = 0usize;
    fn walk(
        root: &Path,
        path: &Path,
        result: &mut BTreeSet<PathBuf>,
        seen: &mut usize,
        depth: usize,
    ) -> Result<()> {
        owned(root, path)?;
        if depth > 128 {
            bail!("控制树层数超限");
        }
        if !path.exists() {
            return Ok(());
        }
        *seen += 1;
        if *seen > MAX_NODES {
            bail!("控制树条目超限");
        }
        let meta = fs::symlink_metadata(path)?;
        if meta.is_file() {
            result.insert(path.strip_prefix(root)?.into());
        } else if meta.is_dir() {
            for entry in fs::read_dir(path)?.take(MAX_NODES + 1) {
                walk(root, &entry?.path(), result, seen, depth + 1)?;
            }
        } else {
            bail!("控制树含未知实体");
        }
        Ok(())
    }
    for name in [".launcher-workspace", "state", "config", "launcher.json"] {
        walk(root, &root.join(name), &mut result, &mut seen, 0)?;
    }
    let profiles = root.join("profiles");
    owned(root, &profiles)?;
    if profiles.exists() {
        for entry in fs::read_dir(profiles)?.take(MAX_NODES + 1) {
            let path = entry?.path();
            owned(root, &path)?;
            if !path.is_dir() {
                bail!("profile容器含非目录");
            }
            for name in ["profile.json", "user_data"] {
                walk(root, &path.join(name), &mut result, &mut seen, 0)?;
            }
            let compat = path.join("compat");
            owned(root, &compat)?;
            if compat.exists() {
                for release in fs::read_dir(compat)?.take(MAX_NODES + 1) {
                    let release = release?.path();
                    owned(root, &release)?;
                    if !release.is_dir() {
                        bail!("兼容资料容器含非目录");
                    }
                    for name in ["assets/config.json", "config", "toml"] {
                        walk(root, &release.join(name), &mut result, &mut seen, 0)?;
                    }
                }
            }
        }
    }
    let releases = root.join("releases");
    owned(root, &releases)?;
    if releases.exists() {
        for entry in fs::read_dir(releases)?.take(MAX_NODES + 1) {
            let path = entry?.path();
            owned(root, &path)?;
            if !path.is_dir() {
                bail!("发布容器含非目录");
            }
            for name in ["release.json", "app/.source-integrity.json"] {
                walk(root, &path.join(name), &mut result, &mut seen, 0)?;
            }
        }
    }
    Ok(result)
}
pub fn capture_controls(root: &Path, validate_schema: bool) -> Result<ControlSnapshot> {
    let mut files = BTreeMap::new();
    let mut total = 0u64;
    for path in control_paths(root)? {
        let absolute = root.join(&path);
        let id = identity(&absolute, MAX_CONTROL)?;
        total = total.checked_add(id.bytes).context("控制快照容量溢出")?;
        if total > MAX_CONTROLS {
            bail!("控制快照超出512MiB，拒绝壳更新");
        }
        if validate_schema && path.extension().is_some_and(|s| s == "json") {
            let value: Value = serde_json::from_slice(&read(&absolute, MAX_CONTROL)?)
                .context("控制JSON损坏，不覆盖")?;
            if let Some(version) = value.get("schema_version") {
                if !matches!(version.as_u64(), Some(1..=3)) {
                    bail!("控制schema未知，拒绝壳更新");
                }
            }
        }
        files.insert(path, id);
    }
    Ok(ControlSnapshot {
        schema_version: 1,
        files,
        total_bytes: total,
    })
}
fn validate_snapshot(snapshot: &ControlSnapshot) -> Result<()> {
    if snapshot.schema_version != 1 || snapshot.files.len() > MAX_NODES {
        bail!("控制快照协议无效");
    }
    let mut total = 0u64;
    for (path, id) in &snapshot.files {
        relative(path)?;
        hex(&id.sha256, 32)?;
        if id.bytes > MAX_CONTROL {
            bail!("控制快照单文件超限");
        }
        total = total.checked_add(id.bytes).context("控制快照容量溢出")?;
    }
    if total != snapshot.total_bytes || total > MAX_CONTROLS {
        bail!("控制快照容量不符");
    }
    Ok(())
}
pub fn save_controls(root: &Path, tx: &Path, snapshot: &ControlSnapshot) -> Result<()> {
    validate_snapshot(snapshot)?;
    if capture_controls(root, true)? != *snapshot {
        bail!("保存前控制状态变化");
    }
    for (path, id) in &snapshot.files {
        copy_new(root, &root.join(path), &tx.join("controls").join(path), id)?;
    }
    if capture_controls(root, true)? != *snapshot {
        bail!("保存期间控制状态变化");
    }
    Ok(())
}
pub fn verify_controls(root: &Path, snapshot: &ControlSnapshot) -> Result<()> {
    validate_snapshot(snapshot)?;
    if capture_controls(root, false)? != *snapshot {
        bail!("只读trial改变了控制文件集合或原字节");
    }
    Ok(())
}
fn verify_backups(root: &Path, tx: &Path, snapshot: &ControlSnapshot) -> Result<()> {
    validate_snapshot(snapshot)?;
    for (path, id) in &snapshot.files {
        let backup = tx.join("controls").join(path);
        owned(root, &backup)?;
        if identity(&backup, MAX_CONTROL)? != *id {
            bail!("原字节快照缺失或损坏，保持新壳恢复模式");
        }
    }
    Ok(())
}
pub fn restore_controls(root: &Path, tx: &Path, snapshot: &ControlSnapshot) -> Result<()> {
    verify_backups(root, tx, snapshot)?;
    let observed = capture_controls(root, false)?;
    for (path, id) in &observed.files {
        if snapshot.files.get(path) != Some(id) {
            let source = root.join(path);
            let target = tx.join("quarantine").join(path);
            owned(root, &target)?;
            if target.exists() {
                if identity(&target, MAX_CONTROL)? != *id {
                    bail!("隔离现场冲突，禁止覆盖");
                }
                bail!("已有隔离现场，需人工检查重复外部变化");
            }
            fs::create_dir_all(target.parent().context("隔离目录缺失")?)?;
            fs::rename(source, target)?;
        }
    }
    for (path, id) in &snapshot.files {
        let target = root.join(path);
        if !target.exists() || identity(&target, MAX_CONTROL)? != *id {
            atomic_copy(root, tx, &tx.join("controls").join(path), &target, id)?;
        }
    }
    verify_controls(root, snapshot)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProcessIdentity {
    pub pid: u32,
    pub created_at: u64,
}
#[cfg(windows)]
pub fn process_identity(pid: u32) -> Result<Option<ProcessIdentity>> {
    use windows_sys::Win32::{
        Foundation::{CloseHandle, FILETIME, WAIT_OBJECT_0, WAIT_TIMEOUT},
        System::Threading::{
            GetProcessTimes, OpenProcess, WaitForSingleObject, PROCESS_QUERY_LIMITED_INFORMATION,
            PROCESS_SYNCHRONIZE,
        },
    };
    let handle = unsafe {
        OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
            0,
            pid,
        )
    };
    if handle.is_null() {
        let e = std::io::Error::last_os_error();
        if matches!(e.raw_os_error(), Some(87 | 1168)) {
            return Ok(None);
        }
        return Err(e.into());
    }
    let mut created = FILETIME {
        dwLowDateTime: 0,
        dwHighDateTime: 0,
    };
    let mut exited = created;
    let mut kernel = created;
    let mut user = created;
    let ok = unsafe { GetProcessTimes(handle, &mut created, &mut exited, &mut kernel, &mut user) };
    let status = unsafe { WaitForSingleObject(handle, 0) };
    unsafe { CloseHandle(handle) };
    if ok == 0 {
        return Err(std::io::Error::last_os_error()).context("读取进程创建时间失败");
    }
    if status == WAIT_OBJECT_0 {
        return Ok(None);
    }
    if status != WAIT_TIMEOUT {
        bail!("进程归属读取失败");
    }
    Ok(Some(ProcessIdentity {
        pid,
        created_at: ((created.dwHighDateTime as u64) << 32) | created.dwLowDateTime as u64,
    }))
}
#[cfg(not(windows))]
pub fn process_identity(_pid: u32) -> Result<Option<ProcessIdentity>> {
    bail!("原生更新仅支持Windows进程身份");
}
fn process_live(expected: &ProcessIdentity) -> Result<bool> {
    Ok(process_identity(expected.pid)?.as_ref() == Some(expected))
}
fn wait_parent(parent: &ProcessIdentity, timeout: Duration) -> Result<()> {
    let deadline = Instant::now() + timeout;
    while process_live(parent)? {
        if Instant::now() >= deadline {
            bail!("等待已登记父进程退出超时；未终止任何外部进程");
        }
        std::thread::sleep(Duration::from_millis(40));
    }
    Ok(())
}

fn envelope_verify(envelope: &Value, keys: &BTreeMap<String, String>) -> Result<Value> {
    if envelope["schema_version"] != 1 {
        bail!("壳签名封套版本未知");
    }
    let key_id = envelope["key_id"].as_str().context("壳签名key缺失")?;
    let public = keys.get(key_id).context("壳签名key未受信任")?;
    let payload = envelope["payload"].as_str().context("壳签名payload缺失")?;
    let sig = envelope["signature_hex"].as_str().context("壳签名缺失")?;
    UnparsedPublicKey::new(&ED25519, hex(public, 32)?)
        .verify(payload.as_bytes(), &hex(sig, 64)?)
        .map_err(|_| anyhow::anyhow!("壳policy Ed25519签名无效"))?;
    Ok(serde_json::from_str(payload)?)
}
pub fn verify_fixture_proof(root: &Path, proof: &Value, asset: &Identity) -> Result<()> {
    verify_fixture_records(root, root, proof, asset, now())
}
fn verify_fixture_records(
    root: &Path,
    records: &Path,
    proof: &Value,
    asset: &Identity,
    at: u64,
) -> Result<()> {
    regular(root)?;
    hex(&asset.sha256, 32)?;
    if asset.bytes == 0
        || asset.bytes > MAX_SHELL
        || proof["production_update"] != false
        || proof["old_sha256"] != asset.sha256
        || proof["candidate_sha256"] != asset.sha256
        || proof["bytes"] != asset.bytes
    {
        bail!("同包壳fixture身份不符，生产更新默认拒绝");
    }
    let fixtures: Value =
        serde_json::from_str(include_str!("../../catalog/signed-fixtures-v1.json"))?;
    let envelope: Value = serde_json::from_str(
        proof["policy_envelope_raw"]
            .as_str()
            .context("壳policy原封套缺失")?,
    )?;
    if envelope != fixtures["shell-self-copy-policy"] {
        bail!("壳policy不是编译固定fixture");
    }
    let mut keys = BTreeMap::from([(ROOT_KEY_ID.into(), ROOT_KEY.into())]);
    let policy = envelope_verify(&envelope, &keys)?;
    if proof["policy"] != policy
        || proof["policy_payload_sha256"] != hash(envelope["payload"].as_str().unwrap().as_bytes())
        || policy["action"] != "replace_shell_self_copy"
        || policy["current_relative"] != CURRENT
        || policy["candidate_relative"] != CANDIDATE
        || policy["platform"] != "windows-x86_64"
        || policy["max_bytes"] != MAX_SHELL
        || at < policy["issued_at"].as_u64().context("policy起始时间缺失")?
        || at
            >= policy["expires_at"]
                .as_u64()
                .context("policy到期时间缺失")?
    {
        bail!("壳policy路径/动作/时间合同不符");
    }
    let session_raw = read(
        &records.join("state/signed-catalog-session.json"),
        MAX_CONTROL,
    )?;
    let session: Value = serde_json::from_slice(&session_raw)?;
    if proof["session"] != session
        || session["schema_version"] != 1
        || session["root_absolute"] != root.to_string_lossy().as_ref()
        || session["fixture_id"] != "signed-catalog-v1"
        || session["root_key_id"] != ROOT_KEY_ID
        || session["root_public_key_hex"] != ROOT_KEY
        || session["endpoint"] != "embedded://signed-catalog-v1"
        || session["shell_sha256"] != asset.sha256
        || session["opened_at"]
            .as_u64()
            .is_none_or(|n| n == 0 || n > now())
    {
        bail!("壳fixture会话根/端点/身份不符");
    }
    let history: Value = serde_json::from_slice(&read(
        &records.join("state/signed-catalog.json"),
        MAX_CONTROL,
    )?)?;
    if proof["history"] != history
        || history["schema_version"] != 1
        || history["root_absolute"] != session["root_absolute"]
        || history["fixture_id"] != session["fixture_id"]
        || history["session_sha256"] != hash(&session_raw)
    {
        bail!("壳fixture历史与只读会话不符");
    }
    let receipts = history["receipts"]
        .as_array()
        .context("壳fixture缺少验签历史")?;
    if receipts.is_empty() || receipts.len() > 3 {
        bail!("壳fixture历史数量不受支持");
    }
    let cases = ["valid-v1", "rotate-v2", "revoke-v3"];
    let mut accepted = session["opened_at"].as_u64().unwrap();
    let mut revoked = BTreeSet::new();
    for (index, receipt) in receipts.iter().enumerate() {
        let envelope: Value =
            serde_json::from_str(receipt["envelope_raw"].as_str().context("历史原封套缺失")?)?;
        if envelope != fixtures[cases[index]]
            || receipt["trusted_keys_before"] != serde_json::to_value(&keys)?
            || receipt["time_basis"] != "system_clock"
            || revoked.contains(envelope["key_id"].as_str().unwrap_or(""))
        {
            bail!("壳fixture历史链/固定动作不符");
        }
        let payload = envelope_verify(&envelope, &keys)?;
        let time = receipt["accepted_at"]
            .as_u64()
            .context("历史接受时间缺失")?;
        if time < accepted
            || time > now()
            || time < payload["issued_at"].as_u64().context("历史发行时间缺失")?
            || time >= payload["expires_at"].as_u64().context("历史过期时间缺失")?
            || receipt["payload_sha256"] != hash(envelope["payload"].as_str().unwrap().as_bytes())
            || receipt["sequence"] != payload["sequence"]
        {
            bail!("壳fixture历史序号/时间/摘要不符");
        }
        accepted = time;
        for item in payload["rotations"].as_array().context("历史轮换缺失")? {
            keys.insert(
                item["key_id"].as_str().context("轮换key缺失")?.into(),
                item["public_key_hex"]
                    .as_str()
                    .context("轮换公钥缺失")?
                    .into(),
            );
        }
        for item in payload["revoked_keys"]
            .as_array()
            .context("历史撤销记录缺失")?
        {
            revoked.insert(item.as_str().context("撤销key无效")?.to_string());
        }
    }
    if revoked.contains(ROOT_KEY_ID) {
        bail!("壳fixture policy根已撤销");
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema_version: u32,
    pub authorized_at: u64,
    pub root_absolute: PathBuf,
    pub current_relative: PathBuf,
    pub candidate_relative: PathBuf,
    pub asset: Identity,
    pub controls: ControlSnapshot,
    pub trust_proof: Value,
    pub trial_mode: String,
    pub plan_sha256: String,
}
pub fn seal_plan(plan: &mut Plan) -> Result<()> {
    plan.plan_sha256.clear();
    plan.plan_sha256 = digest(plan)?;
    Ok(())
}
fn validate_plan(root: &Path, records: &Path, plan: &Plan, historical: bool) -> Result<()> {
    let mut expected = plan.clone();
    seal_plan(&mut expected)?;
    if plan.schema_version != 1
        || plan.root_absolute != root
        || plan.current_relative != Path::new(CURRENT)
        || plan.candidate_relative != Path::new(CANDIDATE)
        || plan.plan_sha256 != expected.plan_sha256
        || plan.authorized_at == 0
        || plan.authorized_at > now()
        || !matches!(plan.trial_mode.as_str(), "normal" | "reject")
    {
        bail!("壳更新计划根/清单/动作/摘要无效");
    }
    validate_snapshot(&plan.controls)?;
    if plan.controls.files.get(Path::new(".launcher-workspace"))
        != Some(&Identity {
            bytes: b"next-trainer-desktop-v1".len() as u64,
            sha256: hash(b"next-trainer-desktop-v1"),
        })
    {
        bail!("壳更新快照不含精确工作区归属标记");
    }
    verify_fixture_records(
        root,
        records,
        &plan.trust_proof,
        &plan.asset,
        if historical {
            plan.authorized_at
        } else {
            now()
        },
    )
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Intent {
    pub schema_version: u32,
    pub transaction: String,
    pub status: String,
    pub plan: Plan,
    pub parent: ProcessIdentity,
    pub helper: Option<ProcessIdentity>,
    pub trial: Option<ProcessIdentity>,
    pub old_shell: Identity,
    pub updated_at: u64,
    pub failure: Option<String>,
    pub intent_sha256: String,
}
fn seal_intent(intent: &mut Intent) -> Result<()> {
    intent.intent_sha256.clear();
    intent.intent_sha256 = digest(intent)?;
    Ok(())
}
fn tx_root(tx: &Path) -> Result<PathBuf> {
    regular(tx)?;
    let transaction = tx
        .file_name()
        .and_then(|n| n.to_str())
        .context("壳事务ID缺失")?;
    component(transaction)?;
    if !transaction.starts_with("shell-update-") {
        bail!("壳事务ID无效");
    }
    let shell = tx.parent().context("壳事务父目录缺失")?;
    let updates = shell.parent().context("壳事务上级缺失")?;
    if shell.file_name().is_none_or(|n| n != "shell")
        || updates.file_name().is_none_or(|n| n != "updates")
    {
        bail!("壳事务不在固定updates/shell命名空间");
    }
    Ok(updates.parent().context("壳事务根缺失")?.into())
}
pub fn load_intent(tx: &Path) -> Result<Intent> {
    let root = tx_root(tx)?;
    let intent: Intent = serde_json::from_slice(&read(&tx.join("intent.json"), 16 * 1024 * 1024)?)?;
    let mut expected = intent.clone();
    seal_intent(&mut expected)?;
    if intent.schema_version != 1
        || tx.file_name().and_then(|n| n.to_str()) != Some(intent.transaction.as_str())
        || intent.intent_sha256 != expected.intent_sha256
        || intent.parent.pid == 0
        || intent.parent.created_at == 0
        || !matches!(
            intent.status.as_str(),
            "prepared"
                | "waiting"
                | "swapping"
                | "trial"
                | "committed"
                | "restoring"
                | "restored"
                | "recovery_required"
                | "aborted"
        )
    {
        bail!("壳更新意图身份/状态/摘要无效");
    }
    // 常规读取只核对不可变信任材料，避免每次展示状态都重读整套历史快照。
    for name in [
        "state/signed-catalog-session.json",
        "state/signed-catalog.json",
    ] {
        let expected = intent
            .plan
            .controls
            .files
            .get(Path::new(name))
            .context("壳更新快照缺少信任控制文件")?;
        let backup = tx.join("controls").join(name);
        owned(&root, &backup)?;
        if identity(&backup, MAX_CONTROL)? != *expected {
            bail!("壳更新信任原字节快照损坏");
        }
    }
    validate_plan(&root, &tx.join("controls"), &intent.plan, true)?;
    if intent.old_shell != intent.plan.asset {
        bail!("fixture旧壳必须与候选同包");
    }
    Ok(intent)
}
fn store_intent(tx: &Path, intent: &mut Intent) -> Result<()> {
    let root = tx_root(tx)?;
    intent.updated_at = now();
    seal_intent(intent)?;
    write_json(&root, &tx.join("intent.json"), intent)
}
pub fn assert_ready(root: &Path) -> Result<()> {
    let gate = root.join("updates/shell/active.json");
    owned(root, &gate)?;
    if !gate.exists() {
        return Ok(());
    }
    let value: Value = serde_json::from_slice(&read(&gate, 64 * 1024)?)?;
    let transaction = value["transaction"]
        .as_str()
        .context("壳活动gate缺少事务ID")?;
    component(transaction)?;
    if value["schema_version"] != 1 || value["root_absolute"] != root.to_string_lossy().as_ref() {
        bail!("壳活动gate身份不符");
    }
    let intent = load_intent(&root.join("updates/shell").join(transaction))?;
    if !matches!(intent.status.as_str(), "committed" | "restored" | "aborted") {
        bail!("壳更新事务{}尚未恢复，禁止启动和变更", intent.transaction);
    }
    Ok(())
}
pub fn prepare(
    root: &Path,
    plan: &Plan,
    parent: ProcessIdentity,
    source: &Path,
) -> Result<PathBuf> {
    assert_ready(root)?;
    validate_plan(root, root, plan, false)?;
    if process_identity(parent.pid)?.as_ref() != Some(&parent) {
        bail!("壳父进程身份已经变化");
    }
    if identity(source, MAX_SHELL)? != plan.asset {
        bail!("壳源不是受会话锁定的同包");
    }
    verify_controls(root, &plan.controls)?;
    let transaction = format!(
        "shell-update-{}-{}-{}",
        now(),
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let tx = root.join("updates/shell").join(&transaction);
    owned(root, &tx)?;
    if tx.exists() {
        bail!("壳事务目录已存在");
    }
    fs::create_dir_all(&tx)?;
    save_controls(root, &tx, &plan.controls)?;
    copy_new(root, source, &tx.join("old-shell.exe"), &plan.asset)?;
    verify_controls(root, &plan.controls)?;
    let mut intent = Intent {
        schema_version: 1,
        transaction: transaction.clone(),
        status: "prepared".into(),
        plan: plan.clone(),
        parent,
        helper: None,
        trial: None,
        old_shell: plan.asset.clone(),
        updated_at: now(),
        failure: None,
        intent_sha256: String::new(),
    };
    store_intent(&tx, &mut intent)?;
    write_json(
        root,
        &root.join("updates/shell/active.json"),
        &json!({"schema_version":1,"root_absolute":root,"transaction":transaction}),
    )?;
    // 所有实际目标变更均在durable intent/gate之后，部分创建失败也可按事务恢复。
    for name in [CURRENT, CANDIDATE] {
        let target = root.join(name);
        owned(root, &target)?;
        if target.exists() {
            if identity(&target, MAX_SHELL)? != plan.asset {
                bail!("壳fixture目标已被未知资产占用");
            }
        } else {
            atomic_copy(root, &tx, source, &target, &plan.asset)?;
        }
    }
    Ok(tx)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrialRequest {
    pub schema_version: u32,
    pub root_absolute: PathBuf,
    pub transaction: String,
    pub token: String,
    pub expected_shell_sha256: String,
    pub helper_pid: u32,
    pub helper_created_at: u64,
    pub timeout_ms: u64,
    pub trial_mode: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrialAck {
    pub schema_version: u32,
    pub transaction: String,
    pub token: String,
    pub trial_pid: u32,
    pub trial_created_at: u64,
    pub rendered: bool,
    pub recovery_available: bool,
    pub expected_shell_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrialResult {
    pub schema_version: u32,
    pub transaction: String,
    pub status: String,
    pub message: String,
}
fn request(tx: &Path, intent: &Intent) -> Result<TrialRequest> {
    let req: TrialRequest =
        serde_json::from_slice(&read(&tx.join("trial-request.json"), 64 * 1024)?)?;
    hex(&req.token, 32)?;
    if req.schema_version != 1
        || req.root_absolute != intent.plan.root_absolute
        || req.transaction != intent.transaction
        || req.expected_shell_sha256 != intent.plan.asset.sha256
        || req.timeout_ms != 30_000
        || req.trial_mode != intent.plan.trial_mode
        || intent.helper.as_ref()
            != Some(&ProcessIdentity {
                pid: req.helper_pid,
                created_at: req.helper_created_at,
            })
    {
        bail!("只读trial请求与壳事务不符");
    }
    Ok(req)
}
pub fn trial_context(tx: &Path) -> Result<TrialRequest> {
    let intent = load_intent(tx)?;
    if intent.status != "trial" {
        bail!("壳事务不在只读trial阶段");
    }
    let req = request(tx, &intent)?;
    if !process_live(&ProcessIdentity {
        pid: req.helper_pid,
        created_at: req.helper_created_at,
    })? {
        bail!("只读trial的helper不再归属本事务");
    }
    let current = std::env::current_exe()?;
    let target = req.root_absolute.join(CURRENT);
    regular(&target)?;
    if fs::canonicalize(current)? != fs::canonicalize(&target)?
        || identity(&target, MAX_SHELL)?.sha256 != req.expected_shell_sha256
    {
        bail!("只读trial不是固定候选壳");
    }
    verify_controls(&req.root_absolute, &intent.plan.controls)?;
    Ok(req)
}
pub fn write_trial_ack(
    tx: &Path,
    token: &str,
    rendered: bool,
    recovery_available: bool,
) -> Result<()> {
    let req = trial_context(tx)?;
    if token != req.token || !rendered || !recovery_available {
        bail!("只读trial握手尚未完整或令牌错误");
    }
    let process = process_identity(std::process::id())?.context("无法读取trial自身身份")?;
    let ack = TrialAck {
        schema_version: 1,
        transaction: req.transaction,
        token: req.token,
        trial_pid: process.pid,
        trial_created_at: process.created_at,
        rendered,
        recovery_available,
        expected_shell_sha256: req.expected_shell_sha256,
    };
    let path = tx.join("trial-ack.json");
    if path.exists() {
        let old: TrialAck = serde_json::from_slice(&read(&path, 64 * 1024)?)?;
        if digest(&old)? != digest(&ack)? {
            bail!("trial已有不同握手，拒绝覆盖");
        }
        return Ok(());
    }
    write_json(&req.root_absolute, &path, &ack)
}
pub fn trial_result(tx: &Path) -> Result<Option<TrialResult>> {
    let root = tx_root(tx)?;
    let path = tx.join("trial-result.json");
    owned(&root, &path)?;
    if !path.exists() {
        return Ok(None);
    }
    let result: TrialResult = serde_json::from_slice(&read(&path, 64 * 1024)?)?;
    if result.schema_version != 1
        || tx.file_name().and_then(|s| s.to_str()) != Some(result.transaction.as_str())
        || !matches!(result.status.as_str(), "verified" | "rejected")
    {
        bail!("trial结果身份/状态无效");
    }
    Ok(Some(result))
}
fn ack_valid(ack: &TrialAck, req: &TrialRequest, child: &ProcessIdentity) -> Result<()> {
    if ack.schema_version != 1
        || ack.transaction != req.transaction
        || ack.token != req.token
        || ack.trial_pid != child.pid
        || ack.trial_created_at != child.created_at
        || ack.expected_shell_sha256 != req.expected_shell_sha256
        || !ack.rendered
        || !ack.recovery_available
    {
        bail!("trial令牌/进程/渲染/恢复入口握手失败");
    }
    Ok(())
}
fn result_file(tx: &Path, intent: &Intent, verified: bool) -> Result<()> {
    write_json(
        &intent.plan.root_absolute,
        &tx.join("trial-result.json"),
        &TrialResult {
            schema_version: 1,
            transaction: intent.transaction.clone(),
            status: if verified { "verified" } else { "rejected" }.into(),
            message: if verified {
                "只读窗口和恢复入口已确认，请退出trial"
            } else {
                "试运行未通过，关闭后恢复原壳和控制状态"
            }
            .into(),
        },
    )
}
fn finish_child(child: &mut Child) -> Result<()> {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if child.try_wait()?.is_some() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            child.kill()?;
            child.wait()?;
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(40));
    }
}
#[cfg(windows)]
struct TrialJob(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
impl TrialJob {
    fn new() -> Result<Self> {
        use windows_sys::Win32::System::JobObjects::{
            CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if handle.is_null() {
            return Err(std::io::Error::last_os_error()).context("创建trial进程组失败");
        }
        let job = Self(handle);
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error()).context("设置trial退出回收失败");
        }
        Ok(job)
    }
    fn attach(&self, child: &Child) -> Result<()> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::AssignProcessToJobObject;
        if unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle() as _) } == 0 {
            return Err(std::io::Error::last_os_error()).context("trial进程组归属失败");
        }
        Ok(())
    }
}
#[cfg(windows)]
impl Drop for TrialJob {
    fn drop(&mut self) {
        unsafe { windows_sys::Win32::Foundation::CloseHandle(self.0) };
    }
}
fn run_trial(tx: &Path, intent: &mut Intent) -> Result<()> {
    let root = intent.plan.root_absolute.clone();
    let helper = process_identity(std::process::id())?.context("helper进程归属缺失")?;
    intent.helper = Some(helper.clone());
    let mut random = [0u8; 32];
    SystemRandom::new()
        .fill(&mut random)
        .map_err(|_| anyhow::anyhow!("trial随机令牌创建失败"))?;
    let token = random.iter().map(|v| format!("{v:02x}")).collect();
    let req = TrialRequest {
        schema_version: 1,
        root_absolute: root.clone(),
        transaction: intent.transaction.clone(),
        token,
        expected_shell_sha256: intent.plan.asset.sha256.clone(),
        helper_pid: helper.pid,
        helper_created_at: helper.created_at,
        timeout_ms: 30_000,
        trial_mode: intent.plan.trial_mode.clone(),
    };
    write_json(&root, &tx.join("trial-request.json"), &req)?;
    intent.status = "trial".into();
    store_intent(tx, intent)?;
    let mut command = Command::new(root.join(CURRENT));
    command
        .arg("--shell-trial")
        .arg(tx)
        .current_dir(tx)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    #[cfg(windows)]
    let job = TrialJob::new()?;
    let mut child = command.spawn().context("新壳trial启动失败")?;
    #[cfg(windows)]
    if let Err(error) = job.attach(&child) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    let outcome = (|| {
        let child_id = process_identity(child.id())?.context("新壳trial在握手前退出")?;
        intent.trial = Some(child_id.clone());
        store_intent(tx, intent)?;
        let deadline = Instant::now() + Duration::from_millis(req.timeout_ms);
        loop {
            let ack_path = tx.join("trial-ack.json");
            if ack_path.exists() {
                let ack: TrialAck = serde_json::from_slice(&read(&ack_path, 64 * 1024)?)?;
                ack_valid(&ack, &req, &child_id)?;
                verify_controls(&root, &intent.plan.controls)?;
                if req.trial_mode == "reject" {
                    bail!("固定fixture拒绝分支：渲染握手后模拟新壳首启失败");
                }
                return Ok(());
            }
            if child.try_wait()?.is_some() {
                bail!("新壳trial在完整握手前退出");
            }
            if Instant::now() >= deadline {
                bail!("新壳trial渲染/恢复入口自检超时");
            }
            std::thread::sleep(Duration::from_millis(40));
        }
    })();
    let notified = result_file(tx, intent, outcome.is_ok());
    let finished = finish_child(&mut child);
    notified?;
    finished?;
    outcome?;
    verify_controls(&root, &intent.plan.controls)
}
fn acquire(root: &Path) -> Result<File> {
    regular(root)?;
    let path = root.join(".launcher-lock");
    owned(root, &path)?;
    let lock = OpenOptions::new().read(true).write(true).open(path)?;
    lock.try_lock_exclusive()
        .context("安装/变更/壳更新共用锁正被使用")?;
    Ok(lock)
}
fn restore(tx: &Path, intent: &mut Intent) -> Result<()> {
    let root = intent.plan.root_absolute.clone();
    verify_backups(&root, tx, &intent.plan.controls)?;
    if identity(&tx.join("old-shell.exe"), MAX_SHELL)? != intent.old_shell {
        bail!("旧壳原件快照缺失或损坏，保留新壳只读恢复");
    }
    let target = root.join(CURRENT);
    let actual = if target.exists() {
        Some(identity(&target, MAX_SHELL)?)
    } else {
        None
    };
    if actual
        .as_ref()
        .is_some_and(|v| v != &intent.plan.asset && v != &intent.old_shell)
    {
        bail!("壳目标出现非本事务资产，禁止恢复覆盖");
    }
    intent.status = "restoring".into();
    store_intent(tx, intent)?;
    restore_controls(&root, tx, &intent.plan.controls)?;
    atomic_copy(
        &root,
        tx,
        &tx.join("old-shell.exe"),
        &target,
        &intent.old_shell,
    )?;
    if identity(&target, MAX_SHELL)? != intent.old_shell {
        bail!("恢复旧壳身份不符");
    }
    verify_controls(&root, &intent.plan.controls)?;
    intent.status = "restored".into();
    store_intent(tx, intent)
}
pub fn helper_apply(tx: &Path, recover: bool) -> Result<Intent> {
    let mut intent = load_intent(tx)?;
    let root = intent.plan.root_absolute.clone();
    wait_parent(&intent.parent, Duration::from_secs(15))?;
    let _lock = acquire(&root)?;
    intent = load_intent(tx)?;
    if matches!(intent.status.as_str(), "committed" | "restored" | "aborted") {
        return Ok(intent);
    }
    if recover
        || matches!(
            intent.status.as_str(),
            "swapping" | "trial" | "restoring" | "recovery_required"
        )
    {
        if let Some(trial) = &intent.trial {
            if process_live(trial)? {
                bail!("原trial仍存活，恢复不会终止非本helper持有的进程");
            }
        }
        if let Err(error) = restore(tx, &mut intent) {
            intent.status = "recovery_required".into();
            intent.failure = Some(format!("{error:#}"));
            store_intent(tx, &mut intent)?;
            return Err(error);
        }
        return Ok(intent);
    }
    if !matches!(intent.status.as_str(), "prepared" | "waiting") {
        bail!("壳事务状态不允许开始替换");
    }
    intent.status = "waiting".into();
    store_intent(tx, &mut intent)?;
    if let Err(error) = verify_controls(&root, &intent.plan.controls) {
        intent.status = "aborted".into();
        intent.failure = Some(format!("{error:#}"));
        store_intent(tx, &mut intent)?;
        return Err(error);
    }
    verify_backups(&root, tx, &intent.plan.controls)?;
    if identity(&root.join(CURRENT), MAX_SHELL)? != intent.old_shell
        || identity(&root.join(CANDIDATE), MAX_SHELL)? != intent.plan.asset
    {
        bail!("壳源/候选实体变化，保留待恢复现场");
    }
    intent.status = "swapping".into();
    store_intent(tx, &mut intent)?;
    let outcome = (|| {
        atomic_copy(
            &root,
            tx,
            &root.join(CANDIDATE),
            &root.join(CURRENT),
            &intent.plan.asset,
        )?;
        run_trial(tx, &mut intent)?;
        intent.status = "committed".into();
        store_intent(tx, &mut intent)
    })();
    if let Err(error) = outcome {
        intent.failure = Some(format!("{error:#}"));
        if let Err(restore_error) = restore(tx, &mut intent) {
            intent.status = "recovery_required".into();
            intent.failure = Some(format!("trial失败：{error:#}；恢复失败：{restore_error:#}"));
            store_intent(tx, &mut intent)?;
            return Err(restore_error);
        }
        return Err(error);
    }
    Ok(intent)
}

#[cfg(test)]
#[path = "shell_update_protocol_tests.rs"]
mod tests;

/// 格式迁移是壳确认后的独立事务；当前无自动格式升级，故显式返回no_migration而不改状态。
pub fn migration_status(tx: &Path) -> Result<Value> {
    let intent = load_intent(tx)?;
    if intent.status != "committed" {
        bail!("壳尚未确认，不允许格式迁移");
    }
    Ok(
        json!({"schema_version":1,"transaction":intent.transaction,"status":"no_migration","writes":[],"reason":"当前壳支持既有控制协议；不自动迁移资料或重写格式"}),
    )
}
