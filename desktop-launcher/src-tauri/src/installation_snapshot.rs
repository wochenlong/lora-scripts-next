//! 开窗只读概况：只读取有界元数据和必要入口是否存在，不计算安装文件摘要，不执行解释器。
//! start_available 只表示可以尝试正式启动；正式启动仍独立检查全部可信文件、事务、租约和健康接口。
use super::{release_support, ReleaseSupport};
use crate::model::{self, Catalog, EnvironmentBinding, Profile, Registry, Release, ReleaseReceipt};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
};

const MAX_METADATA_BYTES: u64 = 32 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 64 * 1024 * 1024;
const MAX_RECORDS: usize = 256;

#[derive(Serialize)]
pub struct InstallationSnapshot {
    root: String,
    verification: &'static str,
    workspace: &'static str,
    current_release: Option<String>,
    previous_known_good: Option<String>,
    profile_path: Option<String>,
    start_available: bool,
    versions: Vec<InstallationVersionView>,
    issues: Vec<SnapshotIssue>,
}

#[derive(Serialize)]
struct InstallationVersionView {
    id: String,
    channel: String,
    version: String,
    commit: String,
    download_bytes: u64,
    source_bytes: u64,
    installed: bool,
    source_present: bool,
    // 只表示登记中已有GUI实例绑定；即使目录缺失也保留true，不代表环境可用。
    environment_bound: bool,
    environment_present: bool,
    current: bool,
    known_good: bool,
    managed_recipe: bool,
    #[serde(flatten)]
    support: ReleaseSupport,
    structure: &'static str,
    issues: Vec<SnapshotIssue>,
}

#[derive(Serialize)]
struct SnapshotIssue {
    code: &'static str,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    release_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    path: Option<String>,
}

fn issue(code: &'static str, message: impl Into<String>, path: Option<&Path>) -> SnapshotIssue {
    SnapshotIssue {
        code,
        message: message.into(),
        release_id: None,
        path: path.map(|p| p.to_string_lossy().into()),
    }
}

struct Reader<'a> {
    root: &'a Path,
    remaining: u64,
    records: usize,
}

impl Reader<'_> {
    fn guard(&self, path: &Path) -> Result<()> {
        if !path.starts_with(self.root) {
            bail!("概况路径越出安装目录");
        }
        model::validate_storage_directory(path)
    }

    fn present(&self, path: &Path, directory: bool) -> Result<bool> {
        self.guard(path)?;
        match fs::symlink_metadata(path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
            Err(error) => Err(error.into()),
            Ok(meta) if directory && meta.is_dir() || !directory && meta.is_file() => Ok(true),
            Ok(_) => bail!("必要入口不是预期的普通文件或目录：{}", path.display()),
        }
    }

    fn optional(&mut self, path: &Path) -> Result<Option<Vec<u8>>> {
        if !self.present(path, false)? {
            return Ok(None);
        }
        self.records += 1;
        if self.records > MAX_RECORDS {
            bail!("安装概况元数据条目过多，请使用完整检查诊断");
        }
        let input = File::open(path)?;
        let size = input.metadata()?.len();
        if size > MAX_METADATA_BYTES || size > self.remaining {
            bail!("安装概况元数据超出只读限额，请使用完整检查诊断");
        }
        let mut bytes = Vec::new();
        input.take(size + 1).read_to_end(&mut bytes)?;
        self.guard(path)?;
        if bytes.len() as u64 != size {
            bail!("读取概况期间元数据发生变化，请刷新");
        }
        self.remaining -= size;
        Ok(Some(bytes))
    }

    fn json(&mut self, path: &Path) -> Result<Option<Value>> {
        self.optional(path)?
            .map(|raw| serde_json::from_slice(&raw).context("安装元数据不是有效JSON"))
            .transpose()
    }

    fn directory(&self, path: &Path) -> Result<Vec<PathBuf>> {
        if !self.present(path, true)? {
            return Ok(vec![]);
        }
        let mut paths = Vec::new();
        for entry in fs::read_dir(path)? {
            if paths.len() >= MAX_RECORDS {
                bail!("安装概况事务条目过多，请使用完整检查诊断");
            }
            paths.push(entry?.path());
        }
        paths.sort();
        Ok(paths)
    }
}

