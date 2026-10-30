//! 补登记的独立信任根：固定归档索引、固定uv生成控制；不依赖缓存或本地RECORD授信。
use crate::{
    model::{self, Layout, Release},
    operations::CancelToken,
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::Read,
    path::{Path, PathBuf},
};

const INDEX: &[u8] = include_bytes!("../../catalog/gui-cp310-installed-files-v2.json");
const INDEX_SHA: &str = "92e6e98081506d5022ded8bf5ab7d6f30e80d2d20b7bcfe76d248fffadd94bcb";
const MANAGED_VENV: &[u8] = include_bytes!("../../catalog/gui-cp310-managed-venv-v1.json");
const MANAGED_VENV_SHA: &str = "eac53df7da3d94c78d39501bd4e3e19713567b54762b67ee4921b1419184dfdb";
const RECIPE_SHA: &str = "4a513405052a63b34ef854bde95506693a03db716b64856bc33e0b925f6574ca";
const MAX_FILE: u64 = 512 * 1024 * 1024;
const MAX_TREE: u64 = 2 * 1024 * 1024 * 1024;
pub(crate) fn trusted_index_sha256() -> &'static str {
    INDEX_SHA
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrustedEnvironment {
    pub environment: PathBuf,
    pub recipe_sha256: String,
    pub trusted_index_sha256: String,
    pub files: u64,
    pub bytes: u64,
    pub closure_sha256: String,
}
#[derive(Deserialize)]
struct Index {
    schema_version: u32,
    recipe_id: String,
    recipe_sha256: String,
    uv_exe_sha256: String,
    python_archive_sha256: String,
    controls: Vec<Control>,
    packages: Vec<Package>,
    entrypoint_controls: Vec<Entry>,
    entrypoint_pe_template_hex: String,
}
#[derive(Deserialize)]
struct Original {
    path: String,
    bytes: u64,
    sha256: String,
}
#[derive(Deserialize)]
struct Control {
    path: String,
    bytes: u64,
    sha256: String,
    kind: String,
    template: Option<String>,
}
#[derive(Deserialize)]
struct Package {
    name: String,
    version: String,
    archive_sha256: String,
    dist_info: String,
    originals: Vec<Original>,
}
#[derive(Deserialize)]
struct Entry {
    package: String,
    path: String,
    kind: u8,
    script_template: String,
}
#[derive(Deserialize)]
struct ManagedVenv {
    schema_version: u32,
    recipe_sha256: String,
    uv_exe_sha256: String,
    python_archive_sha256: String,
    template_sha256: String,
    template_hex: String,
    trampoline_kind: u8,
    mode: String,
    home_directory: String,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum VenvMode {
    LegacyPatch,
    ManagedMinorAlias,
}
fn pyvenv_config(home: &Path) -> Vec<u8> {
    format!("home = {}\nimplementation = CPython\nuv = 0.11.16\nversion_info = 3.10.19\ninclude-system-site-packages = false\n",home.display()).into_bytes()
}
fn managed_python_root(root: &Path) -> PathBuf {
    // Windows的PathBuf保留传入片段内的斜杠；按组件拼接才能匹配固定uv原生字节。
    root.join("python").join("3.10.19")
}
fn environment_python_path(environment: &Path) -> PathBuf {
    // 固定uv入口同时在PE资源与脚本中嵌入原生路径，整文件校验不能混用分隔符。
    environment.join("Scripts").join("python.exe")
}
fn select_venv_mode(root: &Path, bytes: &[u8]) -> Result<VenvMode> {
    let managed = managed_python_root(root);
    if bytes == pyvenv_config(&managed.join("cpython-3.10-windows-x86_64-none")) {
        Ok(VenvMode::ManagedMinorAlias)
    } else if bytes == pyvenv_config(&managed.join("cpython-3.10.19-windows-x86_64-none")) {
        Ok(VenvMode::LegacyPatch)
    } else {
        bail!("pyvenv.cfg不是固定uv已验证的完整五键合同");
    }
}
fn managed_template(recipe: &GuiRecipe) -> Result<Vec<u8>> {
    if hash(MANAGED_VENV) != MANAGED_VENV_SHA {
        bail!("受管Python启动器模板信任根身份不符");
    }
    let fixed: ManagedVenv = serde_json::from_slice(MANAGED_VENV)?;
    let template = decode_hex(&fixed.template_hex)?;
    if fixed.schema_version != 1
        || fixed.recipe_sha256 != RECIPE_SHA
        || fixed.uv_exe_sha256 != recipe.tool_uv.exe_sha256
        || fixed.python_archive_sha256 != recipe.python.archive.sha256
        || fixed.trampoline_kind != 2
        || fixed.mode != "managed_minor_alias"
        || fixed.home_directory != "cpython-3.10-windows-x86_64-none"
        || template.len() != 45568
        || hash(&template) != fixed.template_sha256
    {
        bail!("受管Python启动器模板与固定uv/Python/生成模式不符");
    }
    Ok(template)
}
/// 固定uv三资源解释器PE：整文件重建，仅同根已验证minor alias路径变化。
fn managed_interpreter_executable(template: &[u8], base_python: &str) -> Result<Vec<u8>> {
    if template.len() != 45568 {
        bail!("受管解释器PE模板长度不符");
    }
    let start = 43008usize;
    let old_raw = get32(template, 640)?;
    let mut output = template[..start].to_vec();
    let mut resource = template[start..start + 276].to_vec();
    let manifest_start = get32(template, start + 192)?
        .checked_sub(61440)
        .context("受管解释器manifest RVA无效")?;
    let manifest_size = get32(template, start + 196)?;
    let manifest = template
        .get(start + manifest_start..start + manifest_start + manifest_size)
        .context("受管解释器manifest越界")?;
    let kind = [2u8];
    for (entry, payload) in
        [160, 176, 192]
            .into_iter()
            .zip([base_python.as_bytes(), kind.as_slice(), manifest])
    {
        let count = (4 - resource.len() % 4) % 4;
        padding(&mut resource, count);
        let offset = resource.len();
        put32(&mut resource, entry, 61440 + offset)?;
        put32(&mut resource, entry + 4, payload.len())?;
        resource.extend(payload);
    }
    let count = (4 - resource.len() % 4) % 4;
    padding(&mut resource, count);
    if resource.len() > 4096 {
        bail!("受管解释器资源超出固定PE区间");
    }
    let new_raw = resource.len().div_ceil(512) * 512;
    put32(&mut output, 152, get32(template, 152)? + new_raw - old_raw)?;
    put32(&mut output, 276, resource.len())?;
    put32(&mut output, 632, resource.len())?;
    put32(&mut output, 640, new_raw)?;
    put32(&mut output, 684, start + new_raw)?;
    output.extend(&resource);
    padding(&mut output, new_raw - resource.len());
    output.extend(&template[start + old_raw..]);
    Ok(output)
}
enum Expected {
    Digest(u64, String),
    Exact(Vec<u8>),
    Metadata,
    Record,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn relative(value: &str) -> Result<PathBuf> {
    if value.len() > 4096 || value.contains('\\') {
        bail!("可信索引路径格式不支持");
    }
    let mut path = PathBuf::new();
    for part in value.split('/') {
        model::validate_component(part)?;
        path.push(part);
    }
    Ok(path)
}
fn add(map: &mut BTreeMap<PathBuf, Expected>, path: &str, expected: Expected) -> Result<()> {
    if map.insert(relative(path)?, expected).is_some() {
        bail!("可信索引路径冲突");
    }
    Ok(())
}
fn read(layout: &Layout, path: &Path, limit: u64, cancel: &CancelToken) -> Result<Vec<u8>> {
    cancel.check()?;
    layout.guard_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() || before.len() > limit {
        bail!("补登记验证只接受受限普通文件：{}", path.display());
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(1);
    }
    let mut input = options.open(path)?;
    let opened = input.metadata()?;
    if opened.len() != before.len() {
        bail!("补登记验证文件已变化");
    }
    let mut data = Vec::with_capacity(opened.len() as usize);
    let mut buffer = [0; 65536];
    loop {
        cancel.check()?;
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        if data.len() as u64 + count as u64 > limit {
            bail!("补登记文件读取超限");
        }
        data.extend_from_slice(&buffer[..count]);
    }
    layout.guard_path(path)?;
    let after = fs::symlink_metadata(path)?;
    let handle_after = input.metadata()?;
    if !after.is_file()
        || after.len() != data.len() as u64
        || opened.len() != after.len()
        || opened.modified().ok() != after.modified().ok()
        || opened.modified().ok() != handle_after.modified().ok()
    {
        bail!("补登记验证期间文件变化");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if (opened.dev(), opened.ino()) != (after.dev(), after.ino()) {
            bail!("验证文件被替换");
        }
    }
    Ok(data)
}

/// 固定 uv 在首次 pip 写入时生成的可选空锁；不是可执行文件或任意隐藏文件许可。
/// 来源为独立固定 uv + 原始 CPython + synthetic wheel 的离线控制复现。
fn runtime_control(
    layout: &Layout,
    environment: &Path,
    path: &Path,
    cancel: &CancelToken,
) -> Result<Option<Vec<u8>>> {
    if path != environment.join(".lock") {
        return Ok(None);
    }
    // limit=0 同时拒绝非空锁、目录和 reparse，绝不修改或清空现场。
    Ok(Some(read(layout, path, 0, cancel)?))
}
fn decode_hex(value: &str) -> Result<Vec<u8>> {
    if !value.len().is_multiple_of(2) {
        bail!("PE模板编码无效");
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair)?;
            Ok(u8::from_str_radix(text, 16)?)
        })
        .collect()
}
fn get32(bytes: &[u8], at: usize) -> Result<usize> {
    Ok(u32::from_le_bytes(bytes.get(at..at + 4).context("PE模板越界")?.try_into()?) as usize)
}
fn put32(bytes: &mut [u8], at: usize, value: usize) -> Result<()> {
    bytes
        .get_mut(at..at + 4)
        .context("PE模板写越界")?
        .copy_from_slice(&u32::try_from(value)?.to_le_bytes());
    Ok(())
}
fn padding(output: &mut Vec<u8>, count: usize) {
    output.extend(b"PADDINGXXPADDING".iter().copied().cycle().take(count));
}
fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb88320 & (0u32.wrapping_sub(crc & 1)));
        }
    }
    !crc
}
fn u16s(output: &mut Vec<u8>, values: &[u16]) {
    for value in values {
        output.extend(value.to_le_bytes());
    }
}
fn u32s(output: &mut Vec<u8>, values: &[u32]) {
    for value in values {
        output.extend(value.to_le_bytes());
    }
}
fn zip_script(main: &[u8]) -> Result<Vec<u8>> {
    let name = b"__main__.py";
    let length = u32::try_from(main.len())?;
    let crc = crc32(main);
    let mut output = Vec::new();
    u32s(&mut output, &[0x04034b50]);
    u16s(&mut output, &[10, 2048, 0, 0, 33]);
    u32s(&mut output, &[crc, length, length]);
    u16s(&mut output, &[11, 0]);
    output.extend(name);
    output.extend(main);
    let central = u32::try_from(output.len())?;
    u32s(&mut output, &[0x02014b50]);
    u16s(&mut output, &[831, 10, 2048, 0, 0, 33]);
    u32s(&mut output, &[crc, length, length]);
    u16s(&mut output, &[11, 0, 0, 0, 0]);
    u32s(&mut output, &[0, 0]);
    output.extend(name);
    let central_length = u32::try_from(output.len())? - central;
    u32s(&mut output, &[0x06054b50]);
    u16s(&mut output, &[0, 0, 1, 1]);
    u32s(&mut output, &[central_length, central]);
    u16s(&mut output, &[0]);
    Ok(output)
}
/// 重建固定uv PE的全部字节，未知header/资源/尾部内容均不能通过。
fn entry_executable(template: &[u8], python: &str, main: &[u8], kind: u8) -> Result<Vec<u8>> {
    if template.len() != 46080 || !matches!(kind, 1 | 2) {
        bail!("入口模板身份不支持");
    }
    let start = 43008usize;
    let old_raw = get32(template, 640)?;
    let mut output = template[..start].to_vec();
    let mut resource = template[start..start + 356].to_vec();
    let manifest_start = get32(template, start + 240)?
        .checked_sub(61440)
        .context("资源RVA无效")?;
    let manifest_size = get32(template, start + 244)?;
    let manifest = template
        .get(start + manifest_start..start + manifest_start + manifest_size)
        .context("manifest越界")?;
    let archive = zip_script(main)?;
    let kind_byte = [kind];
    for (entry, payload) in [192, 208, 224, 240].into_iter().zip([
        python.as_bytes(),
        archive.as_slice(),
        kind_byte.as_slice(),
        manifest,
    ]) {
        let count = (4 - resource.len() % 4) % 4;
        padding(&mut resource, count);
        let offset = resource.len();
        put32(&mut resource, entry, 61440 + offset)?;
        put32(&mut resource, entry + 4, payload.len())?;
        resource.extend(payload);
    }
    let count = (4 - resource.len() % 4) % 4;
    padding(&mut resource, count);
    if resource.len() > 4096 {
        bail!("入口资源超出固定PE区间");
    }
    let new_raw = resource.len().div_ceil(512) * 512;
    put32(&mut output, 152, get32(template, 152)? + new_raw - old_raw)?;
    put32(&mut output, 276, resource.len())?;
    put32(&mut output, 632, resource.len())?;
    put32(&mut output, 640, new_raw)?;
    put32(&mut output, 684, start + new_raw)?;
    output.extend(&resource);
    padding(&mut output, new_raw - resource.len());
    output.extend(&template[start + old_raw..]);
    Ok(output)
}
fn record_relative(text: &str) -> Result<PathBuf> {
    if text.contains(['\\', ':']) || text.len() > 4096 {
        bail!("RECORD路径不支持");
    }
    let mut parts = vec!["Lib", "site-packages"];
    for part in text.split('/') {
        if part == ".." {
            parts.pop().context("RECORD越出环境")?;
        } else {
            model::validate_component(part)?;
            parts.push(part);
        }
    }
    if parts.is_empty() {
        bail!("RECORD指向环境根");
    }
    Ok(parts.iter().collect())
}
fn validate_record(
    data: &[u8],
    allowed: &BTreeSet<PathBuf>,
    required: &BTreeSet<PathBuf>,
) -> Result<()> {
    let text = std::str::from_utf8(data)?;
    let mut seen = BTreeSet::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split(',').collect();
        if fields.len() != 3 || fields.iter().any(|x| x.contains('"')) {
            bail!("固定uv RECORD格式无效");
        }
        let path = record_relative(fields[0])?;
        if !allowed.contains(&path) || !seen.insert(path) {
            bail!("RECORD包含未知或重复路径");
        }
    }
    if !required.is_subset(&seen) {
        bail!("RECORD遗漏必要原文件或生成项");
    }
    Ok(())
}
fn check_metadata(path: &Path, data: &[u8]) -> Result<()> {
    match path.file_name().and_then(|s| s.to_str()) {
        Some("INSTALLER") if data == b"uv" => Ok(()),
        Some("REQUESTED") if data.is_empty() => Ok(()),
        Some("direct_url.json" | "uv_cache.json") => {
            if data.len() > 16384 || !serde_json::from_slice::<serde_json::Value>(data)?.is_object()
            {
                bail!("安装器元数据不支持");
            }
            Ok(())
        }
        _ => bail!("安装器控制内容无效：{}", path.display()),
    }
}

