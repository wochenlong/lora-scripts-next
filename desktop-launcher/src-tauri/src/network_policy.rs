//! Rust/Python 共用网络语义。显式代理失败由调用方报错，不重试直连。
use anyhow::{bail, Context, Result};
use reqwest::Url;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{json, Value};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fmt,
    marker::PhantomData,
    net::IpAddr,
    path::{Path, PathBuf},
    process::Command,
    rc::Rc,
};

pub type ProxyEnv = BTreeMap<String, String>;
pub const ORIGINAL_PROXY_ENV: &str = "NEXT_TRAINER_ORIGINAL_PROXY_ENV";
const LOOPBACK: &str = "localhost,127.0.0.1,::1";
const CONFIG_LIMIT: u64 = 64 * 1024;
const PROXY_ERROR: &str =
    "代理需要有效的 HTTP/HTTPS 地址与端口；SOCKS 请改用代理软件的 HTTP 端口。";

#[derive(Clone, Default)]
pub struct Settings {
    pub mode: Option<String>,
    pub http_proxy: Option<String>,
    pub https_proxy: Option<String>,
    pub no_proxy: Option<String>,
    // Python dict.get distinguishes absent from an explicit null as well as an empty string.
    pub explicit_nulls: BTreeSet<String>,
}
impl<'de> Deserialize<'de> for Settings {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        let values = BTreeMap::<String, Value>::deserialize(deserializer)?;
        let mut settings = Self::default();
        for (key, value) in values {
            let destination = match key.as_str() {
                "mode" => &mut settings.mode,
                "http_proxy" => &mut settings.http_proxy,
                "https_proxy" => &mut settings.https_proxy,
                "no_proxy" => &mut settings.no_proxy,
                _ => continue,
            };
            match value {
                Value::String(text) => *destination = Some(text),
                Value::Null => {
                    settings.explicit_nulls.insert(key);
                }
                _ => return Err(serde::de::Error::custom("网络设置字段必须为字符串或 null")),
            }
        }
        Ok(settings)
    }
}
impl Serialize for Settings {
    fn serialize<S: Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        let mut map = BTreeMap::new();
        for (key, value) in [
            ("mode", &self.mode),
            ("http_proxy", &self.http_proxy),
            ("https_proxy", &self.https_proxy),
            ("no_proxy", &self.no_proxy),
        ] {
            if let Some(value) = value {
                map.insert(key, Value::String(value.clone()));
            } else if self.explicit_nulls.contains(key) {
                map.insert(key, Value::Null);
            }
        }
        map.serialize(serializer)
    }
}
impl fmt::Debug for Settings {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Settings")
            .field("mode", &self.mode)
            .field(
                "http_proxy",
                &self.http_proxy.as_ref().map(|_| "<configured>"),
            )
            .field(
                "https_proxy",
                &self.https_proxy.as_ref().map(|_| "<configured>"),
            )
            .field("no_proxy", &self.no_proxy.as_deref().map(redact))
            .finish()
    }
}
#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub struct SystemSettings {
    pub http: Option<String>,
    pub https: Option<String>,
    pub no_proxy: Option<String>,
    pub pac: bool,
}
impl fmt::Debug for SystemSettings {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SystemSettings")
            .field("http", &self.http.as_ref().map(|_| "<configured>"))
            .field("https", &self.https.as_ref().map(|_| "<configured>"))
            .field("no_proxy", &self.no_proxy.as_deref().map(redact))
            .field("pac", &self.pac)
            .finish()
    }
}
#[derive(Clone)]
pub struct Policy {
    pub mode: String,
    pub source: String,
    pub no_proxy: String,
    pub warning: String,
    http_proxy: Option<String>,
    https_proxy: Option<String>,
    original: ProxyEnv,
}
impl fmt::Debug for Policy {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.diagnostic(None).fmt(f)
    }
}
fn is_proxy_key(key: &str) -> bool {
    matches!(
        key.to_ascii_lowercase().as_str(),
        "http_proxy" | "https_proxy" | "all_proxy" | "no_proxy"
    )
}
pub fn original_proxy_env(env: &ProxyEnv) -> ProxyEnv {
    if let Some(raw) = env.get(ORIGINAL_PROXY_ENV).filter(|raw| !raw.is_empty()) {
        if let Ok(Value::Object(parsed)) = serde_json::from_str::<Value>(raw) {
            return parsed
                .into_iter()
                .filter_map(|(key, value)| {
                    if is_proxy_key(&key) {
                        value.as_str().map(|value| (key, value.to_owned()))
                    } else {
                        None
                    }
                })
                .collect();
        }
    }
    env.iter()
        .filter(|(key, _)| is_proxy_key(key))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect()
}
fn variable<'a>(env: &'a ProxyEnv, name: &str) -> Option<&'a str> {
    env.get(name)
        .or_else(|| env.get(&name.to_ascii_uppercase()))
        .map(String::as_str)
}
fn configured<'a>(
    settings: &Settings,
    field: &str,
    value: &'a Option<String>,
    fallback: Option<&'a str>,
) -> Option<&'a str> {
    if value.is_some() || settings.explicit_nulls.contains(field) {
        value.as_deref()
    } else {
        fallback
    }
}
pub fn proxy_url(value: Option<&str>) -> Result<Option<String>> {
    let Some(value) = value.filter(|value| !value.is_empty()) else {
        return Ok(None);
    };
    let trimmed = value.trim();
    let normalized = if trimmed.contains("://") {
        trimmed.to_owned()
    } else {
        format!("http://{trimmed}")
    };
    if normalized.chars().any(char::is_whitespace) {
        bail!(PROXY_ERROR);
    }
    // Url normalizes dot segments; Python checks the original path. A proxy
    // such as host/path/.. must not become an accepted root URL by normalization.
    let rest = normalized.split_once("://").expect("scheme normalized").1;
    let suffix = &rest[rest.find(['/', '?', '#']).unwrap_or(rest.len())..];
    let raw_path = suffix.split(['?', '#']).next().unwrap_or("");
    let parsed = Url::parse(&normalized).map_err(|_| anyhow::anyhow!(PROXY_ERROR))?;
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.host_str().is_none()
        || parsed.port() == Some(0)
        || !matches!(raw_path, "" | "/")
        || parsed.query().is_some_and(|query| !query.is_empty())
        || parsed
            .fragment()
            .is_some_and(|fragment| !fragment.is_empty())
    {
        bail!(PROXY_ERROR);
    }
    Ok(Some(normalized.trim_end_matches('/').to_owned()))
}