// 只解码实例身份和状态；verified中的大文件树由serde跳过，绝不在此校验/遍历环境。
#[derive(Deserialize)]
struct InstanceHeader {
    schema_version: u32,
    component: String,
    instance_id: String,
    #[serde(default)]
    storage_version: u32,
    release_id: String,
    root_absolute: PathBuf,
    recipe_id: String,
    recipe_sha256: String,
    generation: u64,
    validated_generation: u64,
    dirty: bool,
    pending: Option<serde::de::IgnoredAny>,
    base_python_pending: Option<serde::de::IgnoredAny>,
}

fn inspect_binding(
    reader: &mut Reader<'_>,
    release: &Release,
    binding: &EnvironmentBinding,
) -> Result<()> {
    let path = reader
        .root
        .join("state/instances")
        .join(format!("{}.json", binding.instance_id));
    let raw = reader.optional(&path)?.context("绑定的环境实例记录缺失")?;
    let state: InstanceHeader = serde_json::from_slice(&raw)?;
    if !matches!(state.schema_version, 2 | 3)
        || state.component != "gui"
        || state.root_absolute != reader.root
        || state.release_id != release.id
        || state.instance_id != binding.instance_id
        || state.storage_version != binding.storage_version
        || state.recipe_id != binding.recipe_id
        || state.recipe_sha256 != binding.recipe_sha256
        || state.generation != binding.generation
    {
        bail!("环境实例身份或绑定代次不一致，请使用完整检查诊断");
    }
    if state.dirty
        || state.pending.is_some()
        || state.base_python_pending.is_some()
        || state.generation != state.validated_generation
    {
        bail!("环境实例有未完成操作或未经验证的代次，请恢复原操作");
    }
    Ok(())
}

fn profile(reader: &mut Reader<'_>, registry: &Registry) -> Result<PathBuf> {
    let bindings_path = reader.root.join("state/profile-bindings.json");
    let mut id = "default".to_string();
    if let Some(raw) = reader.optional(&bindings_path)? {
        let bindings: crate::data_import::Bindings = serde_json::from_slice(&raw)?;
        if bindings.schema_version != 1 || bindings.generation == 0 {
            bail!("用户资料绑定schema或代次不支持");
        }
        let current = bindings.current.context("活动资料绑定缺失")?;
        model::validate_component(&current.profile_id)?;
        if current.profile_schema_version != 1
            || registry.current.as_deref() != Some(&current.release_id)
            || current
                .environment_instance_ids
                .keys()
                .ne(current.environment_generations.keys())
            || current
                .environment_generations
                .values()
                .any(|generation| *generation == 0)
        {
            bail!("活动资料绑定与当前发布不一致");
        }
        let gui = registry
            .gui_binding(&current.release_id)
            .context("资料组合缺少GUI实例绑定")?;
        if current.environment_instance_ids.get("gui") != Some(&gui.instance_id)
            || current.environment_generations.get("gui") != Some(&gui.generation)
        {
            bail!("活动资料组合与GUI实例绑定不一致");
        }
        for (component, instance) in &current.environment_instance_ids {
            if !matches!(
                component.as_str(),
                "gui" | "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth"
            ) {
                bail!("活动资料组合包含未知环境组件");
            }
            model::validate_component(instance)?;
        }
        id = current.profile_id;
    }
    let directory = reader.root.join("profiles").join(&id);
    let descriptor = directory.join("profile.json");
    let raw = reader
        .optional(&descriptor)?
        .context("当前用户资料描述缺失")?;
    let value: Profile = serde_json::from_slice(&raw)?;
    if value.schema_version != 1 || value.id != id {
        bail!("用户资料描述与绑定不一致");
    }
    Ok(directory)
}

