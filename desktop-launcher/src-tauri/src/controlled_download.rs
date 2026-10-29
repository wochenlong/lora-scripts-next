//! 持工作区租约的归档下载。部分文件只按绑定的长度与强 ETag 续传，
//! 全量长度和 SHA256 通过后才发布 cache；网络任务可被独立取消并等待析构。
use crate::{
    model::{self, Layout, WorkspaceMutation},
    operations::CancelToken,
};
use anyhow::{bail, Context, Result};
use reqwest::{
    header::{
        HeaderMap, ACCEPT_ENCODING, CONTENT_ENCODING, CONTENT_LENGTH, CONTENT_RANGE, ETAG,
        IF_RANGE, LAST_MODIFIED, RANGE,
    },
    Client, StatusCode,
};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    thread,
    time::Duration,
};

const PARTIAL_SCHEMA: u32 = 1;
const MAX_METADATA_BYTES: u64 = 16 * 1024;
static NEXT_QUARANTINE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    tag = "kind",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
enum Validator {
    Etag(String),
    LastModified(String),
}

impl Validator {
    fn value(&self) -> &str {
        match self {
            Self::Etag(value) | Self::LastModified(value) => value,
        }
    }

    fn validate(&self) -> Result<()> {
        let value = self.value();
        if value.is_empty() || value.len() > 1024 || !value.is_ascii() {
            bail!("partial 验证器无效，保留原记录");
        }
        let _: reqwest::header::HeaderValue = value.parse()?;
        if matches!(self, Self::Etag(_))
            && (value.starts_with("W/")
                || value.len() < 2
                || !value.starts_with('"')
                || !value.ends_with('"')
                || !value.as_bytes()[1..value.len() - 1]
                    .iter()
                    .all(|byte| *byte == 0x21 || (0x23..=0x7e).contains(byte)))
        {
            bail!("partial 只接受强 ETag");
        }
        Ok(())
    }

