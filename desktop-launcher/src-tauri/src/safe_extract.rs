//! ZIP 安全边界：先预检全部条目，再向空目录写入；错误/取消留下的内容不视为可复用资产。
use crate::{model, operations::CancelToken};
use anyhow::{bail, Context, Result};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Component, Path, PathBuf},
};

const MAX_ENTRIES: usize = 20_000;
const MAX_FILE_BYTES: u64 = 512 * 1024 * 1024;
const RATIO: u64 = 1000;
const RATIO_ALLOWANCE: u64 = 64 * 1024;

fn check_cancel(cancel: Option<&CancelToken>) -> Result<()> {
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    Ok(())
}

fn metadata_safe(metadata: &fs::Metadata) -> Result<()> {
    if metadata.file_type().is_symlink() {
        bail!("解包路径包含符号链接，拒绝修改");
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            bail!("解包路径包含重解析点，拒绝修改");
        }
    }
    Ok(())
}

/// Windows 目录句柄不共享 WRITE/DELETE；检查后仍持有，阻止替换或改设 reparse。
fn pin_directory(path: &Path) -> Result<Option<File>> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        let file = OpenOptions::new()
            .read(true)
            .share_mode(0x1) // FILE_SHARE_READ；拒绝 WRITE/DELETE，固定目录身份和类型。
            .custom_flags(0x0200_0000 | 0x0020_0000) // BACKUP_SEMANTICS | OPEN_REPARSE_POINT。
            .open(path)?;
        let metadata = file.metadata()?;
        metadata_safe(&metadata)?;
        if !metadata.is_dir() {
            bail!("解包父路径不是目录");
        }
        Ok(Some(file))
    }
    #[cfg(not(windows))]
    {
        let metadata = fs::symlink_metadata(path)?;
        metadata_safe(&metadata)?;
        if !metadata.is_dir() {
            bail!("解包父路径不是目录");
        }
        Ok(None)
    }
}

fn check_chain(path: &Path) -> Result<()> {
    let mut current = PathBuf::new();
    for part in path.components() {
        match part {
            Component::ParentDir | Component::CurDir => bail!("解包路径不允许跳转"),
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("解包路径不是有效 Unicode")?)?;
            }
            _ => {}
        }
        current.push(part.as_os_str());
        match fs::symlink_metadata(&current) {
            Ok(metadata) => metadata_safe(&metadata)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

/// 逐层创建并在创建前后检查；保持所有已打开的 Windows 目录句柄直到解包结束。
fn directories(path: &Path, pins: &mut BTreeMap<PathBuf, Option<File>>) -> Result<()> {
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component.as_os_str());
        if matches!(component, Component::Prefix(_)) {
            continue;
        }
        if pins.contains_key(&current) {
            continue;
        }
        check_chain(&current)?;
        match fs::symlink_metadata(&current) {
            Ok(metadata) => {
                metadata_safe(&metadata)?;
                if !metadata.is_dir() {
                    bail!("解包父路径不是目录");
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::create_dir(&current)?;
            }
            Err(error) => return Err(error.into()),
        }
        check_chain(&current)?;
        pins.insert(current.clone(), pin_directory(&current)?);
    }
    Ok(())
}

fn u16_at(bytes: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([bytes[at], bytes[at + 1]])
}
fn u32_at(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().expect("固定长度 ZIP 字段"))
}

