//! 为不认识数据根环境变量的历史版本构造可重建工作目录。
use crate::model::{self, Layout, Release};
use crate::operations::CancelToken;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT_PROBE: AtomicU64 = AtomicU64::new(0);
const PROBE_COPY_BLOCK_BYTES: usize = 65_536;

const SHARED: &[(&str, &str)] = &[
    ("user_data", "user_data"),
    ("sd-models", "library/models"),
    ("tagger-models", "library/tagger-models"),
    ("datasets", "library/datasets"),
    ("output", "library/output"),
    ("outputs", "library/output"),
];
const PER_RELEASE: &[&str] = &[
    "assets",
    "config",
    "toml",
    "logs",
    ".runtime",
    "extensions",
    "train",
    ".cache",
];

pub fn redirected(name: &str) -> bool {
    SHARED.iter().any(|(legacy, _)| *legacy == name) || PER_RELEASE.contains(&name)
}

fn copy_missing(source: &Path, target: &Path, layout: &Layout) -> Result<()> {
    layout.ensure_dir(target)?;
    if !source.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let from = entry.path();
        let to = target.join(entry.file_name());
        layout.guard_path(&from)?;
        layout.guard_path(&to)?;
        if entry.file_type()?.is_dir() {
            copy_missing(&from, &to, layout)?;
        } else if entry.file_type()?.is_file() && !to.exists() {
            fs::copy(from, to)?;
        } else if entry.file_type()?.is_symlink() {
            bail!("不接受版本内符号链接");
        }
    }
    Ok(())
}

/// 仅用于本次独占探针目录；取消留下的部分副本不得复用到兼容资料目录。
fn copy_probe_file(
    source: &Path,
    target: &Path,
    layout: &Layout,
    cancel: &CancelToken,
) -> Result<()> {
    cancel.check()?;
    layout.guard_path(source)?;
    layout.guard_path(target)?;
    let metadata = fs::symlink_metadata(source)?;
    if !metadata.is_file() {
        bail!("入口探测只复制普通文件");
    }
    let input = File::open(source);
    cancel.check()?;
    let mut input = input?;
    // 不跳过既有部分文件，也不覆盖其他尝试留下的文件。
    let output = OpenOptions::new().write(true).create_new(true).open(target);
    cancel.check()?;
    let mut output = output?;
    let mut copied = 0u64;
    let mut buffer = [0; PROBE_COPY_BLOCK_BYTES];
    loop {
        cancel.check()?;
        // 最多多读一字节识别复制期间的增长，不追随持续增长的文件。
        let read_size = metadata
            .len()
            .saturating_sub(copied)
            .saturating_add(1)
            .min(buffer.len() as u64) as usize;
        let read = input.read(&mut buffer[..read_size]);
        #[cfg(test)]
        if let Ok(count) = read.as_ref() {
            tests::after_probe_copy_read(source, *count);
        }
        cancel.check()?;
        let count = read?;
        if count == 0 {
            break;
        }
        copied = copied
            .checked_add(count as u64)
            .context("入口探测副本字节数溢出")?;
        if copied > metadata.len() {
            bail!("入口探测源文件在复制期间增长");
        }
        let written = output.write_all(&buffer[..count]);
        cancel.check()?;
        written?;
    }
    if copied != metadata.len() {
        bail!("入口探测源文件在复制期间长度变化");
    }
    drop(output);
    layout.guard_path(target)?;
    fs::set_permissions(target, metadata.permissions())?;
    cancel.check()?;
    Ok(())
}

fn copy_probe_tree(
    source: &Path,
    target: &Path,
    layout: &Layout,
    cancel: &CancelToken,
) -> Result<()> {
    cancel.check()?;
    layout.guard_path(source)?;
    layout.guard_path(target)?;
    layout.ensure_dir(target)?;
    if !source.exists() {
        cancel.check()?;
        return Ok(());
    }
    if !fs::symlink_metadata(source)?.is_dir() {
        bail!("入口探测复制源不是普通目录");
    }
    let entries = fs::read_dir(source);
    cancel.check()?;
    for entry in entries? {
        cancel.check()?;
        let entry = entry?;
        let from = entry.path();
        let to = target.join(entry.file_name());
        layout.guard_path(&from)?;
        layout.guard_path(&to)?;
        let metadata = fs::symlink_metadata(&from)?;
        if metadata.is_dir() {
            copy_probe_tree(&from, &to, layout, cancel)?;
        } else if metadata.is_file() {
            copy_probe_file(&from, &to, layout, cancel)?;
        } else {
            bail!("入口探测不接受符号链接或非普通文件");
        }
    }
    cancel.check()?;
    Ok(())
}