    fn matches(&self, headers: &HeaderMap) -> Result<bool> {
        let name = match self {
            Self::Etag(_) => ETAG,
            Self::LastModified(_) => LAST_MODIFIED,
        };
        Ok(header(headers, name)?.as_deref() == Some(self.value()))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Partial {
    schema_version: u32,
    url: String,
    sha256: String,
    exact_bytes: u64,
    written: u64,
    validator: Option<Validator>,
}

impl Partial {
    fn validate(&self) -> Result<()> {
        if self.schema_version != PARTIAL_SCHEMA {
            bail!(
                "partial schema {} 不受支持，保留原文件并拒绝变更",
                self.schema_version
            );
        }
        validate_asset(&self.sha256, self.exact_bytes)?;
        if self.url.is_empty() || self.url.len() > 8192 || self.written > self.exact_bytes {
            bail!("partial 绑定或已写长度无效，保留原记录");
        }
        if let Some(validator) = &self.validator {
            validator.validate()?;
        }
        Ok(())
    }

    fn binds(&self, url: &str, expected: &str, exact_bytes: u64) -> bool {
        self.url == url && self.sha256 == expected && self.exact_bytes == exact_bytes
    }
}

#[derive(Clone)]
struct Paths {
    layout: Layout,
    target: PathBuf,
    partial: PathBuf,
    metadata: PathBuf,
}

impl Paths {
    fn new(layout: &Layout, name: &str) -> Result<Self> {
        model::validate_component(name)?;
        let cache = layout.root.join("cache");
        let paths = Self {
            layout: layout.clone(),
            target: cache.join(name),
            partial: cache.join(format!("{name}.part")),
            metadata: cache.join(format!("{name}.part.json")),
        };
        for path in [&paths.target, &paths.partial, &paths.metadata] {
            layout.guard_path(path)?;
            if path.exists() && !path.is_file() {
                bail!("下载路径不是普通文件：{}", path.display());
            }
        }
        Ok(paths)
    }

    fn read_metadata(&self) -> Result<Option<Partial>> {
        self.layout.guard_path(&self.metadata)?;
        if !self.metadata.exists() {
            return Ok(None);
        }
        if fs::metadata(&self.metadata)?.len() > MAX_METADATA_BYTES {
            bail!("partial 元数据过大，保留原文件并拒绝变更");
        }
        let record: Partial = serde_json::from_slice(&fs::read(&self.metadata)?)
            .context("partial 元数据损坏或字段不受支持；保留原文件")?;
        record.validate()?;
        Ok(Some(record))
    }

    fn checkpoint(&self, output: &mut File, record: &Partial) -> Result<()> {
        self.layout.guard_path(&self.partial)?;
        self.layout.guard_path(&self.metadata)?;
        output.flush()?;
        output.sync_all()?;
        // 先同步数据再提交长度。崩溃留下长度不符时，下次隔离，不猜测已提交范围。
        model::write_json_atomic(&self.metadata, record)
    }

    fn quarantine_partial(&self) -> Result<()> {
        quarantine(&self.layout, &self.partial)?;
        quarantine(&self.layout, &self.metadata)
    }
}

fn validate_asset(expected: &str, exact_bytes: u64) -> Result<()> {
    if exact_bytes == 0 || exact_bytes > model::MAX_DOWNLOAD_BYTES {
        bail!("资产预期长度超出下载上限");
    }
    if expected.len() != 64
        || !expected
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        bail!("资产 SHA256 必须为64位小写十六进制");
    }
    Ok(())
}

fn quarantine(layout: &Layout, path: &Path) -> Result<()> {
    layout.guard_path(path)?;
    if !path.exists() {
        return Ok(());
    }
    let serial = NEXT_QUARANTINE.fetch_add(1, Ordering::Relaxed);
    let destination = path.with_file_name(format!(
        "{}.quarantine-{}-{}-{serial}",
        path.file_name()
            .context("隔离文件缺少文件名")?
            .to_string_lossy(),
        std::process::id(),
        super::stamp()
    ));
    layout.guard_path(&destination)?;
    if destination.exists() {
        bail!("隔离目标已存在，保留原文件");
    }
    fs::rename(path, destination)?;
    Ok(())
}

fn header(headers: &HeaderMap, name: reqwest::header::HeaderName) -> Result<Option<String>> {
    let mut values = headers.get_all(name).iter();
    let value = values
        .next()
        .map(|value| value.to_str().map(str::to_owned))
        .transpose()?;
    if values.next().is_some() {
        bail!("下载响应包含重复的关键标头");
    }
    Ok(value)
}

fn validator(headers: &HeaderMap) -> Result<Option<Validator>> {
    if let Some(value) = header(headers, ETAG)? {
        if !value.starts_with("W/") {
            let validator = Validator::Etag(value);
            validator.validate()?;
            return Ok(Some(validator));
        }
    }
    if let Some(value) = header(headers, LAST_MODIFIED)? {
        // 日期仅保存身份，不以 Last-Modified 独立证明强验证器。
        let validator = Validator::LastModified(value);
        validator.validate()?;
        return Ok(Some(validator));
    }
    Ok(None)
}

fn content_length(headers: &HeaderMap) -> Result<Option<u64>> {
    header(headers, CONTENT_LENGTH)?
        .map(|value| value.parse().context("下载 Content-Length 无效"))
        .transpose()
}

fn verify_range(headers: &HeaderMap, start: u64, exact_bytes: u64) -> Result<()> {
    let value = header(headers, CONTENT_RANGE)?.context("206 缺少 Content-Range")?;
    let expected = format!("bytes {start}-{}/{exact_bytes}", exact_bytes - 1);
    if value != expected || content_length(headers)? != Some(exact_bytes - start) {
        bail!("206 的起点、终点、总长度或 Content-Length 不匹配");
    }
    Ok(())
}

async fn transfer(
    paths: Paths,
    client: Client,
    mut previous: Option<Partial>,
    mut record: Partial,
    cancel: CancelToken,
) -> Result<()> {
    // 416 不匹配时最多隔离重试一次，避免服务端异常导致无限重下。
    for attempt in 0..2 {
        cancel.check()?;
        let resume = previous.as_ref().filter(|record| {
            record.written > 0 && matches!(record.validator, Some(Validator::Etag(_)))
        });
        let mut request = client.get(&record.url).header(ACCEPT_ENCODING, "identity");
        if let Some(resume) = resume {
            request = request
                .header(RANGE, format!("bytes={}-", resume.written))
                .header(
                    IF_RANGE,
                    resume.validator.as_ref().context("续传缺少验证器")?.value(),
                );
        }
        let mut response = request.send().await?;
        cancel.check()?;
        if header(response.headers(), CONTENT_ENCODING)?
            .is_some_and(|value| !value.eq_ignore_ascii_case("identity"))
        {
            bail!("归档响应使用了非 identity 编码，拒绝按压缩后偏移续传");
        }
        match response.status() {
            StatusCode::RANGE_NOT_SATISFIABLE => {
                let resume = resume.context("无 Range 请求却收到416")?;
                let expected = format!("bytes */{}", record.exact_bytes);
                let range_matches = header(response.headers(), CONTENT_RANGE)?.as_deref()
                    == Some(expected.as_str());
                if range_matches
                    && resume.written == record.exact_bytes
                    && super::digest(&paths.partial)? == record.sha256
                {
                    return Ok(());
                }
                drop(response);
                paths.quarantine_partial()?;
                previous = None;
                if attempt == 0 {
                    continue;
                }
                bail!("416 无法确认完整资产，原 partial 已隔离");
            }
            StatusCode::PARTIAL_CONTENT => {
                let resume = resume.context("无 Range 请求却收到206")?;
                verify_range(response.headers(), resume.written, record.exact_bytes)?;
                if !resume
                    .validator
                    .as_ref()
                    .context("续传缺少验证器")?
                    .matches(response.headers())?
                {
                    bail!("206 的验证器与 If-Range 不匹配，保留原 partial");
                }
                record = resume.clone();
            }
            StatusCode::OK => {
                if header(response.headers(), CONTENT_RANGE)?.is_some()
                    || content_length(response.headers())?
                        .is_some_and(|length| length != record.exact_bytes)
                {
                    bail!("200 响应长度或范围不匹配，保留原 partial");
                }
                record.written = 0;
                record.validator = validator(response.headers())?;
            }
            status => bail!("下载响应状态不受支持：{status}"),
        }
        cancel.check()?;
        paths.layout.guard_path(&paths.partial)?;
        let mut output = if record.written == 0 {
            OpenOptions::new()
                .write(true)
                .create(true)
                .truncate(true)
                .open(&paths.partial)?
        } else {
            let output = OpenOptions::new().append(true).open(&paths.partial)?;
            if output.metadata()?.len() != record.written {
                bail!("partial 长度已变化，保留现场并拒绝追加");
            }
            output
        };
        paths.checkpoint(&mut output, &record)?;
        loop {
            cancel.check()?;
            let Some(chunk) = response.chunk().await? else {
                break;
            };
            let written = record
                .written
                .checked_add(chunk.len() as u64)
                .context("下载长度溢出")?;
            if written > record.exact_bytes {
                bail!("实际响应超出资产预期长度，partial 未发布");
            }
            output.write_all(&chunk)?;
            record.written = written;
            paths.checkpoint(&mut output, &record)?;
        }
        if record.written != record.exact_bytes {
            bail!("响应提前结束，保留已提交长度的 partial");
        }
        cancel.check()?;
        return Ok(());
    }
    unreachable!("416 最多重试一次")
}

pub(super) fn download(
    mutation: &WorkspaceMutation,
    client: Client,
    url: &str,
    name: &str,
    expected: &str,
    exact_bytes: u64,
    cancel: &CancelToken,
) -> Result<PathBuf> {
    cancel.check()?;
    validate_asset(expected, exact_bytes)?;
    if url.is_empty() || url.len() > 8192 {
        bail!("资产 URL 无效");
    }
    let paths = Paths::new(mutation.layout(), name)?;
    // 先读取已知格式，未知/损坏 sidecar 绝不因缓存命中或准备新请求被覆盖。
    let mut previous = paths.read_metadata()?;
    if paths.target.exists() {
        if fs::metadata(&paths.target)?.len() == exact_bytes
            && super::digest(&paths.target)? == expected
        {
            cancel.check()?;
            return Ok(paths.target);
        }
        quarantine(&paths.layout, &paths.target)?;
    }
    paths
        .layout
        .ensure_dir(paths.target.parent().context("缓存缺少父目录")?)?;
    let trusted = match &previous {
        Some(record) if paths.partial.exists() => {
            record.binds(url, expected, exact_bytes)
                && fs::metadata(&paths.partial)?.len() == record.written
                && (record.written == 0 || matches!(record.validator, Some(Validator::Etag(_))))
        }
        _ => false,
    };
    if !trusted {
        paths.quarantine_partial()?;
        previous = None;
    }
    let record = Partial {
        schema_version: PARTIAL_SCHEMA,
        url: url.into(),
        sha256: expected.into(),
        exact_bytes,
        written: 0,
        validator: None,
    };
    let task = tauri::async_runtime::spawn(transfer(
        paths.clone(),
        client,
        previous,
        record,
        cancel.clone(),
    ));
    loop {
        if cancel.is_cancel_requested() {
            task.abort();
            // 必须等待响应 socket 和 partial 文件释放，不能遗留后台网络任务。
            let _ = tauri::async_runtime::block_on(task);
            cancel.check()?;
            unreachable!("取消标记不会清除");
        }
        if task.inner().is_finished() {
            tauri::async_runtime::block_on(task)??;
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    cancel.check()?;
    paths.layout.guard_path(&paths.partial)?;
    if fs::metadata(&paths.partial)?.len() != exact_bytes
        || super::digest(&paths.partial)? != expected
    {
        bail!("资产完整 SHA256 校验失败，partial 保留且缓存未发布");
    }
    paths.layout.guard_path(&paths.target)?;
    if paths.target.exists() {
        bail!("缓存目标在下载时已出现，拒绝覆盖");
    }
    cancel.check()?;
    fs::rename(&paths.partial, &paths.target)?;
    paths.layout.guard_path(&paths.metadata)?;
    fs::remove_file(&paths.metadata).context("缓存已发布，但 partial 元数据清理失败")?;
    Ok(paths.target)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::operations::{CancelReceipt, OperationKind, OperationManager};
    use sha2::{Digest, Sha256};
    use std::{
        io::Read,
        net::{TcpListener, TcpStream},
        sync::mpsc,
        time::Instant,
    };

    const BODY: &[u8] = b"0123456789";
    const NAME: &str = "catalog.zip";
    static NEXT_TEST: AtomicU64 = AtomicU64::new(0);

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let serial = NEXT_TEST.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "next-trainer-range-{}-{}-{serial}",
                std::process::id(),
                super::super::stamp()
            ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }

        fn mutation(&self) -> WorkspaceMutation {
            let catalog = model::Catalog::embedded().unwrap();
            WorkspaceMutation::acquire(&self.0, &catalog.releases[0].id).unwrap()
        }

        fn paths(&self, mutation: &WorkspaceMutation) -> Paths {
            Paths::new(mutation.layout(), NAME).unwrap()
        }

        fn seed(&self, mutation: &WorkspaceMutation, url: &str, bytes: &[u8]) -> Paths {
            let paths = self.paths(mutation);
            mutation.layout().ensure_dir(&self.0.join("cache")).unwrap();
            fs::write(&paths.partial, bytes).unwrap();
            model::write_json_atomic(
                &paths.metadata,
                &Partial {
                    schema_version: PARTIAL_SCHEMA,
                    url: url.into(),
                    sha256: hash(BODY),
                    exact_bytes: BODY.len() as u64,
                    written: bytes.len() as u64,
                    validator: Some(Validator::Etag("\"asset-v1\"".into())),
                },
            )
            .unwrap();
            paths
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            if self.0.is_absolute()
                && self.0.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .0
                    .file_name()
                    .is_some_and(|name| name.to_string_lossy().starts_with("next-trainer-range-"))
            {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
    }

    fn hash(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    fn client() -> Client {
        Client::builder()
            .no_proxy()
            .connect_timeout(Duration::from_secs(2))
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap()
    }

    fn response(status: &str, headers: &str, body: &[u8]) -> Vec<u8> {
        let mut response =
            format!("HTTP/1.1 {status}\r\nConnection: close\r\n{headers}\r\n").into_bytes();
        response.extend_from_slice(body);
        response
    }

    fn accept(listener: &TcpListener) -> TcpStream {
        let start = Instant::now();
        loop {
            match listener.accept() {
                Ok((stream, _)) => {
                    // Windows 接受的 socket 可能继承 nonblocking，显式恢复带超时的读写。
                    stream.set_nonblocking(false).unwrap();
                    stream
                        .set_read_timeout(Some(Duration::from_secs(4)))
                        .unwrap();
                    stream
                        .set_write_timeout(Some(Duration::from_secs(4)))
                        .unwrap();
                    return stream;
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(
                        start.elapsed() < Duration::from_secs(10),
                        "未收到回环 HTTP 请求"
                    );
                    thread::sleep(Duration::from_millis(10));
                }
                Err(error) => panic!("回环 HTTP accept 失败：{error}"),
            }
        }
    }

    fn read_request(stream: &mut TcpStream) -> String {
        let mut bytes = Vec::new();
        while !bytes.ends_with(b"\r\n\r\n") {
            let mut byte = [0];
            assert_eq!(stream.read(&mut byte).unwrap(), 1);
            bytes.push(byte[0]);
            assert!(bytes.len() < 16384, "测试请求标头过大");
        }
        String::from_utf8(bytes).unwrap().to_ascii_lowercase()
    }

    fn serve(responses: Vec<Vec<u8>>) -> (String, thread::JoinHandle<Vec<String>>) {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}/asset.zip", listener.local_addr().unwrap());
        let worker = thread::spawn(move || {
            responses
                .into_iter()
                .map(|response| {
                    let mut stream = accept(&listener);
                    let request = read_request(&mut stream);
                    stream.write_all(&response).unwrap();
                    stream.flush().unwrap();
                    request
                })
                .collect()
        });
        (url, worker)
    }

    fn fetch(mutation: &WorkspaceMutation, url: &str) -> Result<PathBuf> {
        download(
            mutation,
            client(),
            url,
            NAME,
            &hash(BODY),
            BODY.len() as u64,
            &CancelToken::new(),
        )
    }

    #[test]
    fn disconnected_response_resumes_with_exact_206_and_if_range() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let (url, server) = serve(vec![
            response(
                "200 OK",
                "Content-Length: 10\r\nETag: \"asset-v1\"\r\n",
                &BODY[..4],
            ),
            response(
                "206 Partial Content",
                "Content-Length: 6\r\nContent-Range: bytes 4-9/10\r\nETag: \"asset-v1\"\r\n",
                &BODY[4..],
            ),
        ]);
        assert!(fetch(&mutation, &url).is_err());
        let paths = fixture.paths(&mutation);
        assert!(!paths.target.exists());
        assert_eq!(fs::read(&paths.partial).unwrap(), &BODY[..4]);
        assert_eq!(paths.read_metadata().unwrap().unwrap().written, 4);
        let target = fetch(&mutation, &url).unwrap();
        let requests = server.join().unwrap();
        assert!(!requests[0].contains("range:"));
        assert!(requests[1].contains("\r\nrange: bytes=4-\r\n"));
        assert!(requests[1].contains("\r\nif-range: \"asset-v1\"\r\n"));
        assert!(requests
            .iter()
            .all(|request| request.contains("accept-encoding: identity")));
        assert_eq!(fs::read(&target).unwrap(), BODY);
        assert!(!paths.partial.exists());
        assert!(!paths.metadata.exists());
        // 已验证缓存不需要联网；关闭服务后仍能直接复用。
        assert_eq!(fetch(&mutation, &url).unwrap(), target);
    }

    #[test]
    fn ignored_range_200_truncates_and_restarts_with_new_validator() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let (url, server) = serve(vec![response(
            "200 OK",
            "Content-Length: 10\r\nETag: \"asset-v2\"\r\n",
            BODY,
        )]);
        let paths = fixture.seed(&mutation, &url, &BODY[..4]);
        let target = fetch(&mutation, &url).unwrap();
        let requests = server.join().unwrap();
        assert!(requests[0].contains("range: bytes=4-"));
        assert_eq!(fs::read(target).unwrap(), BODY);
        assert!(!paths.metadata.exists());
    }

    #[test]
    fn wrong_ranges_lengths_and_changed_validators_never_append_or_publish() {
        for headers in [
            "Content-Length: 6\r\nContent-Range: bytes 3-8/10\r\nETag: \"asset-v1\"\r\n",
            "Content-Length: 6\r\nContent-Range: bytes 4-9/11\r\nETag: \"asset-v1\"\r\n",
            "Content-Length: 5\r\nContent-Range: bytes 4-9/10\r\nETag: \"asset-v1\"\r\n",
            "Content-Length: 6\r\nContent-Range: bytes 4-9/10\r\nETag: \"asset-v2\"\r\n",
            "Content-Length: 6\r\nContent-Range: bytes 4-9/10\r\n",
        ] {
            let fixture = Fixture::new();
            let mutation = fixture.mutation();
            let (url, server) = serve(vec![response("206 Partial Content", headers, &BODY[4..])]);
            let paths = fixture.seed(&mutation, &url, &BODY[..4]);
            let before = fs::read(&paths.metadata).unwrap();
            assert!(fetch(&mutation, &url).is_err());
            server.join().unwrap();
            assert_eq!(fs::read(&paths.partial).unwrap(), &BODY[..4]);
            assert_eq!(fs::read(&paths.metadata).unwrap(), before);
            assert!(!paths.target.exists());
        }
    }

    #[test]
    fn last_modified_is_recorded_but_does_not_authorize_if_range() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let date = "Wed, 21 Oct 2015 07:28:00 GMT";
        let (url, server) = serve(vec![
            response(
                "200 OK",
                &format!("Content-Length: 10\r\nLast-Modified: {date}\r\n"),
                &BODY[..4],
            ),
            response(
                "200 OK",
                &format!("Content-Length: 10\r\nLast-Modified: {date}\r\n"),
                BODY,
            ),
        ]);
        assert!(fetch(&mutation, &url).is_err());
        let paths = fixture.paths(&mutation);
        assert_eq!(
            paths.read_metadata().unwrap().unwrap().validator,
            Some(Validator::LastModified(date.into()))
        );
        assert_eq!(fs::read(fetch(&mutation, &url).unwrap()).unwrap(), BODY);
        let requests = server.join().unwrap();
        assert!(!requests[1].contains("\r\nif-range:"));
        assert!(!requests[1].contains("\r\nrange:"));
    }