/// zip crate 按名称去重；先核原始中心目录计数和边界，避免重复名及假条目数被隐藏。
/// 本模块的 2GB/20k 限额无需 ZIP64；多卷、ZIP64 和额外中心目录结构保守拒绝。
fn central_count(file: &mut File) -> Result<usize> {
    let length = file.metadata()?.len();
    let tail_size = length.min(65_557) as usize;
    file.seek(SeekFrom::End(-(tail_size as i64)))?;
    let mut tail = vec![0; tail_size];
    file.read_exact(&mut tail)?;
    let end = (0..tail.len().saturating_sub(21))
        .rev()
        .find(|&i| {
            tail[i..].starts_with(b"PK\x05\x06")
                && i + 22 + u16_at(&tail, i + 20) as usize == tail.len()
        })
        .context("ZIP 结束目录无效")?;
    let header = &tail[end..];
    let count = u16_at(header, 10) as usize;
    let size = u32_at(header, 12) as u64;
    let offset = u32_at(header, 16) as u64;
    if count == 0
        || count > MAX_ENTRIES
        || u16_at(header, 4) != 0
        || u16_at(header, 6) != 0
        || u16_at(header, 8) as usize != count
        || size == u32::MAX as u64
        || offset == u32::MAX as u64
        || offset.checked_add(size) != Some(length - tail_size as u64 + end as u64)
    {
        bail!("ZIP 条目数、卷号或中心目录边界不受支持");
    }
    file.seek(SeekFrom::Start(offset))?;
    let mut consumed = 0u64;
    for _ in 0..count {
        let mut entry = [0u8; 46];
        file.read_exact(&mut entry)?;
        if &entry[..4] != b"PK\x01\x02"
            || u16_at(&entry, 34) != 0
            || u32_at(&entry, 20) == u32::MAX
            || u32_at(&entry, 24) == u32::MAX
            || u32_at(&entry, 42) as u64 >= offset
        {
            bail!("ZIP 中心目录条目无效或需要 ZIP64");
        }
        let skip =
            u16_at(&entry, 28) as u64 + u16_at(&entry, 30) as u64 + u16_at(&entry, 32) as u64;
        consumed = consumed
            .checked_add(46 + skip)
            .context("ZIP 中心目录溢出")?;
        if consumed > size {
            bail!("ZIP 中心目录条目越界");
        }
        file.seek(SeekFrom::Current(skip as i64))?;
    }
    if consumed != size {
        bail!("ZIP 中心目录计数不覆盖全部原始条目");
    }
    file.seek(SeekFrom::Start(0))?;
    Ok(count)
}

struct Entry {
    index: usize,
    relative: PathBuf,
    directory: bool,
    size: u64,
}
struct Node {
    spelling: String,
    directory: bool,
    explicit: bool,
}

fn preflight(
    archive: &mut zip::ZipArchive<File>,
    count: usize,
    strip_root: bool,
    cancel: Option<&CancelToken>,
) -> Result<Vec<Entry>> {
    if archive.len() != count {
        bail!("ZIP 包含重复的原始文件名");
    }
    let mut nodes: BTreeMap<String, Node> = BTreeMap::new();
    let mut result = Vec::with_capacity(count);
    let mut root: Option<String> = None;
    let mut total = 0u64;
    for index in 0..count {
        check_cancel(cancel)?;
        let entry = archive.by_index(index)?;
        let enclosed = entry.enclosed_name().context("ZIP 路径逃逸目标目录")?;
        let name = entry.name();
        let directory = entry.is_dir();
        let clean = name.strip_suffix('/').unwrap_or(name);
        let parts: Vec<_> = clean.split('/').collect();
        if parts.len() > 128 || name.len() > 16 * 1024 {
            bail!("ZIP 路径层级或长度过大");
        }
        for part in &parts {
            model::validate_component(part)?;
        }
        if enclosed != parts.iter().collect::<PathBuf>() {
            bail!("ZIP 路径规范化不一致");
        }
        if let Some(mode) = entry.unix_mode() {
            let expected = if directory { 0o040000 } else { 0o100000 };
            if mode & 0o170000 != expected {
                bail!("ZIP 只接受普通文件和目录，拒绝链接及特殊类型");
            }
        }
        let size = entry.size();
        if directory && (size != 0 || entry.compressed_size() != 0) {
            bail!("ZIP 目录条目包含数据");
        }
        if size > MAX_FILE_BYTES
            || size
                > entry
                    .compressed_size()
                    .saturating_mul(RATIO)
                    .saturating_add(RATIO_ALLOWANCE)
        {
            bail!("ZIP 单文件大小或压缩比超过限额");
        }
        total = total.checked_add(size).context("ZIP 声明展开总量溢出")?;
        if total > model::MAX_EXTRACT_BYTES {
            bail!("ZIP 声明展开总量超过限额");
        }
        let output = if strip_root {
            if let Some(root) = &root {
                if root != parts[0] {
                    bail!("ZIP 必须全部位于同一顶层目录");
                }
            } else {
                root = Some(parts[0].to_owned());
            }
            if parts.len() == 1 {
                if !directory {
                    bail!("strip_root 不接受顶层普通文件");
                }
                continue;
            }
            &parts[1..]
        } else {
            &parts[..]
        };
        for depth in 1..=output.len() {
            let spelling = output[..depth].join("/");
            let key = spelling.to_uppercase();
            let last = depth == output.len();
            let is_dir = !last || directory;
            if let Some(old) = nodes.get_mut(&key) {
                if old.spelling != spelling
                    || old.directory != is_dir
                    || (!is_dir || (last && old.explicit))
                {
                    bail!("ZIP 文件名大小写重复或文件/目录冲突");
                }
                old.explicit |= last;
            } else {
                nodes.insert(
                    key,
                    Node {
                        spelling,
                        directory: is_dir,
                        explicit: last,
                    },
                );
            }
        }
        result.push(Entry {
            index,
            relative: output.iter().collect(),
            directory,
            size,
        });
    }
    Ok(result)
}

