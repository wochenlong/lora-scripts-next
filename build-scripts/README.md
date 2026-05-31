# build-scripts

Windows 便携整合包构建脚本。详细契约见 [`docs/portable-packaging-git-update.md`](../docs/portable-packaging-git-update.md)。

## 入口

| 脚本 | 用途 |
|------|------|
| `build_portable.ps1` | 主流程：Python embed + 复制 SD-Trainer + 7z |
| `build-all.ps1` | 旧版一键构建（`build/sd-trainer-portable`） |

## Anima Fast（v2.7.0+）

**整合包不预装** `extensions/anima_lora/.venv`。`build_portable.ps1` 与 `03-copy-project.ps1` 在 robocopy 时排除整个 `extensions/`，避免把维护机上的插件快照或 venv 打进 7z。用户首次在 WebUI **Anima LoRA → Fast 模式** 页内安装插件。