// 事务只看有界JSON身份和终态；既不验证事务保护树，也不执行恢复。正式启动仍核完整gate。
fn gate(reader: &mut Reader<'_>, path: &Path, terminals: &[&str]) -> Result<()> {
    let Some(value) = reader.json(path)? else {
        return Ok(());
    };
    if value["schema_version"] != 1 {
        bail!("事务元数据schema不支持，请使用完整检查诊断");
    }
    for field in ["root", "root_absolute"] {
        if let Some(root) = value.get(field) {
            if root.as_str() != Some(reader.root.to_string_lossy().as_ref()) {
                bail!("事务安装目录身份不一致");
            }
        }
    }
    if let Some(release) = value.get("release_id") {
        model::validate_release_id(release.as_str().context("事务发布身份无效")?)?;
    }
    let phase = value
        .get("status")
        .or_else(|| value.get("phase"))
        .and_then(Value::as_str)
        .context("事务状态字段缺失")?;
    if !terminals.contains(&phase) {
        bail!("安装目录有未完成或未知的事务状态（{phase}），请恢复或完整检查");
    }
    Ok(())
}

fn gates(reader: &mut Reader<'_>, issues: &mut Vec<SnapshotIssue>) {
    let result = (|| -> Result<()> {
        for (relative, terminals) in [
            ("state/base-python-repair.json", &["committed"][..]),
            ("state/profile-binding-intent.json", &["committed"][..]),
        ] {
            gate(reader, &reader.root.join(relative), terminals)?;
        }
        // 壳gate固定指向一个事务，仅读取其描述，不读取/校验EXE或保护目录。
        if let Some(value) = reader.json(&reader.root.join("updates/shell/active.json"))? {
            let transaction = value["transaction"]
                .as_str()
                .context("壳活动事务缺少身份")?;
            model::validate_component(transaction)?;
            if value["schema_version"] != 1
                || value["root_absolute"] != reader.root.to_string_lossy().as_ref()
            {
                bail!("壳活动事务身份不一致");
            }
            let intent = reader
                .root
                .join("updates/shell")
                .join(transaction)
                .join("intent.json");
            if !reader.present(&intent, false)? {
                bail!("壳活动事务记录缺失");
            }
            gate(reader, &intent, &["committed", "restored", "aborted"])?;
        }
        for path in reader.directory(&reader.root.join("state"))? {
            let name = path
                .file_name()
                .context("状态文件缺少名称")?
                .to_string_lossy();
            if name.starts_with("journal-") && path.extension().is_some_and(|ext| ext == "json") {
                gate(reader, &path, &["committed"])?;
            } else if name.starts_with("gui-source-")
                && path.extension().is_some_and(|ext| ext == "json")
            {
                gate(reader, &path, &["committed", "rolled_back"])?;
            }
        }
        for (relative, terminals) in [
            ("state/gui-registration", &["committed"][..]),
            ("state/gui-binding-switch", &["committed"][..]),
            ("state/gui-rebuild", &["committed", "orphaned"][..]),
        ] {
            for path in reader.directory(&reader.root.join(relative))? {
                if path.extension().is_none_or(|ext| ext != "json") {
                    bail!("事务目录含未知项目，请使用完整检查诊断");
                }
                gate(reader, &path, terminals)?;
            }
        }
        Ok(())
    })();
    if let Err(error) = result {
        issues.push(issue(
            "pending_or_invalid_transaction",
            format!("{error:#}"),
            None,
        ));
    }
}