#[derive(Serialize, Deserialize)]
struct View {
    schema_version: u32,
    release_id: String,
    source_hashes: BTreeMap<String, String>,
}

/// 每次构建新的代码副本，目录联接只连接受保护的固定 profile 目标。
/// 不遍历或删除旧工作目录，避免跟随联接破坏用户资料。
pub fn prepare(layout: &Layout, release: &Release) -> Result<()> {
    layout.guard_path(&layout.app)?;
    layout.guard_path(&layout.run)?;
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let staged = layout
        .staging
        .with_file_name(format!("view-{}-{unique}", release.id));
    layout.ensure_dir(&staged)?;
    let compat = layout.profile.join("compat").join(&release.id);
    layout.ensure_dir(&compat)?;
    for entry in fs::read_dir(&layout.app)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if redirected(&name) {
            continue;
        }
        let dest = staged.join(entry.file_name());
        layout.guard_path(&entry.path())?;
        if entry.file_type()?.is_dir() {
            copy_missing(&entry.path(), &dest, layout)?;
        } else if entry.file_type()?.is_file() {
            fs::copy(entry.path(), dest)?;
        } else {
            bail!("版本源码含非普通文件");
        }
    }
    for (legacy, relative) in SHARED {
        let target = layout.profile.join(relative);
        layout.ensure_dir(&target)?;
        // 只接入已验证的 managed 目录；不从 profile 复制数据到版本源码。
        link_directory(&target, &staged.join(legacy))?;
    }
    for legacy in PER_RELEASE {
        let target = compat.join(legacy);
        copy_missing(&layout.app.join(legacy), &target, layout)?;
        link_directory(&target, &staged.join(legacy))?;
    }
    let hashes: BTreeMap<String, String> =
        serde_json::from_slice(&fs::read(layout.app.join(".source-integrity.json"))?)?;
    model::write_json_atomic(
        &staged.join(".runtime-view.json"),
        &View {
            schema_version: 1,
            release_id: release.id.clone(),
            source_hashes: hashes,
        },
    )?;
    if layout.run.exists() {
        let backup = layout
            .root
            .join("backups")
            .join(format!("view-{}-{unique}", release.id));
        layout.guard_path(&backup)?;
        fs::rename(&layout.run, backup).context("保留旧运行视图失败")?;
    }
    layout.ensure_dir(layout.run.parent().context("缺少运行目录父路径")?)?;
    fs::rename(staged, &layout.run)?;
    Ok(())
}

/// 登记/重建入口探测使用完全私有的普通目录副本；不建立任何资料目录联接。
pub(crate) struct ProbeView {
    pub workspace: PathBuf,
    pub run: PathBuf,
    pub profile: PathBuf,
    pub state: PathBuf,
}

/// 调用者先验证固定源码，复制后还须以固定清单核验副本再执行。
/// 唯一目录保留为事务证据；不得复用既有run/profile或清理其上层目录。
pub(crate) fn prepare_probe(
    layout: &Layout,
    transaction: &str,
    cancel: &CancelToken,
) -> Result<ProbeView> {
    cancel.check()?;
    model::validate_component(transaction)?;
    if transaction.len() > 96
        || !(transaction.starts_with("gui-registration-")
            || transaction.starts_with("gui-rebuild-"))
    {
        bail!("GUI入口探测事务身份无效");
    }
    layout.guard_path(&layout.app)?;
    let parent = layout.root.join("backups").join(transaction);
    layout.ensure_dir(&parent)?;
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let serial = NEXT_PROBE.fetch_add(1, Ordering::Relaxed);
    let workspace = parent.join(format!(
        "entry-probe-{}-{unique}-{serial}",
        std::process::id()
    ));
    layout.guard_path(&workspace)?;
    fs::create_dir(&workspace).context("入口探测目录已存在或无法独占创建")?;
    let view = ProbeView {
        run: workspace.join("run"),
        profile: workspace.join("profile"),
        state: workspace.join("state"),
        workspace,
    };
    copy_probe_tree(&layout.app, &view.run, layout, cancel)?;
    cancel.check()?;
    layout.ensure_dir(&view.profile)?;
    cancel.check()?;
    layout.ensure_dir(&view.state)?;
    cancel.check()?;
    // 历史源码若忽略DATA_ROOT/STATE_ROOT，也只会写自己的run副本。
    // 不先创建额外代码内目录：调用者要按可信清单核验完整副本。
    Ok(view)
}