pub(crate) fn verify(
    layout: &Layout,
    release: &Release,
    environment: &Path,
    cancel: &CancelToken,
) -> Result<TrustedEnvironment> {
    cancel.check()?;
    release.validate()?;
    let recipe = GuiRecipe::embedded()?;
    if hash(INDEX) != INDEX_SHA
        || hash(include_bytes!("../../catalog/gui-cp310-win-x64-v1.json")) != RECIPE_SHA
    {
        bail!("内置信任根身份不符");
    }
    let index: Index = serde_json::from_slice(INDEX)?;
    if index.schema_version != 1
        || index.recipe_id != recipe.id()
        || index.recipe_sha256 != RECIPE_SHA
        || index.uv_exe_sha256 != recipe.tool_uv.exe_sha256
        || index.python_archive_sha256 != recipe.python.archive.sha256
        || release.commit != recipe.source_commit
        || !recipe.matches_environment_recipe(&release.environment_recipe)
        || index.packages.len() != recipe.wheels.len()
    {
        bail!("可信索引与固定配方不符");
    }
    // 只接受两个既有实例命名空间；旧legacy裸gui目录无实例身份，不能重新解释。
    let compact = environment
        .strip_prefix(layout.root.join("e"))
        .ok()
        .and_then(|p| p.to_str());
    let compact_ok = compact.is_some_and(|id| model::validate_environment_storage(id, 1).is_ok());
    let legacy = layout
        .root
        .join("environments")
        .join(&release.id)
        .join("instances");
    let legacy_ok = environment
        .strip_prefix(&legacy)
        .ok()
        .is_some_and(|p| p.components().count() == 2 && p.file_name().is_some_and(|n| n == "gui"));
    if !compact_ok && !legacy_ok {
        bail!("登记目标不在固定实例命名空间");
    }
    layout.guard_path(environment)?;
    let env = environment.to_str().context("环境路径非UTF8")?;
    let python = environment_python_path(environment);
    let python = python.to_str().context("Python路径非UTF8")?;
    let mut expected = BTreeMap::new();
    let mut optional = BTreeSet::new();
    let mut package_sets = Vec::new();
    // 先核完整固定patch与受控minor junction，不能从pyvenv自述授信外来base路径。
    crate::python_integrity::verify(layout)?;
    let pyvenv_bytes = read(layout, &environment.join("pyvenv.cfg"), 4096, cancel)?;
    let mode = select_venv_mode(&layout.root, &pyvenv_bytes)?;
    let managed = managed_python_root(&layout.root);
    let home = match mode {
        VenvMode::LegacyPatch => managed.join("cpython-3.10.19-windows-x86_64-none"),
        VenvMode::ManagedMinorAlias => {
            let alias = managed.join("cpython-3.10-windows-x86_64-none");
            // python_integrity已逐项检查同根junction；absence不能靠精确字符串补信任。
            if fs::symlink_metadata(&alias).is_err() || !alias.is_dir() {
                bail!("受管minor alias缺失，拒绝动态启动器路径");
            }
            alias
        }
    };
    let interpreter = if mode == VenvMode::ManagedMinorAlias {
        let base = home.join("python.exe");
        let base = base.to_str().context("受管base路径非UTF8")?;
        Some(managed_interpreter_executable(
            &managed_template(&recipe)?,
            base,
        )?)
    } else {
        None
    };
    for control in &index.controls {
        let rule = if matches!(
            control.path.as_str(),
            "Scripts/python.exe" | "Scripts/pythonw.exe"
        ) && mode == VenvMode::ManagedMinorAlias
        {
            Expected::Exact(interpreter.as_ref().context("受管Python模板缺失")?.clone())
        } else {
            match control.kind.as_str() {
                "fixed" => Expected::Digest(control.bytes, control.sha256.clone()),
                "template" => Expected::Exact(
                    control
                        .template
                        .as_ref()
                        .context("控制模板缺失")?
                        .replace("{{ENVIRONMENT}}", env)
                        .replace("{{ENVIRONMENT_SLASH}}", &env.replace('\\', "/"))
                        .replace(
                            "{{ENVIRONMENT_NAME}}",
                            environment
                                .file_name()
                                .and_then(|s| s.to_str())
                                .context("环境名缺失")?,
                        )
                        .into_bytes(),
                ),
                "pyvenv_config" => Expected::Exact(pyvenv_config(&home)),
                _ => bail!("未知uv控制规则"),
            }
        };
        add(&mut expected, &control.path, rule)?;
    }
    let template = decode_hex(&index.entrypoint_pe_template_hex)?;
    for package in &index.packages {
        let wheel = recipe
            .wheels
            .iter()
            .find(|w| w.name == package.name)
            .context("索引包身份未知")?;
        if package.version != wheel.version || package.archive_sha256 != wheel.sha256 {
            bail!("索引wheel身份不符");
        }
        let mut required = BTreeSet::new();
        let mut allowed = BTreeSet::new();
        for file in &package.originals {
            let path = relative(&file.path)?;
            required.insert(path.clone());
            allowed.insert(path);
            add(
                &mut expected,
                &file.path,
                Expected::Digest(file.bytes, file.sha256.clone()),
            )?;
        }
        for name in [
            "RECORD",
            "INSTALLER",
            "REQUESTED",
            "direct_url.json",
            "uv_cache.json",
        ] {
            let path = format!("Lib/site-packages/{}/{name}", package.dist_info);
            let rel = relative(&path)?;
            allowed.insert(rel.clone());
            if matches!(name, "RECORD" | "INSTALLER") {
                required.insert(rel.clone());
            } else {
                optional.insert(rel.clone());
            }
            add(
                &mut expected,
                &path,
                if name == "RECORD" {
                    Expected::Record
                } else {
                    Expected::Metadata
                },
            )?;
        }
        for entry in index
            .entrypoint_controls
            .iter()
            .filter(|entry| entry.package == package.name)
        {
            let main = entry
                .script_template
                .replace("{{PYTHON}}", python)
                .into_bytes();
            let data = entry_executable(&template, python, &main, entry.kind)?;
            let path = relative(&entry.path)?;
            required.insert(path.clone());
            allowed.insert(path);
            add(&mut expected, &entry.path, Expected::Exact(data))?;
        }
        package_sets.push((
            relative(&format!("Lib/site-packages/{}/RECORD", package.dist_info))?,
            allowed,
            required,
        ));
    }
    let mut observed = BTreeMap::new();
    let mut aliases = BTreeSet::new();
    let mut total = 0u64;
    let mut stack = vec![environment.to_path_buf()];
    let mut nodes = 0usize;
    while let Some(directory) = stack.pop() {
        cancel.check()?;
        layout.guard_path(&directory)?;
        if !fs::symlink_metadata(&directory)?.is_dir() {
            bail!("环境根不是普通目录");
        }
        for item in fs::read_dir(&directory)? {
            cancel.check()?;
            nodes += 1;
            if nodes > 100_000 {
                bail!("环境节点超限");
            }
            let path = item?.path();
            layout.guard_path(&path)?;
            let rel = path.strip_prefix(environment)?.to_path_buf();
            let key = rel.to_string_lossy().replace('\\', "/").to_lowercase();
            if !aliases.insert(key) {
                bail!("环境含Windows大小写别名");
            }
            let meta = fs::symlink_metadata(&path)?;
            if let Some(data) = runtime_control(layout, environment, &path, cancel)? {
                observed.insert(rel, (data.len() as u64, hash(&data)));
                continue;
            }
            if meta.is_dir() {
                stack.push(path);
                continue;
            }
            if !meta.is_file() {
                bail!("环境含特殊文件");
            }
            let rule = expected
                .get(&rel)
                .with_context(|| format!("环境含未授权文件，保持原文件：{}", rel.display()))?;
            total = total.checked_add(meta.len()).context("验证字节数溢出")?;
            if total > MAX_TREE {
                bail!("GUI验证合计字节数超限");
            }
            let limit = if matches!(rule, Expected::Metadata | Expected::Record) {
                2 * 1024 * 1024
            } else {
                MAX_FILE
            };
            let data = read(layout, &path, limit, cancel)?;
            match rule {
                Expected::Digest(bytes, sha)
                    if *bytes != data.len() as u64 || hash(&data) != *sha =>
                {
                    bail!("固定原文件内容不符：{}", rel.display())
                }
                Expected::Exact(bytes) if *bytes != data => {
                    bail!("uv控制或入口内容不符：{}", rel.display())
                }
                Expected::Metadata => check_metadata(&rel, &data)?,
                _ => {}
            }
            observed.insert(rel, (data.len() as u64, hash(&data)));
        }
    }
    for path in expected.keys() {
        if !optional.contains(path) && !observed.contains_key(path) {
            bail!("可信闭包缺少必要文件：{}", path.display());
        }
    }
    for (path, allowed, required) in package_sets {
        validate_record(
            &read(layout, &environment.join(path), 2 * 1024 * 1024, cancel)?,
            &allowed,
            &required,
        )?;
    }
    let closure_sha256 = hash(&serde_json::to_vec(&observed)?);
    Ok(TrustedEnvironment {
        environment: environment.to_path_buf(),
        recipe_sha256: RECIPE_SHA.into(),
        trusted_index_sha256: INDEX_SHA.into(),
        files: observed.len() as u64,
        bytes: total,
        closure_sha256,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn index() -> Index {
        serde_json::from_slice(INDEX).unwrap()
    }
    #[test]
    fn managed_alias_template_reconstructs_fixed_uv_source_byte_for_byte() {
        let template = managed_template(&GuiRecipe::embedded().unwrap()).unwrap();
        let base =
            r"E:\NTRegCtrl\K1 控制\python\3.10.19\cpython-3.10-windows-x86_64-none\python.exe";
        assert_eq!(
            managed_interpreter_executable(&template, base).unwrap(),
            template
        );
        assert_eq!(hash(MANAGED_VENV), MANAGED_VENV_SHA);
        assert_eq!(
            hash(&template),
            "9f17b668858f146f5333efef86e8fcc7a93507f69c7234c71a33342f93a26813"
        );
    }
    #[cfg(windows)]
    #[test]
    fn managed_paths_match_independent_uv_native_configuration_and_interpreter_bytes() {
        let root = Path::new(r"E:\NTRegCtrl\K1 控制");
        // 独立固定uv控制案的原始输出；不可用被测路径拼接器生成期望值。
        let config = concat!(
            "home = E:\\NTRegCtrl\\K1 控制\\python\\3.10.19\\cpython-3.10-windows-x86_64-none\n",
            "implementation = CPython\nuv = 0.11.16\nversion_info = 3.10.19\n",
            "include-system-site-packages = false\n"
        );
        assert_eq!(config.len(), 176);
        assert_eq!(
            hash(config.as_bytes()),
            "26cba6ba77ffa2571ab4980316c433d8436442083bfe0da33f61cff980f457b0"
        );
        assert_eq!(
            select_venv_mode(root, config.as_bytes()).unwrap(),
            VenvMode::ManagedMinorAlias
        );
        let base = managed_python_root(root)
            .join("cpython-3.10-windows-x86_64-none")
            .join("python.exe");
        let template = managed_template(&GuiRecipe::embedded().unwrap()).unwrap();
        assert_eq!(
            managed_interpreter_executable(&template, base.to_str().unwrap()).unwrap(),
            template
        );
    }
    #[test]
    fn managed_alias_mode_cannot_authorize_foreign_home_extra_keys_or_patch_shim() {
        let root = Path::new(r"E:\Next Trainer");
        let managed = managed_python_root(root);
        assert_eq!(
            select_venv_mode(
                root,
                &pyvenv_config(&managed.join("cpython-3.10-windows-x86_64-none"))
            )
            .unwrap(),
            VenvMode::ManagedMinorAlias
        );
        assert_eq!(
            select_venv_mode(
                root,
                &pyvenv_config(&managed.join("cpython-3.10.19-windows-x86_64-none"))
            )
            .unwrap(),
            VenvMode::LegacyPatch
        );
        assert!(
            select_venv_mode(root, &pyvenv_config(&PathBuf::from(r"D:\foreign\python"))).is_err()
        );
        let mut extra = pyvenv_config(&managed.join("cpython-3.10-windows-x86_64-none"));
        extra.extend(b"extra = yes\n");
        assert!(select_venv_mode(root, &extra).is_err());
        let template = managed_template(&GuiRecipe::embedded().unwrap()).unwrap();
        let alias = managed_interpreter_executable(
            &template,
            managed
                .join("cpython-3.10-windows-x86_64-none/python.exe")
                .to_str()
                .unwrap(),
        )
        .unwrap();
        // patch-home模式继续绑定v2原复制EXE，不能因路径合法就接受未复现patch shim组合。
        let old = index()
            .controls
            .into_iter()
            .find(|c| c.path == "Scripts/python.exe")
            .unwrap();
        assert_ne!(hash(&alias), old.sha256);
        assert_ne!(alias.len() as u64, old.bytes);
    }
    #[test]
    fn managed_interpreter_reconstruction_binds_path_code_kind_and_all_trailing_bytes() {
        let template = managed_template(&GuiRecipe::embedded().unwrap()).unwrap();
        let base =
            r"E:\NTRegCtrl\K1 控制\python\3.10.19\cpython-3.10-windows-x86_64-none\python.exe";
        let expected = managed_interpreter_executable(&template, base).unwrap();
        assert_ne!(
            expected,
            managed_interpreter_executable(&template, &base.replace("K1 控制", "其它目录"))
                .unwrap()
        );
        let mut code = expected.clone();
        code[1024] ^= 1;
        assert_ne!(expected, code);
        let mut kind = expected.clone();
        let kind_offset = 43008 + get32(&kind, 43008 + 176).unwrap() - 61440;
        kind[kind_offset] = 1;
        assert_ne!(expected, kind);
        let mut tail = expected.clone();
        tail.extend(b"unknown");
        assert_ne!(expected, tail);
        assert!(managed_interpreter_executable(&template, &"x".repeat(5000)).is_err());
    }
    #[test]
    fn uv_runtime_lock_accepts_only_exact_empty_root_file_and_preserves_other_bytes() {
        let root = std::env::temp_dir().join(format!(
            "nt-runtime-lock-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let release = crate::model::Catalog::embedded().unwrap().releases()[0].clone();
        let layout = Layout::new(&root, &release.id).unwrap();
        let _lease = layout.prepare_workspace().unwrap();
        let environment = root.join("e/g3333333333333333");
        fs::create_dir_all(&environment).unwrap();
        let lock = environment.join(".lock");
        let cancel = CancelToken::new();
        fs::write(&lock, b"").unwrap();
        assert_eq!(
            runtime_control(&layout, &environment, &lock, &cancel).unwrap(),
            Some(vec![])
        );
        fs::write(&lock, b"untrusted").unwrap();
        assert!(runtime_control(&layout, &environment, &lock, &cancel).is_err());
        assert_eq!(fs::read(&lock).unwrap(), b"untrusted");
        for path in [
            environment.join("Lib/.lock"),
            environment.join(".lock.py"),
            environment.join(".LOCK"),
        ] {
            assert!(runtime_control(&layout, &environment, &path, &cancel)
                .unwrap()
                .is_none());
        }
        fs::remove_file(&lock).unwrap();
        fs::create_dir(&lock).unwrap();
        assert!(runtime_control(&layout, &environment, &lock, &cancel).is_err());
        // 保留专属测试根；无递归删除或修改生产环境。
    }
    #[test]
    fn index_binds_full_fixed_wheel_closure_and_uv_controls() {
        assert_eq!(hash(INDEX), INDEX_SHA);
        let index = index();
        let recipe = GuiRecipe::embedded().unwrap();
        assert_eq!(index.packages.len(), 81);
        assert_eq!(
            index
                .packages
                .iter()
                .map(|p| p.originals.len())
                .sum::<usize>(),
            12738
        );
        assert_eq!(index.controls.len(), 16);
        assert_eq!(index.entrypoint_controls.len(), 27);
        for p in &index.packages {
            let w = recipe.wheel(&p.name).unwrap();
            assert_eq!(p.version, w.version);
            assert_eq!(p.archive_sha256, w.sha256);
        }
    }
    #[test]
    fn uv_pe_reconstruction_matches_fixed_isolated_generation_byte_for_byte() {
        let index = index();
        let template = decode_hex(&index.entrypoint_pe_template_hex).unwrap();
        let entry = index
            .entrypoint_controls
            .iter()
            .find(|e| e.path == "Scripts/cffi-gen-src.exe")
            .unwrap();
        let python = r"E:\NTRegCtrl\a5-20261029-ctrl1\g0000000000000000\Scripts\python.exe";
        let main = entry.script_template.replace("{{PYTHON}}", python);
        assert_eq!(
            entry_executable(&template, python, main.as_bytes(), entry.kind).unwrap(),
            template
        );
    }
    #[cfg(windows)]
    #[test]
    fn entrypoint_paths_match_all_independent_uv_native_bytes() {
        // 固定uv/81原wheel独立控制案的27个完整PE哈希；不从待恢复环境取期望值。
        // 来源：k1-final-control-comparison.json c481c274…5a0cb3及其固定E控制输出，
        // registration-followup-20261029/diagnosis/entrypoint-path-diagnosis.json逐项复核。
        let environment = Path::new(r"E:\NTRegCtrl\K1 控制\e\g4444444444444444");
        let expected = [
            (
                "Scripts/cffi-gen-src.exe",
                "8835631bb0537da10ad300f6c8689bdb13c5ebce8977e1ea6549433d92740d6f",
            ),
            (
                "Scripts/coloredlogs.exe",
                "ca68090c26685cd9ddca3991bcc154481c100c15b52c7673a196d911bd7d41db",
            ),
            (
                "Scripts/f2py.exe",
                "9863a4387f9cf46a313996adf04a9d52aa603a9928855e8c747e99c1a0e8636b",
            ),
            (
                "Scripts/google-oauthlib-tool.exe",
                "5edfeae106b98d80b8d66896be61af6c28551e1448dceb79ada78e7f721b35ac",
            ),
            (
                "Scripts/hf.exe",
                "fa6a79a8eb52c73f54bb8f893a57e726d5a9c01de1737983e6d4054bb17f8aba",
            ),
            (
                "Scripts/httpx.exe",
                "9244fbd29a4070e1a45303392a45a6690dd800548be88e34f85391b177c73744",
            ),
            (
                "Scripts/huggingface-cli.exe",
                "f1c88d73127f847b174a78f2fe008005684db6ed0a449971a1dc9109b1d3075e",
            ),
            (
                "Scripts/humanfriendly.exe",
                "26fce549bc3e44ffcd8925c95913b9074a52784aab3133a5320ea594736a2040",
            ),
            (
                "Scripts/idna.exe",
                "4ed55a449c7cca877c5a004fa93cdfc342a6f16b4b7d1567942959d6f55dd55e",
            ),
            (
                "Scripts/isympy.exe",
                "80ead33c20d3bcdbd02ba1ae036f73dcce6b30bc32f7a533843e47dcc21c8c4f",
            ),
            (
                "Scripts/markdown-it.exe",
                "b1ea07c9734a43ed7eec3e123d8141ebe82d790f0abec0af01f970625c350e17",
            ),
            (
                "Scripts/markdown_py.exe",
                "6d7631e716862190f6c6a48824c92878338ae50595b030ff0a9a75a3a6ebd80e",
            ),
            (
                "Scripts/modelscope-hub.exe",
                "d9a529c65b3e34df90d8074a5af38c180d17ffdb9f116d9e5689d4a18f7d7cb6",
            ),
            (
                "Scripts/modelscope.exe",
                "d9a529c65b3e34df90d8074a5af38c180d17ffdb9f116d9e5689d4a18f7d7cb6",
            ),
            (
                "Scripts/ms-hub.exe",
                "d9a529c65b3e34df90d8074a5af38c180d17ffdb9f116d9e5689d4a18f7d7cb6",
            ),
            (
                "Scripts/ms.exe",
                "d9a529c65b3e34df90d8074a5af38c180d17ffdb9f116d9e5689d4a18f7d7cb6",
            ),
            (
                "Scripts/normalizer.exe",
                "df4af03aed77eada82db1190a5e09fab1c6e58af8ae748285492c29ff9942ddb",
            ),
            (
                "Scripts/onnxruntime_test.exe",
                "2de6d8d0189c7c534e1bd651c04439a8e5249c6c47e8a2a14948edeae3a3f103",
            ),
            (
                "Scripts/pip.exe",
                "5fd60e03c70a87351fc54817b781e25d5fdabc6e46f254f35cb03ebe69f8afea",
            ),
            (
                "Scripts/pip3.10.exe",
                "5fd60e03c70a87351fc54817b781e25d5fdabc6e46f254f35cb03ebe69f8afea",
            ),
            (
                "Scripts/pip3.exe",
                "5fd60e03c70a87351fc54817b781e25d5fdabc6e46f254f35cb03ebe69f8afea",
            ),
            (
                "Scripts/pygmentize.exe",
                "e8eb775e210ee09c786b10010624cbb775738b2bce0d971753d5135edc84122e",
            ),
            (
                "Scripts/tensorboard.exe",
                "31916e07b7550ab0ac49544c1cdd94a2b6d6c800e8a581a206410e7ef925ff1a",
            ),
            (
                "Scripts/tiny-agents.exe",
                "0364014950b6d6cc7ff927ef69885ed20cd5770457ee85f20024a22964178de1",
            ),
            (
                "Scripts/tqdm.exe",
                "d183f3a6b1d5be3c90a6394f9bb7adc67127cb9e4090898489a942fa52eca54d",
            ),
            (
                "Scripts/uvicorn.exe",
                "cac120e39ffa32bc0ed90764790ec71fe7fe3828e29c1adf59b2c045d0e177d0",
            ),
            (
                "Scripts/wheel.exe",
                "af3fc56cfcf8103ba53d05e5d43927de43e289735fc8ca45f757e6c3201bc9dd",
            ),
        ];
        let index = index();
        assert_eq!(index.entrypoint_controls.len(), expected.len());
        let template = decode_hex(&index.entrypoint_pe_template_hex).unwrap();
        let python = environment_python_path(environment);
        let python = python.to_str().unwrap();
        for (entry, (path, digest)) in index.entrypoint_controls.iter().zip(expected) {
            assert_eq!(entry.path, path);
            let main = entry.script_template.replace("{{PYTHON}}", python);
            let bytes = entry_executable(&template, python, main.as_bytes(), entry.kind).unwrap();
            assert_eq!(bytes.len(), 46080, "{path}");
            assert_eq!(hash(&bytes), digest, "{path}");
        }
    }
    #[test]
    fn uv_pe_reconstruction_binds_unicode_space_path_script_and_kind() {
        let index = index();
        let template = decode_hex(&index.entrypoint_pe_template_hex).unwrap();
        let entry = &index.entrypoint_controls[0];
        let python = r"C:\测试 空格\e\g0000000000000000\Scripts\python.exe";
        let main = entry.script_template.replace("{{PYTHON}}", python);
        let expected = entry_executable(&template, python, main.as_bytes(), 1).unwrap();
        assert_ne!(
            expected,
            entry_executable(
                &template,
                &python.replace("测试", "改变"),
                main.as_bytes(),
                1
            )
            .unwrap()
        );
        assert_ne!(
            expected,
            entry_executable(&template, python, b"import os\n", 1).unwrap()
        );
        assert_ne!(
            expected,
            entry_executable(&template, python, main.as_bytes(), 2).unwrap()
        );
        assert!(entry_executable(&template, python, main.as_bytes(), 0).is_err());
        assert!(entry_executable(&template, &"x".repeat(5000), main.as_bytes(), 1).is_err());
    }
    #[test]
    fn zip_envelope_has_one_exact_stored_main_and_known_crc() {
        assert_eq!(crc32(b"123456789"), 0xcbf43926);
        let bytes = zip_script(b"# coding: utf-8\npass\n").unwrap();
        let mut archive = zip::ZipArchive::new(std::io::Cursor::new(bytes)).unwrap();
        assert_eq!(archive.len(), 1);
        let mut entry = archive.by_index(0).unwrap();
        assert_eq!(entry.name(), "__main__.py");
        assert_eq!(entry.compression(), zip::CompressionMethod::Stored);
        let mut text = String::new();
        entry.read_to_string(&mut text).unwrap();
        assert_eq!(text, "# coding: utf-8\npass\n");
    }
    #[test]
    fn record_cannot_expand_trust_to_pth_or_escape_or_omit_original() {
        let original = PathBuf::from("Lib/site-packages/pkg/a.py");
        let allowed = BTreeSet::from([original.clone()]);
        assert!(validate_record(b"pkg/a.py,arbitrary,999\n", &allowed, &allowed).is_ok());
        assert!(validate_record(
            b"pkg/a.py,,\n../../Scripts/injected.exe,,\n",
            &allowed,
            &allowed
        )
        .is_err());
        assert!(validate_record(b"pkg/a.py,,\nuser.pth,,\n", &allowed, &allowed).is_err());
        assert!(validate_record(b"../../../outside,,\n", &allowed, &allowed).is_err());
        assert!(validate_record(b"", &allowed, &allowed).is_err());
        assert!(validate_record(b"pkg/a.py,,\npkg/a.py,,\n", &allowed, &allowed).is_err());
    }
}
