//! 统一的受管制品下载入口；固定资产校验、续传和取消由下载器处理。
use crate::{model::WorkspaceMutation, operations::CancelToken};
use anyhow::Result;
use std::path::PathBuf;

pub(crate) struct ArtifactDownloads;

impl ArtifactDownloads {
    pub(crate) fn new() -> Self {
        Self
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
            return Ok(path);
        }
        super::controlled_download::download_artifact(ctx, url, name, expected, bytes, cancel)
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
    fn downloads_without_creating_download_accounting_state() {
        let ctx = fixture("no-accounting");
        let (url, server) = serve(&[b"alpha", b"beta"]);
        let mut downloads = ArtifactDownloads::new();
        let cancel = CancelToken::new();
        let first = downloads
            .download(&ctx, &url, "first.zip", &hash(b"alpha"), 5, &cancel)
            .unwrap();
        let second = downloads
            .download(&ctx, &url, "second.zip", &hash(b"beta"), 4, &cancel)
            .unwrap();
        server.join().unwrap();
        assert_eq!(fs::read(&first).unwrap(), b"alpha");
        assert_eq!(fs::read(second).unwrap(), b"beta");
        // 已校验缓存离线可用，不发起额外请求。
        assert_eq!(
            downloads
                .download(
                    &ctx,
                    "http://127.0.0.1:1/unreachable",
                    "first.zip",
                    &hash(b"alpha"),
                    5,
                    &cancel
                )
                .unwrap(),
            first
        );
        for name in [
            "download-budget.json",
            "download-budget-enrollment.json",
            "download-receipts",
        ] {
            assert!(!ctx.layout().root.join("state").join(name).exists());
        }
    }
}