/// Pure resolver: explicit environment input follows Python resolve_policy(environ=...).
/// Runtime ORIGINAL restoration is handled by resolve_current, not this pure call.
pub fn resolve(saved: &Settings, env: &ProxyEnv, system: &SystemSettings) -> Result<Policy> {
    let mode = saved
        .mode
        .as_deref()
        .filter(|mode| !mode.is_empty())
        .or_else(|| env.get("NEXT_TRAINER_NETWORK_MODE").map(String::as_str))
        .unwrap_or("auto");
    if !matches!(mode, "auto" | "system" | "manual" | "direct") {
        bail!("网络模式必须是 auto/system/manual/direct。");
    }
    let original = original_proxy_env(env);
    if mode == "direct" {
        return Ok(Policy {
            mode: mode.into(),
            source: "direct".into(),
            no_proxy: "*".into(),
            warning: String::new(),
            http_proxy: None,
            https_proxy: None,
            original,
        });
    }
    let (http, https, source) = match mode {
        "manual" => {
            let http = saved
                .http_proxy
                .as_deref()
                .filter(|value| !value.is_empty())
                .or(saved.https_proxy.as_deref());
            let https = saved
                .https_proxy
                .as_deref()
                .filter(|value| !value.is_empty())
                .or(saved.http_proxy.as_deref());
            if http.is_none_or(|value| value.is_empty())
                && https.is_none_or(|value| value.is_empty())
            {
                bail!("手动模式需要代理地址。");
            }
            (http, https, "manual")
        }
        "system" => (system.http.as_deref(), system.https.as_deref(), "system"),
        _ => {
            let http = configured(
                saved,
                "http_proxy",
                &saved.http_proxy,
                variable(env, "http_proxy"),
            );
            let https = configured(
                saved,
                "https_proxy",
                &saved.https_proxy,
                variable(env, "https_proxy"),
            );
            let all = variable(env, "all_proxy");
            let source = if http.is_some() || https.is_some() || all.is_some() {
                "environment"
            } else {
                "system"
            };
            (
                http.or(all).or(system.http.as_deref()),
                https.or(all).or(system.https.as_deref()),
                source,
            )
        }
    };
    let bypass = configured(
        saved,
        "no_proxy",
        &saved.no_proxy,
        variable(env, "no_proxy"),
    )
    .or(system.no_proxy.as_deref())
    .unwrap_or("");
    let mut seen = BTreeSet::new();
    let no_proxy = format!("{},{}", bypass.replace(';', ","), LOOPBACK)
        .split(',')
        .filter(|token| seen.insert((*token).to_owned()))
        .collect::<Vec<_>>()
        .join(",");
    let http_proxy = proxy_url(http)?;
    let https_proxy = proxy_url(https)?;
    let enabled = http_proxy.is_some() || https_proxy.is_some();
    Ok(Policy {
        mode: mode.into(),
        source: if enabled { source } else { "direct" }.into(),
        no_proxy,
        warning: if system.pac && !enabled {
            "检测到 PAC，当前不执行 PAC 脚本；请设置手动代理。"
        } else {
            ""
        }
        .into(),
        http_proxy,
        https_proxy,
        original,
    })
}