/// 私有入口验证只复制配置，不联接生产资料或复制模型/数据集。
pub(crate) fn seed_probe_profile(
    layout: &Layout,
    view: &ProbeView,
    profile: &Path,
    cancel: &CancelToken,
) -> Result<()> {
    cancel.check()?;
    layout.guard_path(profile)?;
    for name in ["user_data", "compat"] {
        cancel.check()?;
        let source = profile.join(name);
        layout.guard_path(&source)?;
        copy_probe_tree(&source, &view.profile.join(name), layout, cancel)?;
    }
    cancel.check()?;
    Ok(())
}

#[cfg(windows)]
fn link_directory(target: &Path, link: &Path) -> Result<()> {
    junction::create(target, link)
        .with_context(|| format!("建立用户资料目录联接 {}", link.display()))
}
#[cfg(not(windows))]
fn link_directory(target: &Path, link: &Path) -> Result<()> {
    std::os::unix::fs::symlink(target, link)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Catalog;
    use crate::operations::{CancelReceipt, Cancelled};
    use std::{cell::RefCell, rc::Rc};

    type CopyReadHook = Box<dyn FnMut(&Path, usize)>;
    thread_local! {
        static COPY_READ_HOOK: RefCell<Option<CopyReadHook>> = const { RefCell::new(None) };
    }
    struct RestoreCopyReadHook(Option<CopyReadHook>);
    impl Drop for RestoreCopyReadHook {
        fn drop(&mut self) {
            let previous = self.0.take();
            COPY_READ_HOOK.with(|slot| {
                *slot.borrow_mut() = previous;
            });
        }
    }
    fn with_copy_read_hook<T>(hook: CopyReadHook, work: impl FnOnce() -> T) -> T {
        let previous = COPY_READ_HOOK.with(|slot| slot.replace(Some(hook)));
        let _restore = RestoreCopyReadHook(previous);
        work()
    }
    pub(super) fn after_probe_copy_read(source: &Path, bytes: usize) {
        COPY_READ_HOOK.with(|slot| {
            if let Some(hook) = slot.borrow_mut().as_mut() {
                hook(source, bytes);
            }
        });
    }
    fn probe_fixture(name: &str) -> (Layout, File) {
        let root = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "nt-probe-{name}-{}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos(),
                NEXT_PROBE.fetch_add(1, Ordering::Relaxed)
            ));
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let layout = Layout::new(&root, &release.id).unwrap();
        let lease = layout.prepare_workspace().unwrap();
        layout.ensure_dir(&layout.app).unwrap();
        layout.ensure_dir(&layout.run).unwrap();
        fs::write(layout.run.join("production-sentinel"), b"production-view").unwrap();
        layout
            .ensure_dir(&layout.profile.join("user_data"))
            .unwrap();
        layout.ensure_dir(&layout.profile.join("compat")).unwrap();
        fs::write(layout.profile.join("compat/sentinel"), b"production-compat").unwrap();
        (layout, lease)
    }
    fn cancel_after_first_read(
        source: PathBuf,
        cancel: CancelToken,
        reads: Rc<RefCell<Vec<usize>>>,
    ) -> CopyReadHook {
        Box::new(move |path, bytes| {
            if path == source {
                reads.borrow_mut().push(bytes);
                assert_eq!(reads.borrow().len(), 1, "取消后不得继续读取第二块");
                assert_eq!(bytes, PROBE_COPY_BLOCK_BYTES);
                assert_eq!(cancel.request(), CancelReceipt::Accepted);
            }
        })
    }

    #[test]
    fn rebuilding_code_keeps_user_data_and_version_state() {
        let root =
            std::env::temp_dir().join(format!("nt-view-{}-{}", std::process::id(), model::now()));
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let layout = Layout::new(&root, &release.id).unwrap();
        let _lease = layout.prepare_workspace().unwrap();
        layout.ensure_dir(&layout.app).unwrap();
        fs::write(layout.app.join("gui.py"), "# original").unwrap();
        fs::write(layout.app.join(".source-integrity.json"), "{}").unwrap();
        prepare(&layout, &release).unwrap();
        fs::write(
            layout.run.join("user_data/settings.json"),
            "{\"revision\":7}",
        )
        .unwrap();
        fs::write(layout.run.join("logs/task_queue.json"), "queue").unwrap();
        fs::write(layout.app.join("gui.py"), "# repaired").unwrap();
        prepare(&layout, &release).unwrap();
        assert_eq!(
            fs::read_to_string(layout.run.join("gui.py")).unwrap(),
            "# repaired"
        );
        assert_eq!(
            fs::read_to_string(layout.profile.join("user_data/settings.json")).unwrap(),
            "{\"revision\":7}"
        );
        assert_eq!(
            fs::read_to_string(layout.run.join("logs/task_queue.json")).unwrap(),
            "queue"
        );
        assert!(!layout.app.join("user_data").exists());
        // 含真实目录联接，交由测试现场保留；不递归删除到联接目标。
    }

    #[test]
    fn probe_views_are_independent_plain_copies_and_preserve_production_profiles_and_run() {
        let root = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "nt-probe-view-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let layout = Layout::new(&root, &release.id).unwrap();
        let _lease = layout.prepare_workspace().unwrap();
        layout.ensure_dir(&layout.app.join("config")).unwrap();
        fs::write(layout.app.join("gui.py"), b"# trusted copy fixture").unwrap();
        fs::write(layout.app.join("config/default.json"), b"source default").unwrap();
        layout
            .ensure_dir(&layout.profile.join("user_data"))
            .unwrap();
        fs::write(
            layout.profile.join("user_data/settings.json"),
            b"production-user",
        )
        .unwrap();
        layout.ensure_dir(&layout.run).unwrap();
        fs::write(layout.run.join("production-sentinel"), b"production-view").unwrap();
        let cancel = CancelToken::new();
        let first = prepare_probe(&layout, "gui-registration-repeated", &cancel).unwrap();
        fs::write(first.profile.join("sentinel"), b"first-attempt").unwrap();
        fs::write(first.run.join("config/default.json"), b"first-view-write").unwrap();
        let second = prepare_probe(&layout, "gui-registration-repeated", &cancel).unwrap();
        assert_ne!(first.workspace, second.workspace);
        assert!(!second.profile.join("sentinel").exists());
        assert_eq!(
            fs::read(second.run.join("config/default.json")).unwrap(),
            b"source default"
        );
        assert_eq!(
            fs::read(layout.app.join("config/default.json")).unwrap(),
            b"source default"
        );
        assert_eq!(
            fs::read(layout.profile.join("user_data/settings.json")).unwrap(),
            b"production-user"
        );
        assert_eq!(
            fs::read(layout.run.join("production-sentinel")).unwrap(),
            b"production-view"
        );
        for path in [
            &first.workspace,
            &first.run,
            &first.profile,
            &first.state,
            &second.workspace,
        ] {
            layout.guard_path(path).unwrap();
            assert!(fs::symlink_metadata(path).unwrap().is_dir());
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                assert_eq!(
                    fs::symlink_metadata(path).unwrap().file_attributes() & 0x400,
                    0
                );
            }
        }
        assert!(prepare_probe(&layout, "unrelated", &cancel).is_err());
        assert!(prepare_probe(&layout, "gui-registration-../escape", &cancel).is_err());
        // 保留独立测试证据，无递归清理。
    }

    #[test]
    fn probe_copy_precancel_does_not_create_evidence_or_touch_production() {
        let (layout, _lease) = probe_fixture("precancel");
        let source = vec![b'x'; PROBE_COPY_BLOCK_BYTES * 2 + 1];
        fs::write(layout.app.join("gui.py"), &source).unwrap();
        let cancel = CancelToken::new();
        assert_eq!(cancel.request(), CancelReceipt::Accepted);
        let error = prepare_probe(&layout, "gui-rebuild-copy-precancel", &cancel)
            .err()
            .expect("预取消不得构造入口副本");
        assert!(error.downcast_ref::<Cancelled>().is_some());
        assert!(!layout
            .root
            .join("backups/gui-rebuild-copy-precancel")
            .exists());
        assert_eq!(fs::read(layout.app.join("gui.py")).unwrap(), source);
        assert_eq!(
            fs::read(layout.run.join("production-sentinel")).unwrap(),
            b"production-view"
        );
        assert_eq!(
            fs::read(layout.profile.join("compat/sentinel")).unwrap(),
            b"production-compat"
        );
    }

    #[test]
    fn probe_source_copy_stops_after_first_real_block_and_retry_is_isolated() {
        let (layout, _lease) = probe_fixture("source-cancel");
        let source = vec![b'x'; PROBE_COPY_BLOCK_BYTES * 2 + 1];
        let source_path = layout.app.join("gui.py");
        fs::write(&source_path, &source).unwrap();
        let cancel = CancelToken::new();
        let reads = Rc::new(RefCell::new(Vec::new()));
        let error = with_copy_read_hook(
            cancel_after_first_read(source_path.clone(), cancel.clone(), reads.clone()),
            || prepare_probe(&layout, "gui-rebuild-copy-source", &cancel),
        )
        .err()
        .expect("真实首块读取后必须取消");
        assert!(error.downcast_ref::<Cancelled>().is_some());
        assert_eq!(*reads.borrow(), vec![PROBE_COPY_BLOCK_BYTES]);
        let attempts = fs::read_dir(layout.root.join("backups/gui-rebuild-copy-source"))
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        assert_eq!(attempts.len(), 1);
        let partial = attempts[0].join("run/gui.py");
        assert_eq!(fs::metadata(&partial).unwrap().len(), 0);
        let retried =
            prepare_probe(&layout, "gui-rebuild-copy-source", &CancelToken::new()).unwrap();
        assert_ne!(retried.workspace, attempts[0]);
        assert_eq!(fs::read(retried.run.join("gui.py")).unwrap(), source);
        assert_eq!(fs::metadata(&partial).unwrap().len(), 0);
        assert_eq!(fs::read(&source_path).unwrap(), source);
        assert_eq!(
            fs::read(layout.run.join("production-sentinel")).unwrap(),
            b"production-view"
        );
        assert_eq!(
            fs::read(layout.profile.join("compat/sentinel")).unwrap(),
            b"production-compat"
        );
    }

    #[test]
    fn probe_profile_copy_stops_after_first_real_block_and_retry_is_isolated() {
        let (layout, _lease) = probe_fixture("profile-cancel");
        fs::write(layout.app.join("gui.py"), b"# ordinary source copy").unwrap();
        let source = vec![b'p'; PROBE_COPY_BLOCK_BYTES * 2 + 1];
        let source_path = layout.profile.join("user_data/settings.json");
        fs::write(&source_path, &source).unwrap();
        let cancel = CancelToken::new();
        let view = prepare_probe(&layout, "gui-registration-copy-profile", &cancel).unwrap();
        let reads = Rc::new(RefCell::new(Vec::new()));
        let error = with_copy_read_hook(
            cancel_after_first_read(source_path.clone(), cancel.clone(), reads.clone()),
            || seed_probe_profile(&layout, &view, &layout.profile, &cancel),
        )
        .unwrap_err();
        assert!(error.downcast_ref::<Cancelled>().is_some());
        assert_eq!(*reads.borrow(), vec![PROBE_COPY_BLOCK_BYTES]);
        let partial = view.profile.join("user_data/settings.json");
        assert_eq!(fs::metadata(&partial).unwrap().len(), 0);
        let fresh = CancelToken::new();
        let retried = prepare_probe(&layout, "gui-registration-copy-profile", &fresh).unwrap();
        seed_probe_profile(&layout, &retried, &layout.profile, &fresh).unwrap();
        assert_ne!(retried.workspace, view.workspace);
        assert_eq!(
            fs::read(retried.profile.join("user_data/settings.json")).unwrap(),
            source
        );
        assert_eq!(
            fs::read(retried.profile.join("compat/sentinel")).unwrap(),
            b"production-compat"
        );
        assert_eq!(fs::metadata(&partial).unwrap().len(), 0);
        assert_eq!(fs::read(source_path).unwrap(), source);
        assert_eq!(
            fs::read(layout.profile.join("compat/sentinel")).unwrap(),
            b"production-compat"
        );
        assert_eq!(
            fs::read(layout.run.join("production-sentinel")).unwrap(),
            b"production-view"
        );
    }

    #[test]
    fn probe_source_copy_rejects_directory_links_without_following_them() {
        let (layout, _lease) = probe_fixture("source-link");
        let protected = layout.root.join("protected-source");
        layout.ensure_dir(&protected).unwrap();
        fs::write(protected.join("sentinel"), b"protected").unwrap();
        link_directory(&protected, &layout.app.join("linked")).unwrap();
        assert!(prepare_probe(&layout, "gui-rebuild-copy-link", &CancelToken::new(),).is_err());
        assert_eq!(fs::read(protected.join("sentinel")).unwrap(), b"protected");
        // 含真实链接，保留本轮独占证据；不递归清理。
    }
}