/// 与完整Report独立；没有健康布尔或缓存授权。调用不持有Engine锁，不访问运行中的服务。
pub fn read(root: &Path) -> Result<InstallationSnapshot> {
    model::validate_storage_directory(root)?;
    let mut reader = Reader {
        root,
        remaining: MAX_TOTAL_BYTES,
        records: 0,
    };
    let mut issues = Vec::new();
    let mut workspace = "missing";
    match reader.optional(&root.join(".launcher-workspace")) {
        Ok(Some(raw)) if raw == model::WORKSPACE_MARKER.as_bytes() => workspace = "managed",
        Ok(Some(_)) => {
            workspace = "invalid";
            issues.push(issue(
                "workspace_marker_invalid",
                "安装目录标记不匹配，请保留目录并检查。",
                None,
            ));
        }
        Ok(None) => {
            if reader.present(root, true)? && fs::read_dir(root)?.next().is_some() {
                workspace = "invalid";
                issues.push(issue(
                    "workspace_marker_missing",
                    "非空目录缺少启动器标记，请选择安装目录或完整检查。",
                    None,
                ));
            }
        }
        Err(error) => {
            workspace = "invalid";
            issues.push(issue(
                "workspace_marker_invalid",
                format!("{error:#}"),
                None,
            ));
        }
    }
    let catalog = match Catalog::for_workspace(root) {
        Ok(catalog) => catalog,
        Err(error) => {
            issues.push(issue(
                "catalog_invalid",
                format!("发布目录需要诊断：{error:#}"),
                None,
            ));
            Catalog::embedded()?
        }
    };
    let registry_path = root.join("state/registry.json");
    let mut registry_raw = None;
    let registry = (|| -> Result<Registry> {
        registry_raw = reader.optional(&registry_path)?;
        let registry: Registry = registry_raw
            .as_ref()
            .map(|raw| serde_json::from_slice(raw))
            .transpose()?
            .unwrap_or_default();
        registry.validate()?;
        Ok(registry)
    })();
    let registry = match registry {
        Ok(registry) => registry,
        Err(error) => {
            workspace = "invalid";
            issues.push(issue(
                "registry_invalid",
                format!("安装登记异常，未修改原记录：{error:#}"),
                Some(&registry_path),
            ));
            Registry::default()
        }
    };
    if registry.base_python_pending.is_some() {
        issues.push(issue(
            "base_python_pending",
            "基础Python有未完成恢复操作，请恢复原操作。",
            Some(&registry_path),
        ));
    }
    let recipe = crate::recipe::GuiRecipe::embedded()?;
    let mut versions = Vec::new();
    for release in catalog.releases() {
        let current = registry.current.as_deref() == Some(&release.id);
        let registration = registry
            .installed
            .iter()
            .find(|entry| entry.release_id == release.id);
        let mut version_issues = Vec::new();
        let receipt_path = root.join("releases").join(&release.id).join("release.json");
        let receipt = (|| -> Result<bool> {
            let Some(raw) = reader.optional(&receipt_path)? else {
                return Ok(false);
            };
            let receipt: ReleaseReceipt = serde_json::from_slice(&raw)?;
            if receipt.schema_version != 1 || receipt.release != *release {
                bail!("发布凭据与可信发布身份不匹配");
            }
            Ok(true)
        })();
        let installed = match receipt {
            Ok(installed) => installed,
            Err(error) => {
                version_issues.push(issue(
                    "release_receipt_invalid",
                    format!("{error:#}"),
                    Some(&receipt_path),
                ));
                false
            }
        };
        if registration.is_some() && !installed {
            version_issues.push(issue(
                "release_receipt_missing",
                "已登记版本的发布凭据缺失或异常。",
                Some(&receipt_path),
            ));
        }
        if installed && registration.is_none() {
            version_issues.push(issue(
                "release_registration_missing",
                "版本目录存在但缺少安装登记，请完整检查或恢复登记。",
                Some(&receipt_path),
            ));
        }
        let mut source_present = false;
        let mut environment_present = false;
        if installed || registration.is_some() {
            let present = (|| -> Result<()> {
                let app = root.join("releases").join(&release.id).join("app");
                source_present = reader.present(&app, true)?;
                for relative in &release.required_files {
                    source_present &= reader.present(&app.join(relative), false)?;
                }
                if !source_present {
                    bail!("主程序源码或网页必要入口缺失，请完整检查");
                }
                let environment = match registration.and_then(|entry| entry.gui.as_ref()) {
                    Some(binding) => {
                        inspect_binding(&mut reader, release, binding)?;
                        model::environment_path(
                            root,
                            &release.id,
                            &binding.instance_id,
                            binding.storage_version,
                        )?
                    }
                    None => root.join("environments").join(&release.id).join("gui"),
                };
                environment_present = reader.present(&environment, true)?
                    && reader.present(&environment.join("Scripts/python.exe"), false)?
                    && reader.present(&environment.join("pyvenv.cfg"), false)?;
                if !environment_present {
                    bail!("主程序环境或解释器入口缺失，请完整检查或安装");
                }
                if !reader.present(&root.join("tools/uv.exe"), false)? {
                    bail!("基础uv工具入口缺失，请完整检查");
                }
                let python = root
                    .join("python")
                    .join(&release.python)
                    .join(format!("cpython-{}-windows-x86_64-none", release.python))
                    .join("python.exe");
                if !reader.present(&python, false)? {
                    bail!("基础Python解释器入口缺失，请完整检查");
                }
                Ok(())
            })();
            if let Err(error) = present {
                version_issues.push(issue(
                    "installation_structure_attention",
                    format!("{error:#}"),
                    None,
                ));
            }
        }
        for entry in &mut version_issues {
            entry.release_id = Some(release.id.clone());
        }
        versions.push(InstallationVersionView {
            id: release.id.clone(),
            channel: release.channel.clone(),
            version: release.version.clone(),
            commit: release.commit.clone(),
            download_bytes: release.archive.bytes,
            source_bytes: release.archive.unpacked_bytes,
            installed,
            source_present,
            environment_bound: registry.gui_binding(&release.id).is_some(),
            environment_present,
            current,
            known_good: registration.is_some_and(|entry| entry.healthy_at.is_some()),
            managed_recipe: release.environment_recipe == "gui-cp310-win-x64-v1",
            support: release_support(release, &recipe),
            structure: if !version_issues.is_empty() {
                "attention"
            } else if installed {
                "present"
            } else {
                "missing"
            },
            issues: version_issues,
        });
    }
    if registry
        .current
        .as_ref()
        .is_some_and(|id| catalog.release(id).is_err())
    {
        issues.push(issue(
            "current_release_unknown",
            "当前发布不在可信发布目录中，请完整检查。",
            None,
        ));
    }
    let profile_path = if registry.current.is_some() {
        match profile(&mut reader, &registry) {
            Ok(path) => Some(path.to_string_lossy().into()),
            Err(error) => {
                issues.push(issue(
                    "profile_binding_invalid",
                    format!("用户资料绑定需要诊断：{error:#}"),
                    None,
                ));
                None
            }
        }
    } else {
        None
    };
    if workspace == "managed" {
        gates(&mut reader, &mut issues);
    }
    match reader.optional(&registry_path) {
        Ok(after) if after == registry_raw => {}
        _ => issues.push(issue(
            "metadata_changed",
            "读取期间安装登记发生变化，请刷新安装概况。",
            Some(&registry_path),
        )),
    }
    let start_available = workspace == "managed"
        && issues.is_empty()
        && versions.iter().any(|version| {
            version.current
                && version.installed
                && version.structure == "present"
                && version.support.source_supported
        });
    Ok(InstallationSnapshot {
        root: root.to_string_lossy().into(),
        verification: "not_run",
        workspace,
        current_release: registry.current,
        previous_known_good: registry.previous_known_good,
        profile_path,
        start_available,
        versions,
        issues,
    })
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct Fixture {
        root: PathBuf,
        release: Release,
    }
    impl Fixture {
        fn empty() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            Self {
                root: std::env::temp_dir()
                    .join(format!("nt-quick-install-{}-{nonce}", std::process::id())),
                release: Catalog::embedded().unwrap().releases()[0].clone(),
            }
        }
        fn write(&self, relative: impl AsRef<Path>, bytes: impl AsRef<[u8]>) {
            let path = self.root.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, bytes).unwrap();
        }
        fn json(&self, relative: impl AsRef<Path>, value: &impl Serialize) {
            self.write(relative, serde_json::to_vec(value).unwrap());
        }
        fn installed() -> Self {
            let fixture = Self::empty();
            fixture.write(".launcher-workspace", model::WORKSPACE_MARKER);
            fixture.json("state/registry.json", &serde_json::json!({
                "schema_version":1,"profile_schema_version":1,"current":fixture.release.id,
                "previous_known_good":null,"installed":[{"release_id":fixture.release.id,"healthy_at":1}]
            }));
            fixture.json(
                format!("releases/{}/release.json", fixture.release.id),
                &ReleaseReceipt::new(&fixture.release),
            );
            for relative in &fixture.release.required_files {
                // 有意使用错误源码内容：快概况只表明入口存在，不能当完整性证明。
                fixture.write(
                    Path::new("releases")
                        .join(&fixture.release.id)
                        .join("app")
                        .join(relative),
                    b"not trusted source",
                );
            }
            fixture.write(
                format!("environments/{}/gui/Scripts/python.exe", fixture.release.id),
                b"not executable",
            );
            fixture.write(
                format!("environments/{}/gui/pyvenv.cfg", fixture.release.id),
                b"placeholder",
            );
            fixture.write("tools/uv.exe", b"not executable");
            fixture.write(
                "python/3.10.19/cpython-3.10.19-windows-x86_64-none/python.exe",
                b"not executable",
            );
            fixture.json("profiles/default/profile.json", &Profile::default());
            fixture
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            if self.root.exists() {
                fs::remove_dir_all(&self.root).unwrap();
            }
        }
    }
    fn tree(root: &Path) -> BTreeMap<PathBuf, Option<Vec<u8>>> {
        fn walk(root: &Path, path: &Path, result: &mut BTreeMap<PathBuf, Option<Vec<u8>>>) {
            if path.is_dir() {
                result.insert(path.strip_prefix(root).unwrap().into(), None);
                for entry in fs::read_dir(path).unwrap() {
                    walk(root, &entry.unwrap().path(), result);
                }
            } else {
                result.insert(
                    path.strip_prefix(root).unwrap().into(),
                    Some(fs::read(path).unwrap()),
                );
            }
        }
        let mut result = BTreeMap::new();
        walk(root, root, &mut result);
        result
    }

    #[test]
    fn missing_workspace_is_reported_without_creating_any_files() {
        let fixture = Fixture::empty();
        let result = read(&fixture.root).unwrap();
        assert_eq!(result.workspace, "missing");
        assert_eq!(result.verification, "not_run");
        assert!(!result.start_available);
        assert!(result
            .versions
            .iter()
            .all(|version| version.structure == "missing"));
        assert!(result
            .versions
            .iter()
            .all(|version| !version.environment_bound && !version.environment_present));
        assert!(!fixture.root.exists());
    }

    #[test]
    fn installed_structure_never_runs_interpreters_or_confers_integrity() {
        let fixture = Fixture::installed();
        fixture.write("profiles/default/user_data/keep.txt", b"preserve user data");
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert!(
            result.start_available,
            "{}",
            serde_json::to_string(&result).unwrap()
        );
        assert!(
            result
                .versions
                .iter()
                .find(|version| version.current)
                .unwrap()
                .source_present
        );
        // 旧布局的环境入口存在也不会捏造实例绑定。
        let current = result
            .versions
            .iter()
            .find(|version| version.current)
            .unwrap();
        assert!(!current.environment_bound);
        assert!(current.environment_present);
        let json = serde_json::to_value(result).unwrap();
        assert_eq!(json["verification"], "not_run");
        assert!(json.get("healthy").is_none() && json.get("source").is_none());
        assert!(json["versions"][0].get("source_ok").is_none());
        assert!(json["versions"][0].get("environment_ok").is_none());
        assert_eq!(tree(&fixture.root), before);
        // 快概况放行的虚假可执行文件仍被正式启动前可信源码检查拦截。
        let layout = model::Layout::new(&fixture.root, &fixture.release.id).unwrap();
        assert!(super::super::verify_source(&layout, &fixture.release).is_err());
    }

    #[test]
    fn malformed_registry_remains_diagnosable_and_byte_identical() {
        let fixture = Fixture::installed();
        fixture.write("state/registry.json", b"{broken registry");
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert_eq!(result.workspace, "invalid");
        assert!(!result.start_available);
        assert!(result
            .issues
            .iter()
            .any(|issue| issue.code == "registry_invalid"));
        assert_eq!(tree(&fixture.root), before);
    }

    #[test]
    fn wrong_release_receipt_and_missing_critical_entry_are_not_ready() {
        let fixture = Fixture::installed();
        let receipt = format!("releases/{}/release.json", fixture.release.id);
        let mut changed = fixture.release.clone();
        changed.archive.sha256 = "0".repeat(64);
        fixture.json(&receipt, &ReleaseReceipt::new(&changed));
        let result = read(&fixture.root).unwrap();
        assert!(!result.start_available);
        assert!(result.versions[0]
            .issues
            .iter()
            .any(|issue| issue.code == "release_receipt_invalid"));
        fixture.json(&receipt, &ReleaseReceipt::new(&fixture.release));
        fs::remove_file(fixture.root.join(format!(
            "environments/{}/gui/Scripts/python.exe",
            fixture.release.id
        )))
        .unwrap();
        let result = read(&fixture.root).unwrap();
        assert!(!result.start_available);
        assert!(!result.versions[0].environment_present);
        assert!(!result.versions[0].environment_bound);
    }

    #[test]
    fn unknown_or_pending_transactions_block_attempt_without_recovering() {
        let fixture = Fixture::installed();
        fixture.json(
            "state/profile-binding-intent.json",
            &serde_json::json!({
                "schema_version":1,"root_absolute":fixture.root,"status":"committing"
            }),
        );
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert!(!result.start_available);
        assert!(result
            .issues
            .iter()
            .any(|issue| issue.code == "pending_or_invalid_transaction"));
        assert_eq!(tree(&fixture.root), before);
        fixture.json(
            "state/profile-binding-intent.json",
            &serde_json::json!({"schema_version":99,"status":"committed"}),
        );
        assert!(!read(&fixture.root).unwrap().start_available);
    }

    #[test]
    fn bound_instance_identity_or_generation_mismatch_is_visible() {
        let fixture = Fixture::installed();
        let binding = EnvironmentBinding {
            instance_id: "g0123456789abcdef".into(),
            storage_version: 1,
            recipe_id: "gui-cp310-win-x64-v1".into(),
            recipe_sha256: "1".repeat(64),
            generation: 2,
        };
        fixture.json("state/registry.json", &serde_json::json!({
            "schema_version":2,"profile_schema_version":1,"current":fixture.release.id,
            "previous_known_good":null,"installed":[{"release_id":fixture.release.id,"healthy_at":1,"gui":binding}]
        }));
        fixture.json(format!("state/instances/{}.json", binding.instance_id), &serde_json::json!({
            "schema_version":2,"component":"gui","instance_id":binding.instance_id,"storage_version":1,
            "release_id":fixture.release.id,"root_absolute":fixture.root,"recipe_id":binding.recipe_id,
            "recipe_sha256":binding.recipe_sha256,"generation":1,"validated_generation":1,"dirty":false,
            "pending":null,"base_python_pending":null
        }));
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert!(!result.start_available);
        assert_eq!(result.versions[0].structure, "attention");
        assert!(result.versions[0].environment_bound);
        assert!(!result.versions[0].environment_present);
        assert!(result.versions[0]
            .issues
            .iter()
            .any(|issue| issue.message.contains("身份或绑定代次")));
        assert_eq!(tree(&fixture.root), before);

        // 修正元数据代次后，绑定仍在、但新布局目录缺失：不能误当无绑定安装。
        fixture.json(format!("state/instances/{}.json", binding.instance_id), &serde_json::json!({
            "schema_version":2,"component":"gui","instance_id":binding.instance_id,"storage_version":1,
            "release_id":fixture.release.id,"root_absolute":fixture.root,"recipe_id":binding.recipe_id,
            "recipe_sha256":binding.recipe_sha256,"generation":2,"validated_generation":2,"dirty":false,
            "pending":null,"base_python_pending":null
        }));
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert!(result.versions[0].environment_bound);
        assert!(!result.versions[0].environment_present);
        assert!(!result.start_available);
        assert!(result.versions[0]
            .issues
            .iter()
            .any(|issue| issue.message.contains("环境或解释器入口缺失")));
        assert_eq!(tree(&fixture.root), before);

        fixture.write(
            format!("e/{}/Scripts/python.exe", binding.instance_id),
            b"not executable",
        );
        fixture.write(
            format!("e/{}/pyvenv.cfg", binding.instance_id),
            b"placeholder",
        );
        let before = tree(&fixture.root);
        let result = read(&fixture.root).unwrap();
        assert!(result.versions[0].environment_bound);
        assert!(result.versions[0].environment_present);
        assert!(result.start_available);
        assert_eq!(tree(&fixture.root), before);
    }
}
