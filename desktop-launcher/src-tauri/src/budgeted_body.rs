//! 在正文交付给下载器之前预留额度；reqwest 内部缓冲及 TLS 流量另属计量范围。
use crate::{
    download_budget::{AttemptId, AttemptOutcome, DownloadBudget, ReadCredit, READ_QUANTUM},
    operations::CancelToken,
};
use anyhow::{bail, Result};

/// 与 StreamReader 一样把库返回块适配成有界 read；块内剩余数据尚未交付给下载器。
/// 底层 HTTP 实现可能预读，本类型不把应用层额度冒充网络传输额度。
pub(crate) struct Body {
    response: reqwest::Response,
    buffered: Vec<u8>,
    position: usize,
    budget: DownloadBudget,
    attempt: AttemptId,
    first_credit: Option<ReadCredit>,
    read_started: bool,
}

impl Body {
    pub(crate) fn new(
        response: reqwest::Response,
        budget: &DownloadBudget,
        attempt: AttemptId,
        first_credit: ReadCredit,
    ) -> Self {
        Self {
            response,
            buffered: Vec::new(),
            position: 0,
            budget: budget.clone(),
            attempt,
            first_credit: Some(first_credit),
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
        let credit = match self.first_credit.take() {
            Some(credit) => credit,
            None => self.budget.reserve_read(self.attempt, output.len())?,
        };
        let limit = output.len().min(credit.bytes());
        self.read_started = true;
        let result = async {
            // HTTP 空块不交付正文；有限循环防异常流无限消耗执行时间。
            for _ in 0..32 {
                if self.position < self.buffered.len() {
                    let count = limit.min(self.buffered.len() - self.position);
                    output[..count]
                        .copy_from_slice(&self.buffered[self.position..self.position + count]);
                    self.position += count;
                    return Ok(count);
                }
                cancel.check()?;
                match self.response.chunk().await? {
                    Some(chunk) => {
                        // 限制适配器持有的单块内存，不以此声称限制底层预读。
                        if chunk.len() > 2 * 1024 * 1024 {
                            bail!("HTTP库单块缓冲超过2MiB，停止本次下载");
                        }
                        self.buffered = chunk.to_vec();
                        self.position = 0;
                    }
                    None => return Ok(0),
                }
            }
            bail!("HTTP响应连续空块过多");
        }
        .await;
        match result {
            Ok(count) => {
                self.budget.settle_read(credit, count)?;
                Ok(count)
            }
            Err(error) => {
                self.budget.uncertain_read(credit)?;
                Err(error)
            }
        }
    }

    /// 错误/重定向正文只作有限消费且不记原始文本，避免日志泄露令牌。
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

    pub(crate) fn finish(self, outcome: AttemptOutcome) -> Result<()> {
        // 未消费的首credit保留给finish_attempt保守结算，Drop绝不退款。
        self.budget.finish_attempt(self.attempt, outcome)
    }
}
