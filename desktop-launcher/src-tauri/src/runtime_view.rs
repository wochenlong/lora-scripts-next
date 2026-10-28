//! 为不认识数据根环境变量的历史版本构造可重建工作目录。
use crate::model::{self, Layout, Release};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fs, path::Path};

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
    #[test]
    fn rebuilding_code_keeps_user_data_and_version_state() {
        let root =
            std::env::temp_dir().join(format!("nt-view-{}-{}", std::process::id(), model::now()));
        let release = Catalog::embedded().unwrap().releases[0].clone();
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
}
