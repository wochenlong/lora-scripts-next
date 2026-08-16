# build-scripts

Windows 便携整合包构建脚本。

**协作者发包请先读：** [`docs/portable-build-guide.md`](../docs/portable-build-guide.md)（需求、包型、命令、验收、上传权限）。

契约细节：[`docs/portable-packaging-git-update.md`](../docs/portable-packaging-git-update.md)。  
2026 根目录规格：[`docs/design/portable-2026.md`](../docs/design/portable-2026.md)。

## 入口

| 脚本 | 用途 | 典型产出 |
|------|------|----------|
| `build_portable.ps1` | **lite**：骨架 + 打标；无预装 Torch | `SD-Trainer-v{VER}.7z` |
| `build_portable_2026_full.ps1` | **kohya-musubi** 满配（cu128） | `Next-Trainer-v{VER}-kohya-musubi.7z` |
| `build_portable_kohya_only.ps1` | **kohya** 分轨（`-SkipMusubi`） | `Next-Trainer-v{VER}-kohya.7z` |
| `build_portable_musubi_only.ps1` | **musubi** 分轨（Krea2） | `Next-Trainer-v{VER}-musubi.7z` |
| `apply_portable_2026_root.ps1` | 根目录改为 `启动.bat` / `检查更新.bat` / `说明.txt` | （被 full/分轨调用） |
| `build-all.ps1` | 旧版一键（遗留） | `build/sd-trainer-portable` |

## Anima Fast（v2.7.0+）

**整合包不预装** `extensions/anima_lora/.venv`。`build_portable.ps1` 与 `03-copy-project.ps1` 在 robocopy 时排除整个 `extensions/`。用户在 WebUI **设置 → 训练引擎** 或 Anima Fast 页内安装。
