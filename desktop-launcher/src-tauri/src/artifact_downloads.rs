//! 一个受管操作共享一个正文预算会话；所有异步读取结束后才结账及释放工作区租约。
use crate::{
    download_budget::{self, DownloadBudget, DownloadOutcome, DownloadPolicy, OperationLimits},
    model::WorkspaceMutation,
    operations::{CancelToken, Cancelled},
};
use anyhow::{Context, Result};
use std::path::PathBuf;

pub(crate) struct ArtifactDownloads {
    operation: String,
    limits: OperationLimits,
    session: Option<DownloadBudget>,
    cache_hits: u64,
}

impl ArtifactDownloads {
    pub(crate) fn new(operation: &str, max_body_bytes: u64, max_requests: u32) -> Self {
        Self {
            operation: operation.into(),
            limits: OperationLimits {
                max_charged_body_bytes: max_body_bytes,
                max_requests,
                max_retries: max_requests,
                max_redirects: max_requests,
                max_elapsed_ms: 90 * 60 * 1000,
            },
            session: None,
            cache_hits: 0,
        }
    }

    pub(crate) fn download(
        &mut self,
        ctx: &WorkspaceMutation,
        url: &str,
        name: &str,
        expected: &str,
        bytes: u64,
        cancel: &CancelToken,
    ) -> Result<PathBuf> {
        cancel.check()?;
        if let Some(path) = super::controlled_download::cached_asset(ctx, name, expected, bytes)? {
            self.cache_hits = self.cache_hits.checked_add(1).context("缓存计数溢出")?;
            if let Some(session) = &self.session {
                session.record_cache_hit()?;
            }
            return Ok(path);
        }
        if self.session.is_none() {
            let view = download_budget::snapshot(ctx.layout())?;
            let session = DownloadBudget::begin(
                ctx,
                &self.operation,
                None,
                DownloadPolicy {
                    root_cap_body_bytes: view.root_cap_body_bytes,
                },
                self.limits.clone(),
            )?;
            for _ in 0..self.cache_hits {
                session.record_cache_hit()?;
            }
            self.session = Some(session);
        }
        super::controlled_download::download_with_budget(
            ctx,
            self.session.as_ref().context("下载预算会话未建立")?,
            url,
            name,
            expected,
            bytes,
            cancel,
        )
    }

    pub(crate) fn finish<T>(&self, result: &Result<T>) -> Result<()> {
        if let Some(session) = &self.session {
            let outcome = match result {
                Ok(_) => DownloadOutcome::Succeeded,
                Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
                    DownloadOutcome::Cancelled
                }
                Err(_) => DownloadOutcome::Failed,
            };
            session.finish(outcome)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Catalog;
    use sha2::{Digest, Sha256};
    use std::{
        fs,
        io::{Read, Write},
        net::TcpListener,
        thread,
        time::{Duration, Instant},
    };

    fn fixture(label: &str) -> WorkspaceMutation {
        let base = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = base.join(format!(
            "nt-artifacts-{label}-{}-{}",
            std::process::id(),
            super::super::stamp()
        ));
        assert!(!root.exists());
        fs::create_dir_all(&root).unwrap();
        WorkspaceMutation::acquire(&root, &Catalog::embedded().unwrap().releases()[0].id).unwrap()
    }
    fn hash(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }
    fn serve(bodies: &'static [&'static [u8]]) -> (String, thread::JoinHandle<()>) {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}/asset.zip", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            for body in bodies {
                let start = Instant::now();
                let mut socket = loop {
                    match listener.accept() {
                        Ok((socket, _)) => break socket,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            assert!(start.elapsed() < Duration::from_secs(10));
                            thread::sleep(Duration::from_millis(10));
                        }
                        Err(error) => panic!("accept: {error}"),
                    }
                };
                socket
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                socket
                    .set_write_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut request = [0; 4096];
                assert!(socket.read(&mut request).unwrap() > 0);
                write!(
                    socket,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                )
                .unwrap();
                socket.write_all(body).unwrap();
            }
        });
        (url, server)
    }

    #[test]
    fn one_product_operation_aggregates_multiple_assets_and_earlier_cache_hits() {
        let ctx = fixture("multiple");
        download_budget::initialize_policy(
            &ctx,
            DownloadPolicy {
                root_cap_body_bytes: Some(1024),
            },
        )
        .unwrap();
        fs::write(ctx.layout().root.join("cache/local.zip"), b"local").unwrap();
        let (url, server) = serve(&[b"alpha", b"beta"]);
        let mut downloads = ArtifactDownloads::new("multi-product-install", 1024, 8);
        let cancel = CancelToken::new();
        downloads
            .download(&ctx, &url, "local.zip", &hash(b"local"), 5, &cancel)
            .unwrap();
        downloads
            .download(&ctx, &url, "alpha.zip", &hash(b"alpha"), 5, &cancel)
            .unwrap();
        downloads
            .download(&ctx, &url, "alpha.zip", &hash(b"alpha"), 5, &cancel)
            .unwrap();
        downloads
            .download(&ctx, &url, "beta.zip", &hash(b"beta"), 4, &cancel)
            .unwrap();
        downloads.finish(&Ok(())).unwrap();
        server.join().unwrap();
        let snapshot = download_budget::snapshot_with_receipt(ctx.layout()).unwrap();
        let receipt = snapshot.latest_receipt.unwrap();
        assert_eq!(receipt.operation_id, "multi-product-install");
        assert_eq!(receipt.counters.requests, 2);
        assert_eq!(receipt.counters.cache_hits, 2);
        assert_eq!(receipt.counters.observed_body_bytes, 9);
        assert_eq!(receipt.counters.uncertain_charge_bytes, 0);
        assert_eq!(snapshot.budget.counters, receipt.counters);
        assert!(!snapshot.budget.pending_reconciliation);
        assert_eq!(
            fs::read_dir(ctx.layout().root.join("state/download-receipts"))
                .unwrap()
                .count(),
            1
        );
    }

    #[test]
    fn unconfigured_budget_allows_download_and_preserves_cache_without_a_root_cap() {
        let ctx = fixture("no-cap");
        let target = ctx.layout().root.join("cache/local.zip");
        fs::write(&target, b"local").unwrap();
        let mut downloads = ArtifactDownloads::new("no-cap-product", 1024, 8);
        let cancel = CancelToken::new();
        let (url, server) = serve(&[b"other"]);
        assert_eq!(
            downloads
                .download(&ctx, &url, "local.zip", &hash(b"local"), 5, &cancel)
                .unwrap(),
            target
        );
        assert!(!download_budget::snapshot(ctx.layout()).unwrap().enabled);
        let downloaded = downloads
            .download(&ctx, &url, "other.zip", &hash(b"other"), 5, &cancel)
            .unwrap();
        downloads.finish(&Ok(())).unwrap();
        server.join().unwrap();
        assert_eq!(fs::read(target).unwrap(), b"local");
        assert_eq!(fs::read(downloaded).unwrap(), b"other");
        let snapshot = download_budget::snapshot_with_receipt(ctx.layout()).unwrap();
        assert!(snapshot.budget.enabled);
        assert_eq!(snapshot.budget.root_cap_body_bytes, None);
        assert_eq!(snapshot.budget.remaining_body_bytes, None);
        assert_eq!(snapshot.budget.counters.observed_body_bytes, 5);
        let receipt = snapshot.latest_receipt.unwrap();
        assert_eq!(receipt.counters.requests, 1);
        assert_eq!(receipt.counters.cache_hits, 1);
        assert_eq!(receipt.counters, snapshot.budget.counters);
    }
}
