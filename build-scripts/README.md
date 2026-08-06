# build-scripts

Windows 便携整合包构建脚本。详细契约见 [`docs/portable-packaging-git-update.md`](../docs/portable-packaging-git-update.md)。

## 入口

| 脚本 | 用途 |
|------|------|
| `build_portable.ps1` | 主流程：Python embed + 复制 SD-Trainer + 7z |
| `build-all.ps1` | 旧版一键构建（`build/sd-trainer-portable`） |

## Anima Fast / 双包（lite · full）

| 参数 | 说明 |
|------|------|
| （默认） | **lite**：不预装 Fast；压缩包目标 &lt; 2 GB，适合 GitHub |
| `-BundleAnimaFast` | **full**：打入已就绪的 `extensions/anima_lora`（含 `.venv`），适合百度网盘 |
| `-AnimaFastSource` | full 包 Fast 源目录（需含 `.venv\Scripts\python.exe`） |

两包均会预取默认 WD 打标模型到 `tagger-models/wd14/`。详见 [`docs/portable-packaging-git-update.md`](../docs/portable-packaging-git-update.md)。
