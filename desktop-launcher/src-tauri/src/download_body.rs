//! 将 HTTP 分块响应适配为固定大小的读取；不持久化流量账本或限制累计用量。
use crate::operations::CancelToken;
use anyhow::{bail, Result};

pub(crate) const READ_QUANTUM: usize = 65_536;

pub(crate) struct Body {
    response: reqwest::Response,
    buffered: Vec<u8>,
    position: usize,
    read_started: bool,
}

impl Body {
    pub(crate) fn new(response: reqwest::Response) -> Self {
        Self {
            response,
            buffered: Vec::new(),
            position: 0,
            read_started: false,
        }
    }

    pub(crate) fn status(&self) -> reqwest::StatusCode {
        self.response.status()
    }
    pub(crate) fn headers(&self) -> &reqwest::header::HeaderMap {
        self.response.headers()
    }
    pub(crate) fn read_started(&self) -> bool {
        self.read_started
    }

    pub(crate) async fn read(&mut self, output: &mut [u8], cancel: &CancelToken) -> Result<usize> {
        cancel.check()?;
        if output.is_empty() || output.len() > READ_QUANTUM {
            bail!("正文读取缓冲必须在1至64KiB之间");
        }
        self.read_started = true;
        // 空块不应导致假 EOF；异常响应持续产生空块时及时拒绝。
        for _ in 0..1024 {
            cancel.check()?;
            if self.position < self.buffered.len() {
                let count = output.len().min(self.buffered.len() - self.position);
                output[..count]
                    .copy_from_slice(&self.buffered[self.position..self.position + count]);
                self.position += count;
                return Ok(count);
            }
            match self.response.chunk().await? {
                Some(chunk) => {
                    self.buffered = chunk.to_vec();
                    self.position = 0;
                }
                None => return Ok(0),
            }
        }
        bail!("HTTP响应持续返回空数据块");
    }

    /// 错误/跳转响应只读取有限诊断正文，不把原始内容写到日志。
    pub(crate) async fn discard_diagnostic(&mut self, cancel: &CancelToken) -> Result<()> {
        let mut bytes = [0; 4096];
        let mut consumed = 0;
        while consumed < bytes.len() {
            let count = self.read(&mut bytes[consumed..], cancel).await?;
            if count == 0 {
                break;
            }
            consumed += count;
        }
        Ok(())
    }
}
