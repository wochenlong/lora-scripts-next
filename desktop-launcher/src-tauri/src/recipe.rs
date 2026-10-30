//! 固定 CPython/Windows GUI 候选配方；仅声明已观测制品身份。
//! resolved-closure-superset 不声明每个包都必要，许可证摘要不构成法律批准。
use crate::model::{self, Catalog, UvAsset};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

const RECIPE_ID: &str = "gui-cp310-win-x64-v1";
const MAX_RECIPE_BYTES: usize = 250 * 1024;
const MAX_ASSET_BYTES: u64 = 512 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 1024 * 1024 * 1024;
const EMBEDDED_LOCK: &str = include_str!("../../catalog/gui-cp310-win-x64-v1.lock");

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct GuiRecipe {
    pub schema_version: u32,
    pub id: String,
    pub candidate_only: bool,
    pub source_commit: String,
    pub closure_scope: String,
    pub platform: String,
    pub implementation: String,
    pub abi: String,
    pub python: PythonAsset,
    pub tool_uv: UvAsset,
    pub requirements: Requirements,
    pub frontend: BundledFrontend,
    pub budget: Budget,
    pub wheels: Vec<WheelAsset>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RemoteAsset {
    pub filename: String,
    pub url: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PythonAsset {
    pub version: String,
    pub build: String,
    pub archive: RemoteAsset,
    pub exe_sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Requirements {
    pub input_sha256: String,
    pub input_bytes: u64,
    pub seed_tools_sha256: String,
    pub seed_tools_bytes: u64,
    pub lock_filename: String,
    pub lock_sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct BundledFrontend {
    pub source: String,
    pub filename: String,
    pub sha256: String,
    pub bytes: u64,
    pub unpacked_bytes: u64,
    pub files: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Budget {
    pub max_asset_bytes: u64,
    pub max_total_bytes: u64,
    pub wheel_bytes: u64,
    pub asset_bytes: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WheelAsset {
    pub name: String,
    pub version: String,
    pub url: String,
    pub filename: String,
    pub bytes: u64,
    pub sha256: String,
    pub compatible_tags: Vec<String>,
    pub marker: Option<String>,
    pub marker_matches_target: bool,
    pub requires_python: Vec<String>,
    pub licenses: LicenseSummary,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LicenseSummary {
    pub status: String,
    pub metadata_sha256: String,
    pub expressions: Vec<String>,
    pub classifiers: Vec<String>,
    pub declared_text_sha256: Vec<String>,
    pub files: Vec<LicenseFile>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LicenseFile {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

impl GuiRecipe {
    pub(crate) fn embedded() -> Result<Self> {
        let json = include_str!("../../catalog/gui-cp310-win-x64-v1.json");
        if json.len() > MAX_RECIPE_BYTES {
            bail!("GUI 配方元数据超出250KiB上限");
        }
        let recipe: Self = serde_json::from_str(json)?;
        recipe.validate()?;
        Ok(recipe)
    }

    pub(crate) fn id(&self) -> &str {
        &self.id
    }

    pub(crate) fn lock(&self) -> &'static str {
        EMBEDDED_LOCK
    }

    pub(crate) fn wheel(&self, name: &str) -> Option<&WheelAsset> {
        let normalized = normalize_name(name).ok()?;
        self.wheels.iter().find(|asset| asset.name == normalized)
    }

    /// 旧命名只在源码提交和解释器身份完全相同时兼容，不重绑其他发布版。
    pub(crate) fn matches_environment_recipe(&self, value: &str) -> bool {
        value == self.id
            || value
                == format!(
                    "gui-requirements-{}-python-{}-v1",
                    self.source_commit, self.python.version
                )
    }

    pub(crate) fn validate(&self) -> Result<()> {
        if self.schema_version != 1
            || self.id != RECIPE_ID
            || !self.candidate_only
            || self.closure_scope != "resolved-closure-superset"
            || self.platform != "windows-x86_64"
            || self.implementation != "cpython"
            || self.abi != "cp310"
            || self.python.version != "3.10.19"
            || self.python.build != "20260211"
            || self.wheels.len() != 81
        {
            bail!("GUI 配方 schema、候选身份、目标平台或闭包范围不受支持");
        }
        hex(&self.source_commit, 40)?;
        if self.budget.max_asset_bytes == 0
            || self.budget.max_asset_bytes > MAX_ASSET_BYTES
            || self.budget.max_total_bytes == 0
            || self.budget.max_total_bytes > MAX_TOTAL_BYTES
        {
            bail!("GUI 配方预算超出单资产512MiB或合计1GiB上限");
        }
        let python = &self.python.archive;
        asset(
            &python.filename,
            &python.sha256,
            python.bytes,
            self.budget.max_asset_bytes,
        )?;
        hex(&self.python.exe_sha256, 64)?;
        if python.filename
            != format!(
                "cpython-{}+{}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
                self.python.version, self.python.build
            )
            || python.url
                != format!(
                    "https://github.com/astral-sh/python-build-standalone/releases/download/{}/cpython-{}%2B{}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
                    self.python.build, self.python.version, self.python.build
                )
        {
            bail!("Python 归档与精确版本/BUILD不一致");
        }
        let catalog = Catalog::embedded()?;
        if !catalog
            .releases
            .iter()
            .any(|release| release.python == self.python.version && release.uv == self.tool_uv)
        {
            bail!("GUI 配方 uv 工具与现有发布清单不一致");
        }
        asset(
            "uv-x86_64-pc-windows-msvc.zip",
            &self.tool_uv.sha256,
            self.tool_uv.bytes,
            self.budget.max_asset_bytes,
        )?;
        hex(&self.tool_uv.exe_sha256, 64)?;
        hex(&self.requirements.input_sha256, 64)?;
        hex(&self.requirements.seed_tools_sha256, 64)?;
        if self.requirements.input_bytes == 0
            || self.requirements.input_bytes > MAX_RECIPE_BYTES as u64
            || self.requirements.seed_tools_bytes == 0
            || self.requirements.seed_tools_bytes > MAX_RECIPE_BYTES as u64
            || self.requirements.lock_filename != format!("{RECIPE_ID}.lock")
        {
            bail!("GUI 需求输入或锁文件身份无效");
        }
        asset(
            &self.frontend.filename,
            &self.frontend.sha256,
            self.frontend.bytes,
            self.budget.max_asset_bytes,
        )?;
        if self.frontend.source != "bundled"
            || !self.frontend.filename.ends_with(".zip")
            || self.frontend.unpacked_bytes == 0
            || self.frontend.unpacked_bytes > model::MAX_EXTRACT_BYTES
            || self.frontend.files == 0
            || self.frontend.files > 100_000
        {
            bail!("GUI 前端必须为有固定摘要的随包归档");
        }
        let mut names = BTreeSet::new();
        let mut filenames = BTreeSet::from([
            python.filename.to_ascii_lowercase(),
            "uv-x86_64-pc-windows-msvc.zip".into(),
            self.frontend.filename.to_ascii_lowercase(),
        ]);
        if filenames.len() != 3 {
            bail!("GUI 配方基础制品文件名重复");
        }
        let mut wheel_bytes = 0u64;
        for wheel in &self.wheels {
            if normalize_name(&wheel.name)? != wheel.name || !names.insert(&wheel.name) {
                bail!("GUI 配方包名不规范或重复");
            }
            if !filenames.insert(wheel.filename.to_ascii_lowercase()) {
                bail!("GUI 配方制品文件名重复（按Windows规则比较）");
            }
            wheel.validate(self.budget.max_asset_bytes)?;
            wheel_bytes = wheel_bytes
                .checked_add(wheel.bytes)
                .context("wheel 总长度溢出")?;
        }
        let total = wheel_bytes
            .checked_add(python.bytes)
            .and_then(|total| total.checked_add(self.tool_uv.bytes))
            .and_then(|total| total.checked_add(self.frontend.bytes))
            .context("GUI 配方总长度溢出")?;
        if wheel_bytes != self.budget.wheel_bytes
            || total != self.budget.asset_bytes
            || total > self.budget.max_total_bytes
        {
            bail!("GUI 配方制品合计与预算不一致");
        }
        self.validate_lock(EMBEDDED_LOCK)
    }

    /// 除整个文件摘要外，逐条要求唯一 name==version 与唯一完整 SHA256，
    /// 不接受额外选项、URL、marker、未固定依赖或漏项。
    pub(crate) fn validate_lock(&self, lock: &str) -> Result<()> {
        hex(&self.requirements.lock_sha256, 64)?;
        if lock.len() > MAX_RECIPE_BYTES || sha256(lock.as_bytes()) != self.requirements.lock_sha256
        {
            bail!("GUI 严格锁文件摘要不匹配");
        }
        let expected: BTreeSet<_> = self
            .wheels
            .iter()
            .map(|wheel| {
                format!(
                    "{}=={} --hash=sha256:{}",
                    wheel.name, wheel.version, wheel.sha256
                )
            })
            .collect();
        let mut seen = BTreeSet::new();
        for line in lock
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
        {
            if !expected.contains(line) || !seen.insert(line) {
                bail!("GUI 严格锁存在额外选项、重复项或不匹配的制品");
            }
        }
        if seen.len() != self.wheels.len() {
            bail!("GUI 严格锁未覆盖完整 wheel 闭包");
        }
        Ok(())
    }
}

impl WheelAsset {
    fn validate(&self, limit: u64) -> Result<()> {
        asset(&self.filename, &self.sha256, self.bytes, limit)?;
        if self.version.is_empty()
            || !self
                .version
                .starts_with(|character: char| character.is_ascii_digit())
            || !self
                .version
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b".+_!".contains(&byte))
        {
            bail!("wheel 版本不是固定可识别身份");
        }
        let parts: Vec<_> = self
            .filename
            .strip_suffix(".whl")
            .context("配方只接受wheel")?
            .split('-')
            .collect();
        if !(parts.len() == 5 || parts.len() == 6)
            || normalize_name(parts[0])? != self.name
            || parts[1] != self.version
            || (parts.len() == 6
                && (!parts[2].starts_with(|character: char| character.is_ascii_digit())
                    || !parts[2]
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')))
        {
            bail!("wheel 文件名与包身份不一致");
        }
        if parts[parts.len() - 3..].iter().any(|part| {
            part.split('.').any(|tag| {
                tag.is_empty()
                    || !tag
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
            })
        }) {
            bail!("wheel 文件名标签格式无效");
        }
        let url = reqwest::Url::parse(&self.url)?;
        if url.scheme() != "https"
            || url.host_str() != Some("files.pythonhosted.org")
            || url.port().is_some()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || !url.path().starts_with("/packages/")
            || url.path_segments().and_then(|mut parts| parts.next_back())
                != Some(self.filename.as_str())
        {
            bail!("wheel URL 不在固定HTTPS制品来源白名单内");
        }
        let mut compatible = BTreeSet::new();
        for python in parts[parts.len() - 3].split('.') {
            for abi in parts[parts.len() - 2].split('.') {
                for platform in parts[parts.len() - 1].split('.') {
                    if compatible_tag(python, abi, platform) {
                        compatible.insert(format!("{python}-{abi}-{platform}"));
                    }
                }
            }
        }
        if compatible.is_empty()
            || compatible.into_iter().collect::<Vec<_>>() != self.compatible_tags
        {
            bail!("wheel 标签与CPython3.10/Windows AMD64不兼容或声明不一致");
        }
        let license = &self.licenses;
        if license.status != "metadata_and_files_collected_not_legal_approval" {
            bail!("许可证摘要不得升级为法律批准事实");
        }
        hex(&license.metadata_sha256, 64)?;
        for hash in &license.declared_text_sha256 {
            hex(hash, 64)?;
        }
        let mut paths = BTreeSet::new();
        for file in &license.files {
            if file.path.len() > 1024 || file.path.contains('\\') {
                bail!("许可证归档路径无效");
            }
            for component in file.path.split('/') {
                model::validate_component(component)?;
            }
            hex(&file.sha256, 64)?;
            if file.bytes == 0
                || file.bytes > MAX_ASSET_BYTES
                || !paths.insert(file.path.to_ascii_lowercase())
            {
                bail!("许可证文件长度或路径身份无效");
            }
        }
        Ok(())
    }
}

fn compatible_tag(python: &str, abi: &str, platform: &str) -> bool {
    match (abi, platform) {
        ("cp310", "win_amd64") => python == "cp310",
        ("abi3", "win_amd64") => python
            .strip_prefix("cp3")
            .and_then(|minor| minor.parse::<u8>().ok())
            .is_some_and(|minor| (2..=10).contains(&minor)),
        ("none", "win_amd64" | "any") => {
            python == "cp310"
                || python == "py3"
                || python
                    .strip_prefix("py3")
                    .and_then(|minor| minor.parse::<u8>().ok())
                    .is_some_and(|minor| minor <= 10)
        }
        _ => false,
    }
}

fn normalize_name(value: &str) -> Result<String> {
    if value.is_empty()
        || !value.starts_with(|character: char| character.is_ascii_alphanumeric())
        || !value.ends_with(|character: char| character.is_ascii_alphanumeric())
    {
        bail!("Python 包名必须由ASCII字母/数字和中间分隔符组成");
    }
    let mut normalized = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() {
            normalized.push(byte.to_ascii_lowercase() as char);
        } else if b"-_.".contains(&byte) {
            if !normalized.ends_with('-') {
                normalized.push('-');
            }
        } else {
            bail!("Python 包名包含非法字符");
        }
    }
    Ok(normalized)
}

fn asset(filename: &str, hash: &str, bytes: u64, limit: u64) -> Result<()> {
    model::validate_component(filename)?;
    hex(hash, 64)?;
    if bytes == 0 || bytes > limit {
        bail!("GUI 配方资产长度超出明确预算");
    }
    Ok(())
}

fn hex(value: &str, length: usize) -> Result<()> {
    if value.len() != length
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        bail!("GUI 配方摘要或提交必须为固定长度的小写十六进制");
    }
    Ok(())
}

fn sha256(value: &[u8]) -> String {
    format!("{:x}", Sha256::digest(value))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_recipe_matches_observed_closure_and_strict_lock() {
        let recipe = GuiRecipe::embedded().unwrap();
        assert_eq!(recipe.id(), RECIPE_ID);
        assert_eq!(recipe.wheels.len(), 81);
        assert_eq!(recipe.budget.wheel_bytes, 378_332_343);
        assert_eq!(recipe.budget.asset_bytes, 426_586_132);
        assert_eq!(recipe.wheel("ONNXRuntime_GPU").unwrap().bytes, 244_505_340);
        assert!(recipe.matches_environment_recipe(&format!(
            "gui-requirements-{}-python-3.10.19-v1",
            recipe.source_commit
        )));
        assert!(!recipe.matches_environment_recipe(&format!(
            "gui-requirements-{}-python-3.10.19-v1",
            "0".repeat(40)
        )));
        recipe.validate_lock(recipe.lock()).unwrap();
    }

    #[test]
    fn unknown_recipe_schema_or_fields_and_unapproved_frontend_source_are_rejected() {
        let raw = include_str!("../../catalog/gui-cp310-win-x64-v1.json");
        let mut schema: GuiRecipe = serde_json::from_str(raw).unwrap();
        schema.schema_version = 999;
        assert!(schema.validate().is_err());
        let mut field: serde_json::Value = serde_json::from_str(raw).unwrap();
        field["future_field"] = true.into();
        assert!(serde_json::from_value::<GuiRecipe>(field).is_err());
        let mut frontend = GuiRecipe::embedded().unwrap();
        frontend.frontend.source = "https://example.com/not-published.zip".into();
        assert!(frontend.validate().is_err());
    }

    #[test]
    fn lock_rejects_tampering_even_if_a_new_checksum_is_supplied() {
        let original = GuiRecipe::embedded().unwrap();
        let first = original
            .lock()
            .lines()
            .find(|line| !line.starts_with('#'))
            .unwrap();
        for lock in [
            format!(
                "{}\n--index-url https://example.com/simple\n",
                original.lock()
            ),
            format!("{}\n{first}\n", original.lock()),
            original.lock().replace(first, ""),
            original.lock().replace("absl-py==2.5.1", "absl-py>=2.5.1"),
        ] {
            assert!(original.validate_lock(&lock).is_err());
            let mut with_checksum = original.clone();
            with_checksum.requirements.lock_sha256 = sha256(lock.as_bytes());
            assert!(with_checksum.validate_lock(&lock).is_err());
        }
    }

    #[test]
    fn duplicate_identity_host_tag_and_budget_changes_are_rejected() {
        let original = GuiRecipe::embedded().unwrap();
        let mut duplicate = original.clone();
        duplicate.wheels[1].name = duplicate.wheels[0].name.clone();
        assert!(duplicate.validate().is_err());
        let mut host = original.clone();
        host.wheels[0].url = host.wheels[0].url.replace(
            "files.pythonhosted.org",
            "files.pythonhosted.org.example.com",
        );
        assert!(host.validate().is_err());
        let mut tag = original.clone();
        tag.wheels[0].compatible_tags = vec!["cp311-cp311-win_amd64".into()];
        assert!(tag.validate().is_err());
        let mut budget = original;
        budget.budget.max_total_bytes = budget.budget.asset_bytes - 1;
        assert!(budget.validate().is_err());
    }
}