pub(super) fn extract(
    zip_path: &Path,
    destination: &Path,
    strip_root: bool,
    cancel: Option<&CancelToken>,
) -> Result<()> {
    check_cancel(cancel)?;
    if !zip_path.is_absolute() || !destination.is_absolute() || destination.parent().is_none() {
        bail!("解包必须使用独立的绝对路径");
    }
    check_chain(zip_path)?;
    check_chain(destination)?;
    if destination.exists()
        && (!destination.is_dir() || fs::read_dir(destination)?.next().is_some())
    {
        bail!("解包目标必须为尚不存在或真正空的目录；已有内容保持不变");
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0x1).custom_flags(0x0020_0000);
    }
    let mut file = options.open(zip_path)?;
    metadata_safe(&file.metadata()?)?;
    let count = central_count(&mut file)?;
    let mut archive = zip::ZipArchive::new(file)?;
    let plan = preflight(&mut archive, count, strip_root, cancel)?;
    check_cancel(cancel)?;
    let mut pins = BTreeMap::new();
    directories(destination, &mut pins)?;
    if fs::read_dir(destination)?.next().is_some() {
        bail!("解包目标在预检期间发生变化，拒绝覆盖");
    }
    let mut actual_total = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    for item in plan {
        check_cancel(cancel)?;
        let target = destination.join(&item.relative);
        check_chain(&target)?;
        if item.directory {
            directories(&target, &mut pins)?;
            continue;
        }
        directories(target.parent().context("解包目标缺少父目录")?, &mut pins)?;
        check_chain(&target)?;
        let mut output_options = OpenOptions::new();
        output_options.write(true).create_new(true);
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            output_options.share_mode(0).custom_flags(0x0020_0000);
        }
        let mut output = output_options.open(&target)?;
        metadata_safe(&output.metadata()?)?;
        let mut entry = archive.by_index(item.index)?;
        let mut written = 0u64;
        loop {
            check_cancel(cancel)?;
            // 多读至多一个字节用于识别伪造的声明长度；越界数据从不写入目标。
            let wanted = buffer.len().min((item.size - written + 1) as usize);
            let count = entry.read(&mut buffer[..wanted])?;
            if count == 0 {
                break;
            }
            let next = written
                .checked_add(count as u64)
                .context("ZIP 实际文件大小溢出")?;
            let next_total = actual_total
                .checked_add(count as u64)
                .context("ZIP 实际展开总量溢出")?;
            if next > item.size || next > MAX_FILE_BYTES || next_total > model::MAX_EXTRACT_BYTES {
                bail!("ZIP 实际展开大小超过声明或限额；partial 保留且不可复用");
            }
            check_cancel(cancel)?;
            output.write_all(&buffer[..count])?;
            written = next;
            actual_total = next_total;
        }
        if written != item.size {
            bail!("ZIP 实际展开大小与声明不符；partial 保留且不可复用");
        }
        output.sync_all()?;
        check_cancel(cancel)?;
    }
    check_cancel(cancel)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::operations::{OperationKind, OperationManager};
    use std::sync::atomic::{AtomicU64, Ordering};
    use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let path = std::env::temp_dir().join(format!(
                "next-trainer-safe-extract-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
        fn zip(&self, entries: &[(&str, &[u8])]) -> PathBuf {
            let path = self.0.join("input.zip");
            let mut writer = ZipWriter::new(File::create(&path).unwrap());
            let options =
                SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
            for (name, bytes) in entries {
                if name.ends_with('/') {
                    writer.add_directory(*name, options).unwrap();
                } else {
                    writer.start_file(*name, options).unwrap();
                    writer.write_all(bytes).unwrap();
                }
            }
            writer.finish().unwrap();
            path
        }
        fn output(&self) -> PathBuf {
            self.0.join("output")
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn valid_real_zip_supports_stripped_root_and_existing_empty_target() {
        let temp = Temp::new();
        let archive = temp.zip(&[
            ("one/", b""),
            ("one/data/hello.txt", b"hello"),
            ("one/empty", b""),
        ]);
        fs::create_dir(temp.output()).unwrap();
        extract(&archive, &temp.output(), true, None).unwrap();
        assert_eq!(
            fs::read(temp.output().join("data/hello.txt")).unwrap(),
            b"hello"
        );
        assert_eq!(fs::metadata(temp.output().join("empty")).unwrap().len(), 0);
    }

    #[test]
    fn all_entries_are_preflighted_before_any_target_write() {
        for bad in [
            "../outside",
            "root/../../outside",
            "/absolute",
            "C:/outside",
            "root/CON.txt",
            "root/nul",
            "root/COM¹.log",
            "root/name.",
            "root/name ",
            "root/a\\b",
            "root/a//b",
        ] {
            let temp = Temp::new();
            let archive = temp.zip(&[("root/good.txt", b"good"), (bad, b"bad")]);
            assert!(
                extract(&archive, &temp.output(), true, None).is_err(),
                "{bad}"
            );
            assert!(!temp.output().exists(), "预检失败不创建目标：{bad}");
        }
    }

    #[test]
    fn case_duplicates_and_ancestor_file_conflicts_are_rejected() {
        for names in [
            ["a.txt", "A.TXT"],
            ["dir/a", "DIR/b"],
            ["thing", "thing/child"],
            ["thing/child", "thing"],
            ["thing/", "thing"],
        ] {
            let temp = Temp::new();
            let archive = temp.zip(&[(names[0], b""), (names[1], b"")]);
            assert!(
                extract(&archive, &temp.output(), false, None).is_err(),
                "{names:?}"
            );
            assert!(!temp.output().exists());
        }
    }

    #[test]
    fn mixed_strip_roots_and_top_level_files_are_rejected() {
        for names in [["one/a", "two/b"], ["one/a", "outside"]] {
            let temp = Temp::new();
            let archive = temp.zip(&[(names[0], b"a"), (names[1], b"b")]);
            assert!(extract(&archive, &temp.output(), true, None).is_err());
            assert!(!temp.output().exists());
        }
    }

    #[test]
    fn symlink_and_other_unix_file_types_are_rejected() {
        for mode in [0o120777u32, 0o010644, 0o020644, 0o060644, 0o140644] {
            let temp = Temp::new();
            let archive = temp.zip(&[("entry", b"target")]);
            let mut bytes = fs::read(&archive).unwrap();
            let cd = bytes.windows(4).position(|b| b == b"PK\x01\x02").unwrap();
            bytes[cd + 5] = 3; // Unix creator。
            bytes[cd + 38..cd + 42].copy_from_slice(&(mode << 16).to_le_bytes());
            fs::write(&archive, bytes).unwrap();
            assert!(
                extract(&archive, &temp.output(), false, None).is_err(),
                "{mode:o}"
            );
            assert!(!temp.output().exists());
        }
    }

    #[test]
    fn declared_and_actual_size_forgery_never_publish_excess_bytes() {
        for declared in [1u32, 9, 512 * 1024 * 1024 + 1] {
            let temp = Temp::new();
            let archive = temp.zip(&[("file", b"abcdef")]);
            let mut bytes = fs::read(&archive).unwrap();
            let cd = bytes.windows(4).position(|b| b == b"PK\x01\x02").unwrap();
            bytes[cd + 24..cd + 28].copy_from_slice(&declared.to_le_bytes());
            fs::write(&archive, bytes).unwrap();
            assert!(extract(&archive, &temp.output(), false, None).is_err());
            if let Ok(meta) = fs::metadata(temp.output().join("file")) {
                assert!(meta.len() <= 6 && meta.len() <= declared as u64);
            }
        }
    }

    #[test]
    fn cancellation_and_existing_target_protect_original_bytes() {
        let temp = Temp::new();
        let archive = temp.zip(&[("file", b"replacement")]);
        let manager = OperationManager::default();
        let operation = manager
            .start("cancel-safe-extract", OperationKind::Execute)
            .unwrap();
        manager.cancel("cancel-safe-extract").unwrap();
        assert!(extract(
            &archive,
            &temp.output(),
            false,
            Some(&operation.cancel_token())
        )
        .is_err());
        assert!(!temp.output().exists());
        fs::create_dir(temp.output()).unwrap();
        fs::write(temp.output().join("file"), b"original").unwrap();
        assert!(extract(&archive, &temp.output(), false, None).is_err());
        assert_eq!(fs::read(temp.output().join("file")).unwrap(), b"original");
    }

    #[test]
    fn ratio_and_raw_central_count_are_checked_before_writes() {
        let temp = Temp::new();
        let archive = temp.zip(&[("file", b"x")]);
        let original = fs::read(&archive).unwrap();
        let mut bytes = original.clone();
        let cd = bytes.windows(4).position(|b| b == b"PK\x01\x02").unwrap();
        bytes[cd + 24..cd + 28].copy_from_slice(&1_000_000u32.to_le_bytes());
        fs::write(&archive, bytes).unwrap();
        assert!(extract(&archive, &temp.output(), false, None).is_err());
        assert!(!temp.output().exists());
        let mut bytes = original;
        let end = bytes.windows(4).rposition(|b| b == b"PK\x05\x06").unwrap();
        bytes[end + 8..end + 12].copy_from_slice(&[0x21, 0x4e, 0x21, 0x4e]); // 20,001。
        fs::write(&archive, bytes).unwrap();
        assert!(extract(&archive, &temp.output(), false, None).is_err());
        assert!(!temp.output().exists());
    }

    #[cfg(windows)]
    #[test]
    fn external_junction_in_target_parent_chain_is_never_followed() {
        let temp = Temp::new();
        let archive = temp.zip(&[("file", b"new")]);
        let external = temp.0.join("external");
        fs::create_dir(&external).unwrap();
        fs::write(external.join("sentinel"), b"unchanged").unwrap();
        let link = temp.0.join("junction");
        junction::create(&external, &link).unwrap();
        assert!(extract(&archive, &link.join("output"), false, None).is_err());
        assert!(!external.join("output").exists());
        assert_eq!(fs::read(external.join("sentinel")).unwrap(), b"unchanged");
        junction::delete(&link).unwrap();
    }
}