    #[test]
    fn complete_416_is_published_only_after_full_hash_verification() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let (url, server) = serve(vec![response(
            "416 Range Not Satisfiable",
            "Content-Length: 0\r\nContent-Range: bytes */10\r\n",
            b"",
        )]);
        fixture.seed(&mutation, &url, BODY);
        let target = fetch(&mutation, &url).unwrap();
        let requests = server.join().unwrap();
        assert!(requests[0].contains("range: bytes=10-"));
        assert_eq!(fs::read(target).unwrap(), BODY);
    }

    #[test]
    fn incomplete_or_corrupt_416_is_quarantined_then_retried_without_range() {
        for old in [&BODY[..4], b"abcdefghij".as_slice()] {
            let fixture = Fixture::new();
            let mutation = fixture.mutation();
            let (url, server) = serve(vec![
                response(
                    "416 Range Not Satisfiable",
                    "Content-Length: 0\r\nContent-Range: bytes */10\r\n",
                    b"",
                ),
                response(
                    "200 OK",
                    "Content-Length: 10\r\nETag: \"asset-v2\"\r\n",
                    BODY,
                ),
            ]);
            fixture.seed(&mutation, &url, old);
            let target = fetch(&mutation, &url).unwrap();
            let requests = server.join().unwrap();
            assert!(requests[0].contains("\r\nrange:"));
            assert!(!requests[1].contains("\r\nrange:"));
            assert_eq!(fs::read(target).unwrap(), BODY);
            let isolated: Vec<_> = fs::read_dir(fixture.0.join("cache"))
                .unwrap()
                .map(|entry| entry.unwrap().path())
                .filter(|path| {
                    path.file_name()
                        .unwrap()
                        .to_string_lossy()
                        .contains(".part.quarantine-")
                })
                .collect();
            assert_eq!(isolated.len(), 1);
            assert_eq!(fs::read(&isolated[0]).unwrap(), old);
        }
    }

    #[test]
    fn bad_hash_keeps_consistent_partial_and_never_publishes_cache() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let (url, server) = serve(vec![response(
            "200 OK",
            "Content-Length: 10\r\nETag: \"wrong-content\"\r\n",
            b"abcdefghij",
        )]);
        assert!(fetch(&mutation, &url)
            .unwrap_err()
            .to_string()
            .contains("SHA256"));
        server.join().unwrap();
        let paths = fixture.paths(&mutation);
        assert!(!paths.target.exists());
        assert_eq!(fs::read(&paths.partial).unwrap(), b"abcdefghij");
        assert_eq!(paths.read_metadata().unwrap().unwrap().written, 10);
    }

    #[test]
    fn unknown_metadata_refuses_writes_even_when_cache_would_match() {
        let fixture = Fixture::new();
        let mutation = fixture.mutation();
        let url = "http://127.0.0.1:1/not-requested";
        let paths = fixture.seed(&mutation, url, &BODY[..4]);
        fs::write(&paths.target, BODY).unwrap();
        let record = serde_json::to_value(paths.read_metadata().unwrap().unwrap()).unwrap();
        let mut future_schema = record.clone();
        future_schema["schema_version"] = 999.into();
        let mut future_field = record;
        future_field["future_field"] = true.into();
        for bytes in [
            serde_json::to_vec(&future_schema).unwrap(),
            serde_json::to_vec(&future_field).unwrap(),
            b"{broken metadata".to_vec(),
        ] {
            fs::write(&paths.metadata, &bytes).unwrap();
            assert!(fetch(&mutation, url).is_err());
            assert_eq!(fs::read(&paths.metadata).unwrap(), bytes);
            assert_eq!(fs::read(&paths.partial).unwrap(), &BODY[..4]);
            assert_eq!(fs::read(&paths.target).unwrap(), BODY);
        }
    }

    #[test]
    fn uncommitted_length_or_missing_validator_is_isolated_before_a_fresh_request() {
        for without_validator in [false, true] {
            let fixture = Fixture::new();
            let mutation = fixture.mutation();
            let (url, server) = serve(vec![response("200 OK", "Content-Length: 10\r\n", BODY)]);
            let paths = fixture.seed(&mutation, &url, &BODY[..4]);
            if without_validator {
                let mut record = paths.read_metadata().unwrap().unwrap();
                record.validator = None;
                model::write_json_atomic(&paths.metadata, &record).unwrap();
            } else {
                OpenOptions::new()
                    .append(true)
                    .open(&paths.partial)
                    .unwrap()
                    .write_all(b"x")
                    .unwrap();
            }
            assert_eq!(fs::read(fetch(&mutation, &url).unwrap()).unwrap(), BODY);
            assert!(!server.join().unwrap()[0].contains("\r\nrange:"));
        }
    }

    #[test]
    fn stalled_headers_and_body_are_cancelled_with_socket_release_and_checkpoint_preserved() {
        for headers_sent in [false, true] {
            let fixture = Fixture::new();
            let mutation = fixture.mutation();
            let paths = fixture.paths(&mutation);
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            listener.set_nonblocking(true).unwrap();
            let url = format!("http://{}/asset.zip", listener.local_addr().unwrap());
            let (ready_tx, ready_rx) = mpsc::channel();
            let server = thread::spawn(move || {
                let mut socket = accept(&listener);
                let _ = read_request(&mut socket);
                if headers_sent {
                    socket
                        .write_all(&response(
                            "200 OK",
                            "Content-Length: 10\r\nETag: \"asset-v1\"\r\n",
                            &BODY[..4],
                        ))
                        .unwrap();
                    socket.flush().unwrap();
                }
                ready_tx.send(()).unwrap();
                let mut byte = [0];
                match socket.read(&mut byte) {
                    Ok(0) => {}
                    Err(error)
                        if matches!(
                            error.kind(),
                            std::io::ErrorKind::ConnectionReset
                                | std::io::ErrorKind::ConnectionAborted
                        ) => {}
                    other => panic!("取消未关闭回环 socket：{other:?}"),
                }
            });
            let manager = OperationManager::default();
            let handle = manager
                .start("strict-range-cancel", OperationKind::Download)
                .unwrap();
            let token = handle.cancel_token();
            let worker = thread::spawn(move || {
                download(
                    &mutation,
                    client(),
                    &url,
                    NAME,
                    &hash(BODY),
                    BODY.len() as u64,
                    &token,
                )
            });
            ready_rx.recv_timeout(Duration::from_secs(3)).unwrap();
            if headers_sent {
                let start = Instant::now();
                while paths
                    .read_metadata()
                    .ok()
                    .flatten()
                    .is_none_or(|record| record.written != 4)
                {
                    assert!(start.elapsed() < Duration::from_secs(3), "正文检查点未落盘");
                    thread::sleep(Duration::from_millis(10));
                }
            }
            let start = Instant::now();
            assert_eq!(
                manager.cancel("strict-range-cancel").unwrap(),
                CancelReceipt::Accepted
            );
            let error = worker.join().unwrap().unwrap_err();
            assert!(error
                .downcast_ref::<crate::operations::Cancelled>()
                .is_some());
            assert!(
                start.elapsed() < Duration::from_secs(2),
                "取消等待了网络超时"
            );
            server.join().unwrap();
            assert!(!paths.target.exists());
            if headers_sent {
                assert_eq!(fs::read(&paths.partial).unwrap(), &BODY[..4]);
                assert_eq!(paths.read_metadata().unwrap().unwrap().written, 4);
            } else {
                assert!(!paths.partial.exists());
                assert!(!paths.metadata.exists());
            }
        }
    }
}