pub fn settings_path(root: &Path) -> Result<PathBuf> {
    let layout = crate::model::Layout::new(root, "dev-0000000000000000000000000000000000000000")?;
    let path = root.join("config/network.local.json");
    layout.guard_path(&path)?;
    Ok(path)
}
pub fn load_settings(root: &Path) -> Result<Settings> {
    let path = settings_path(root)?;
    let metadata = match std::fs::metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(Settings::default())
        }
        Err(_) => bail!("网络设置文件不可读，请修复 config/network.local.json。"),
    };
    if !metadata.is_file() || metadata.len() > CONFIG_LIMIT {
        bail!("网络设置文件无效或超过64KiB，请修复 config/network.local.json。");
    }
    // Open after guarding, then take a bounded read; no huge-file race allocation.
    let mut file = std::fs::File::open(&path).context("网络设置文件不可读")?;
    use std::io::Read;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(CONFIG_LIMIT + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > CONFIG_LIMIT {
        bail!("网络设置文件超过64KiB");
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| anyhow::anyhow!("网络设置文件无效，请修复 config/network.local.json。"))
}
pub fn system_settings() -> SystemSettings {
    #[cfg(windows)]
    {
        use winreg::{enums::HKEY_CURRENT_USER, RegKey};
        let Ok(key) = RegKey::predef(HKEY_CURRENT_USER)
            .open_subkey(r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        else {
            return SystemSettings::default();
        };
        let mut settings = SystemSettings {
            pac: !key
                .get_value::<String, _>("AutoConfigURL")
                .unwrap_or_default()
                .is_empty(),
            no_proxy: Some(
                key.get_value::<String, _>("ProxyOverride")
                    .unwrap_or_default(),
            ),
            ..SystemSettings::default()
        };
        if key.get_value::<u32, _>("ProxyEnable").unwrap_or(0) == 0 {
            return settings;
        }
        let server = key
            .get_value::<String, _>("ProxyServer")
            .unwrap_or_default();
        let server = server.trim();
        if server.contains('=') {
            for part in server.split(';') {
                if let Some((scheme, address)) = part.split_once('=') {
                    match scheme.trim().to_ascii_lowercase().as_str() {
                        "http" => settings.http = Some(address.trim().into()),
                        "https" => settings.https = Some(address.trim().into()),
                        _ => {}
                    }
                }
            }
        } else if !server.is_empty() {
            settings.http = Some(server.into());
            settings.https = Some(server.into());
        }
        settings
    }
    #[cfg(not(windows))]
    {
        SystemSettings::default()
    }
}
fn resolve_original(
    settings: &Settings,
    mut env: ProxyEnv,
    system: &SystemSettings,
) -> Result<Policy> {
    let original = original_proxy_env(&env);
    env.retain(|key, _| !is_proxy_key(key));
    env.extend(original.clone());
    let mut policy = resolve(settings, &env, system)?;
    policy.original = original;
    Ok(policy)
}
/// Validates settings against the same original environment/system inputs as for_root,
/// before callers make any persistent change.
pub fn resolve_current(settings: &Settings) -> Result<Policy> {
    resolve_original(settings, std::env::vars().collect(), &system_settings())
}
pub fn for_root(root: &Path) -> Result<Policy> {
    resolve_current(&load_settings(root)?)
}
thread_local! { static ACTIVE: RefCell<Option<(PathBuf, Policy)>> = const { RefCell::new(None) }; }
/// A task guard stays on its worker thread. Nested scopes restore the previous frozen policy.
pub struct PolicyGuard {
    previous: Option<(PathBuf, Policy)>,
    _thread: PhantomData<Rc<()>>,
}
impl Drop for PolicyGuard {
    fn drop(&mut self) {
        ACTIVE.with(|active| *active.borrow_mut() = self.previous.take());
    }
}
pub fn task_policy(root: &Path) -> Result<PolicyGuard> {
    let policy = current_or_root(root)?;
    let previous = ACTIVE.with(|active| active.borrow_mut().replace((root.to_owned(), policy)));
    Ok(PolicyGuard {
        previous,
        _thread: PhantomData,
    })
}
pub fn current_or_root(root: &Path) -> Result<Policy> {
    let frozen = ACTIVE.with(|active| {
        active
            .borrow()
            .as_ref()
            .filter(|(path, _)| path == root)
            .map(|(_, policy)| policy.clone())
    });
    frozen.map_or_else(|| for_root(root), Ok)
}

impl Policy {
    pub fn bypass(&self, url: &str) -> bool {
        let Ok(parsed) = Url::parse(url) else {
            return false;
        };
        let host = parsed
            .host_str()
            .unwrap_or("")
            .trim_matches(['[', ']'])
            .to_ascii_lowercase();
        let host = host.trim_end_matches('.');
        let address = host.parse::<IpAddr>().ok();
        if host == "localhost" || address.is_some_and(|ip| ip.is_loopback()) {
            return true;
        }
        for token in self.no_proxy.replace(';', ",").split(',') {
            let token = token.trim().to_ascii_lowercase();
            if token.is_empty() {
                continue;
            }
            if token == "*" || (token == "<local>" && !host.contains('.') && address.is_none()) {
                return true;
            }
            if token.contains('/') {
                if let (Some(address), Ok(network)) = (address, token.parse::<ipnet::IpNet>()) {
                    if network.trunc().contains(&address) {
                        return true;
                    }
                }
                continue;
            }
            let mut pattern = token.as_str();
            if token.matches(':').count() == 1 {
                let (name, port) = token.rsplit_once(':').expect("one colon");
                if !port.is_empty() && port.chars().all(|c| c.is_ascii_digit()) {
                    if port.parse::<u32>().ok()
                        != Some(
                            parsed
                                .port()
                                .filter(|port| *port > 0)
                                .unwrap_or(if parsed.scheme() == "https" { 443 } else { 80 })
                                as u32,
                        )
                    {
                        continue;
                    }
                    pattern = name;
                }
            }
            let pattern = pattern.trim_matches(['[', ']']).trim_start_matches('.');
            if host == pattern || host.ends_with(&format!(".{pattern}")) || fnmatch(host, pattern) {
                return true;
            }
        }
        false
    }
    pub fn proxy_for(&self, url: &str) -> Option<String> {
        if self.mode == "direct" || self.bypass(url) {
            return None;
        }
        if Url::parse(url)
            .ok()
            .is_some_and(|url| url.scheme() == "https")
        {
            self.https_proxy.clone()
        } else {
            self.http_proxy.clone()
        }
    }
    pub fn diagnostic(&self, url: Option<&str>) -> Value {
        json!({"network_mode":self.mode,"source":self.source,"http_proxy":redact(self.http_proxy.as_deref().unwrap_or("")),
            "https_proxy":redact(self.https_proxy.as_deref().unwrap_or("")),"no_proxy":redact(&self.no_proxy),"warning":self.warning,
            "proxy_enabled":url.map_or(self.http_proxy.is_some() || self.https_proxy.is_some(), |url| self.proxy_for(url).is_some())})
    }
    pub fn client_builder(&self) -> reqwest::ClientBuilder {
        let policy = self.clone();
        reqwest::Client::builder()
            .no_proxy()
            .proxy(reqwest::Proxy::custom(move |url| {
                policy.proxy_for(url.as_str())
            }))
    }
    pub fn blocking_client_builder(&self) -> reqwest::blocking::ClientBuilder {
        let policy = self.clone();
        reqwest::blocking::Client::builder()
            .no_proxy()
            .proxy(reqwest::Proxy::custom(move |url| {
                policy.proxy_for(url.as_str())
            }))
    }
    pub fn process_env(&self, base: &ProxyEnv) -> ProxyEnv {
        let mut env = base.clone();
        env.retain(|key, _| !is_proxy_key(key));
        for (key, value) in [
            ("http_proxy", &self.http_proxy),
            ("https_proxy", &self.https_proxy),
        ] {
            if self.mode != "direct" {
                if let Some(value) = value {
                    env.insert(key.into(), value.clone());
                    env.insert(key.to_ascii_uppercase(), value.clone());
                }
            }
        }
        env.insert("no_proxy".into(), self.no_proxy.clone());
        env.insert("NO_PROXY".into(), self.no_proxy.clone());
        env.insert(
            ORIGINAL_PROXY_ENV.into(),
            serde_json::to_string(&self.original).expect("string map serializes"),
        );
        env
    }
    pub fn apply_command(&self, command: &mut Command) {
        let mut base: ProxyEnv = std::env::vars().collect();
        // Incorporate explicit builder values/removals before deriving the child environment.
        for (key, value) in command.get_envs() {
            let key = key.to_string_lossy().into_owned();
            if let Some(value) = value {
                base.insert(key, value.to_string_lossy().into_owned());
            } else {
                base.remove(&key);
            }
        }
        let mut removals: BTreeSet<String> = base
            .keys()
            .filter(|key| is_proxy_key(key))
            .cloned()
            .collect();
        for key in [
            "http_proxy",
            "HTTP_PROXY",
            "https_proxy",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
            "no_proxy",
            "NO_PROXY",
        ] {
            removals.insert(key.into());
        }
        for key in removals {
            command.env_remove(key);
        }
        // Do not re-add unrelated inherited variables (and preserve non-Unicode OS values).
        for (key, value) in self.process_env(&base) {
            if is_proxy_key(&key) || key == ORIGINAL_PROXY_ENV {
                command.env(key, value);
            }
        }
    }
}

/// Python fnmatchcase subset implemented over Unicode chars, including bracket classes.
/// Hostname inputs have already been normalized to lowercase by bypass().
fn fnmatch(value: &str, pattern: &str) -> bool {
    fn visit(
        value: &[char],
        pattern: &[char],
        seen: &mut BTreeSet<(usize, usize)>,
        i: usize,
        j: usize,
    ) -> bool {
        if !seen.insert((i, j)) {
            return false;
        }
        if j == pattern.len() {
            return i == value.len();
        }
        match pattern[j] {
            '*' => {
                visit(value, pattern, seen, i, j + 1)
                    || (i < value.len() && visit(value, pattern, seen, i + 1, j))
            }
            '?' => i < value.len() && visit(value, pattern, seen, i + 1, j + 1),
            '[' => {
                let mut end = j + 1;
                if pattern.get(end) == Some(&'!') {
                    end += 1;
                }
                if pattern.get(end) == Some(&']') {
                    end += 1;
                }
                while end < pattern.len() && pattern[end] != ']' {
                    end += 1;
                }
                if end == pattern.len() {
                    return i < value.len()
                        && value[i] == '['
                        && visit(value, pattern, seen, i + 1, j + 1);
                }
                if i == value.len() {
                    return false;
                }
                let mut at = j + 1;
                let negate = pattern[at] == '!';
                if negate {
                    at += 1;
                }
                let mut matched = false;
                while at < end {
                    if at + 2 < end && pattern[at + 1] == '-' {
                        matched |= pattern[at] <= value[i] && value[i] <= pattern[at + 2];
                        at += 3;
                    } else {
                        matched |= pattern[at] == value[i];
                        at += 1;
                    }
                }
                matched != negate && visit(value, pattern, seen, i + 1, end + 1)
            }
            c => i < value.len() && c == value[i] && visit(value, pattern, seen, i + 1, j + 1),
        }
    }
    let mut compact_pattern = Vec::new();
    for character in pattern.chars() {
        if character != '*' || compact_pattern.last() != Some(&'*') {
            compact_pattern.push(character);
        }
    }
    visit(
        &value.chars().collect::<Vec<_>>(),
        &compact_pattern,
        &mut BTreeSet::new(),
        0,
        0,
    )
}
fn safe_url(raw: &str) -> String {
    let Ok(url) = Url::parse(raw) else {
        return "<redacted-url>".into();
    };
    let Some((_, rest)) = raw.split_once("://") else {
        return "<redacted-url>".into();
    };
    let authority_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let authority = rest[..authority_end].rsplit('@').next().unwrap_or("");
    let host = url.host_str().unwrap_or("");
    let host = if host.contains(':') && !host.starts_with('[') {
        format!("[{host}]")
    } else {
        host.to_owned()
    };
    let explicit_port = if authority.starts_with('[') {
        authority
            .split_once(']')
            .and_then(|(_, suffix)| suffix.strip_prefix(':'))
    } else {
        authority.rsplit_once(':').map(|(_, port)| port)
    };
    let port = explicit_port
        .and_then(|port| port.parse::<u16>().ok())
        .filter(|port| *port > 0)
        .map(|port| format!(":{port}"))
        .unwrap_or_default();
    let tail = &rest[authority_end..];
    let path = tail.split(['?', '#']).next().unwrap_or("");
    format!("{}://{host}{port}{path}", url.scheme())
}
pub fn redact(value: &str) -> String {
    let mut result = String::new();
    let mut remaining = value;
    loop {
        let lowercase = remaining.to_ascii_lowercase();
        let Some(start) = lowercase
            .find("http://")
            .into_iter()
            .chain(lowercase.find("https://"))
            .min()
        else {
            break;
        };
        result.push_str(&remaining[..start]);
        remaining = &remaining[start..];
        let end = remaining
            .find(|c: char| c.is_whitespace() || matches!(c, '"' | '\'' | '<' | '>'))
            .unwrap_or(remaining.len());
        result.push_str(&safe_url(&remaining[..end]));
        remaining = &remaining[end..];
    }
    result.push_str(remaining);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::{TcpListener, TcpStream},
        sync::atomic::{AtomicU64, Ordering},
        thread,
        time::{Duration, Instant},
    };
    const VECTORS: &str =
        include_str!("../../../tests/fixtures/launcher-network-policy-vectors.json");
    fn fixture() -> Value {
        serde_json::from_str(VECTORS).unwrap()
    }
    fn env(value: &Value) -> ProxyEnv {
        serde_json::from_value(value.clone()).unwrap()
    }
    fn policy(value: &Value) -> Policy {
        resolve(
            &serde_json::from_value(value["saved"].clone()).unwrap(),
            &env(&value["environ"]),
            &serde_json::from_value(value["system"].clone()).unwrap(),
        )
        .unwrap()
    }
    #[test]
    fn shared_python_vectors_and_child_environment() {
        let vectors = fixture();
        for case in vectors["cases"].as_array().unwrap() {
            let policy = policy(case);
            let actual = json!({"mode":policy.mode,"http_proxy":policy.http_proxy,"https_proxy":policy.https_proxy,"source":policy.source,"no_proxy":policy.no_proxy,"warning":policy.warning});
            assert_eq!(actual, case["expected"], "{}", case["id"]);
            for route in case["routes"].as_array().unwrap() {
                let url = route["url"].as_str().unwrap();
                assert_eq!(
                    policy.bypass(url),
                    route["bypass"].as_bool().unwrap(),
                    "{}: {url}",
                    case["id"]
                );
                assert_eq!(
                    serde_json::to_value(policy.proxy_for(url)).unwrap(),
                    route["proxy"],
                    "{}: {url}",
                    case["id"]
                );
            }
            let mut base = env(&case["environ"]);
            base.insert("PATH".into(), "keep-path".into());
            base.insert("UNRELATED".into(), "keep-value".into());
            let child = policy.process_env(&base);
            assert_eq!(child["PATH"], "keep-path");
            assert_eq!(child["UNRELATED"], "keep-value");
            assert!(!child
                .keys()
                .any(|key| key.eq_ignore_ascii_case("all_proxy")));
            for name in ["http_proxy", "https_proxy"] {
                let expected = case["expected"][name].as_str();
                assert_eq!(child.get(name).map(String::as_str), expected);
                assert_eq!(
                    child.get(&name.to_ascii_uppercase()).map(String::as_str),
                    expected
                );
            }
            assert_eq!(child["no_proxy"], policy.no_proxy);
            assert_eq!(child["NO_PROXY"], policy.no_proxy);
            assert!(!format!("{policy:?}").contains("fake-password"));
            assert!(!policy
                .diagnostic(None)
                .to_string()
                .contains("fake-password"));
            assert_eq!(original_proxy_env(&child), original_proxy_env(&base));
        }
        for case in vectors["errors"].as_array().unwrap() {
            let error = resolve(
                &serde_json::from_value(case["saved"].clone()).unwrap(),
                &env(&case["environ"]),
                &serde_json::from_value(case["system"].clone()).unwrap(),
            )
            .unwrap_err();
            assert!(
                !format!("{error:#}").contains("token=fake"),
                "{}",
                case["id"]
            );
        }
        for case in vectors["original_inputs"].as_array().unwrap() {
            assert_eq!(
                original_proxy_env(&env(&case["environ"])),
                env(&case["expected"]),
                "{}",
                case["id"]
            );
        }
        for case in vectors["redact"].as_array().unwrap() {
            assert_eq!(
                redact(case["input"].as_str().unwrap()),
                case["expected"].as_str().unwrap()
            );
        }
    }
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Root(PathBuf);
    impl Root {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "next-trainer-network-policy-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
        fn save(&self, value: &str) {
            std::fs::create_dir_all(self.0.join("config")).unwrap();
            std::fs::write(self.0.join("config/network.local.json"), value).unwrap();
        }
    }
    impl Drop for Root {
        fn drop(&mut self) {
            if self.0.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .0
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("next-trainer-network-policy-")
            {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
    }
    #[test]
    fn settings_are_bounded_and_task_freeze_restores_on_drop() {
        let root = Root::new();
        root.save(r#"{"mode":"direct"}"#);
        let before = load_settings(&root.0).unwrap();
        assert_eq!(before.mode.as_deref(), Some("direct"));
        let outer = task_policy(&root.0).unwrap();
        root.save(r#"{"mode":"manual","http_proxy":"http://manual.test:82"}"#);
        assert_eq!(for_root(&root.0).unwrap().source, "manual");
        assert_eq!(current_or_root(&root.0).unwrap().mode, "direct");
        {
            let _inner = task_policy(&root.0).unwrap();
            assert_eq!(current_or_root(&root.0).unwrap().mode, "direct");
        }
        assert_eq!(current_or_root(&root.0).unwrap().mode, "direct");
        drop(outer);
        assert_eq!(current_or_root(&root.0).unwrap().mode, "manual");
        root.save(&" ".repeat(CONFIG_LIMIT as usize + 1));
        assert!(load_settings(&root.0).is_err());
        root.save(
            r#"{"mode":"manual","http_proxy":"http://u:fake-password@bad.test/path?token=fake"}"#,
        );
        assert!(!format!("{:#}", for_root(&root.0).unwrap_err()).contains("fake-password"));
    }
    #[cfg(windows)]
    #[test]
    fn settings_parent_junction_is_rejected_without_writing_target() {
        let root = Root::new();
        let outside = Root::new();
        std::fs::write(outside.0.join("network.local.json"), b"{}").unwrap();
        junction::create(&outside.0, root.0.join("config")).unwrap();
        assert!(load_settings(&root.0).is_err());
        junction::delete(root.0.join("config")).unwrap();
        assert_eq!(
            std::fs::read(outside.0.join("network.local.json")).unwrap(),
            b"{}"
        );
    }
    fn request(stream: &mut TcpStream) -> String {
        stream
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut bytes = Vec::new();
        while !bytes.ends_with(b"\r\n\r\n") {
            let mut byte = [0];
            assert_eq!(stream.read(&mut byte).unwrap(), 1);
            bytes.push(byte[0]);
            assert!(bytes.len() < 16384);
        }
        String::from_utf8(bytes).unwrap()
    }
    fn accept(listener: &TcpListener) -> TcpStream {
        listener.set_nonblocking(true).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            match listener.accept() {
                Ok((stream, _)) => return stream,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(
                        Instant::now() < deadline,
                        "loopback fixture accept deadline"
                    );
                    thread::sleep(Duration::from_millis(5));
                }
                Err(error) => panic!("{error}"),
            }
        }
    }
    #[test]
    fn explicit_proxy_routes_remote_then_redirect_bypasses_loopback() {
        let proxy = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let proxy_address = proxy.local_addr().unwrap();
        let target = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let target_address = target.local_addr().unwrap();
        let proxy_worker = thread::spawn(move || {
            let mut stream = accept(&proxy);
            let request = request(&mut stream);
            let response = format!("HTTP/1.1 302 Found\r\nLocation: http://{target_address}/done\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            stream.write_all(response.as_bytes()).unwrap();
            request
        });
        let target_worker = thread::spawn(move || {
            let mut stream = accept(&target);
            let request = request(&mut stream);
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
                .unwrap();
            request
        });
        let saved: Settings = serde_json::from_value(
            json!({"mode":"manual","http_proxy":format!("http://{proxy_address}")}),
        )
        .unwrap();
        let policy = resolve(&saved, &ProxyEnv::new(), &SystemSettings::default()).unwrap();
        let text = policy
            .blocking_client_builder()
            .timeout(Duration::from_secs(4))
            .build()
            .unwrap()
            .get("http://remote.invalid/start")
            .send()
            .unwrap()
            .text()
            .unwrap();
        assert_eq!(text, "ok");
        assert!(proxy_worker
            .join()
            .unwrap()
            .starts_with("GET http://remote.invalid/start "));
        assert!(target_worker.join().unwrap().starts_with("GET /done "));
    }
    #[test]
    fn explicit_proxy_failure_never_falls_back_to_direct() {
        let closed = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let address = closed.local_addr().unwrap();
        drop(closed);
        // Target would resolve if reached; resolve override makes a direct fallback observable.
        let target = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        target.set_nonblocking(true).unwrap();
        let target_address = target.local_addr().unwrap();
        let saved: Settings = serde_json::from_value(
            json!({"mode":"manual","http_proxy":format!("http://{address}")}),
        )
        .unwrap();
        let policy = resolve(&saved, &ProxyEnv::new(), &SystemSettings::default()).unwrap();
        let result = policy
            .blocking_client_builder()
            .resolve("remote.invalid", target_address)
            .timeout(Duration::from_secs(2))
            .build()
            .unwrap()
            .get(format!("http://remote.invalid:{}/", target_address.port()))
            .send();
        assert!(result.is_err());
        assert!(
            matches!(target.accept(), Err(error) if error.kind() == std::io::ErrorKind::WouldBlock)
        );
    }
    #[test]
    fn command_keeps_non_proxy_and_records_original_inputs() {
        let mut base = ProxyEnv::new();
        base.insert("HTTPS_PROXY".into(), "http://old.test:1".into());
        base.insert("PATH".into(), "kept".into());
        let policy = resolve(
            &serde_json::from_value(json!({"mode":"direct"})).unwrap(),
            &base,
            &SystemSettings::default(),
        )
        .unwrap();
        let mut command = Command::new("unused-test-executable");
        command
            .env("UNRELATED", "kept")
            .env("HTTPS_PROXY", "http://injected.test:2");
        policy.apply_command(&mut command);
        let explicit: BTreeMap<_, _> = command
            .get_envs()
            .map(|(key, value)| {
                (
                    key.to_string_lossy().into_owned(),
                    value.map(|v| v.to_string_lossy().into_owned()),
                )
            })
            .collect();
        assert_eq!(explicit["UNRELATED"].as_deref(), Some("kept"));
        assert!(explicit["HTTPS_PROXY"].is_none());
        assert_eq!(
            serde_json::from_str::<ProxyEnv>(explicit[ORIGINAL_PROXY_ENV].as_deref().unwrap())
                .unwrap(),
            original_proxy_env(&base)
        );
    }

    #[test]
    fn original_input_resolution_and_debug_never_expose_credentials() {
        let inputs = ProxyEnv::from([
            (ORIGINAL_PROXY_ENV.into(), "{}".into()),
            ("HTTPS_PROXY".into(), "http://injected.test:1".into()),
        ]);
        let system: SystemSettings =
            serde_json::from_value(json!({"https":"system.test:81"})).unwrap();
        let current = resolve_original(&Settings::default(), inputs, &system).unwrap();
        assert_eq!(
            current.proxy_for("https://remote.test/"),
            Some("http://system.test:81".into())
        );
        let settings: Settings = serde_json::from_value(
            json!({"mode":"manual", "http_proxy":"user:fake-password@auth.test:80"}),
        )
        .unwrap();
        assert!(!format!("{settings:?}").contains("fake-password"));
        let policy = resolve(&settings, &ProxyEnv::new(), &SystemSettings::default()).unwrap();
        assert!(!format!("{policy:?}").contains("fake-password"));
        assert_eq!(
            redact("HTTP://user:fake-password@host.test:80/a?token=fake"),
            "http://host.test:80/a"
        );
        assert_eq!(
            settings.http_proxy.as_deref(),
            Some("user:fake-password@auth.test:80")
        );
        let roundtrip: Settings =
            serde_json::from_value(serde_json::to_value(&settings).unwrap()).unwrap();
        assert_eq!(roundtrip.http_proxy, settings.http_proxy);
    }

    #[test]
    fn proxy_validation_uses_raw_path_and_wildcard_runs_are_bounded() {
        assert!(proxy_url(Some("http://proxy.test/path/..")).is_err());
        assert!(proxy_url(Some("http://proxy.test/%2e")).is_err());
        assert_eq!(
            proxy_url(Some("http://proxy.test?")).unwrap().as_deref(),
            Some("http://proxy.test?")
        );
        assert!(fnmatch("remote.test", &"*".repeat(CONFIG_LIMIT as usize)));
    }
}
