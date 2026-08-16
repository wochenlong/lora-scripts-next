# 整合包构建与发包指南（给维护者 / 协作者）

> 面向：**你以外的成员也能按本文打出可发布的 Windows 整合包**。  
> 仓库：[`wochenlong/lora-scripts-next`](https://github.com/wochenlong/lora-scripts-next)  
> 产品名：**Next Trainer**；归档前缀：`Next-Trainer-v*.7z`（旧名 `SD-Trainer-v*.7z` 仅兼容）。

相关文档：

| 文档 | 用途 |
|------|------|
| 本文 | **怎么打、打哪种、验收、上传** |
| [`portable-packaging-git-update.md`](portable-packaging-git-update.md) | 目录契约、Git/Release 更新、用户数据保护 |
| [`design/portable-2026.md`](design/portable-2026.md) | 2026 根目录 UX（`启动.bat` 等）产品规格 |
| [`portable-getting-started.md`](portable-getting-started.md) | 给用户的 lite 上手 |
| [`portable-1.5-krea2-guide.md`](portable-1.5-krea2-guide.md) | 满配/Krea2 用户说明 |
| [`repo-layout.md`](repo-layout.md) | 不可改名的契约路径 |
| [`team/README.md`](team/README.md) | 谁有权发正式 Release |

本地历史笔记（**不在 Git**）：`build/整合包打包规范.md`（若存在）仅作个人备忘，**以本文与仓库内脚本为准**。

---

## 1. 先选包型（需求）

| 包型 | 谁需要 | 预装内容 | 典型体积 | 构建入口 |
|------|--------|----------|----------|----------|
| **lite** | 弱网 / 先开 UI / 自己装引擎 | 嵌入 Python + 代码 + WD 打标；**无** Torch 训练环境 | 7z ~0.4 GB | `build-scripts/build_portable.ps1` |
| **kohya** | 常规 Anima / SDXL / Flux | lite + **Kohya 主环境（cu128）**；无 Musubi | 7z 数 GB | `build-scripts/build_portable_kohya_only.ps1` |
| **kohya-musubi** | 傻瓜满配 / Krea2+常规 | Kohya + **Musubi**（cu128）；无 Fast | 7z ~4 GB 级 | `build-scripts/build_portable_2026_full.ps1` |
| **musubi** | 只要 Krea2、省盘 | lite 骨架 + Musubi；**无**完整 Kohya Torch | 小于满配 | `build-scripts/build_portable_musubi_only.ps1` |

**硬性产品约定（所有包型）：**

- **不预装** Anima Fast（`extensions/anima_lora/.venv`）— 用户在设置页安装  
- **不预装** 训练底模（Anima / Krea2 权重等）  
- **建议预置** 默认 WD 打标：`tagger-models/wd14/wd14-convnextv2-v2/`  
- 解压路径避免中文与空格；目标：Windows 10/11 + NVIDIA（建议 RTX 20+）  
- 30G 云系统盘：**不要**把三引擎硬塞进同一包；用分轨  

**命名：**

```text
Next-Trainer-v{VERSION}.7z                 # lite（旧脚本可能仍产出 SD-Trainer-v*.7z）
Next-Trainer-v{VERSION}-kohya.7z
Next-Trainer-v{VERSION}-kohya-musubi.7z
Next-Trainer-v{VERSION}-musubi.7z
```

`VERSION` 必须与仓库根目录 **`VERSION` 文件**及侧栏一致（正式如 `3.0.0`；候选可用 `3.0.0-rc.1` / 带日期后缀，须在 Release 说明写清）。

---

## 2. 构建机需求

| 项 | 要求 |
|----|------|
| OS | Windows 10/11 x64 |
| 磁盘 | lite：≥ 20 GB 空闲；满配/分轨：建议 ≥ **80 GB**（venv + 7z 临时） |
| 网络 | 能访问 GitHub、PyPI / 国内镜像、PyTorch cu128 索引（满配必连） |
| Git | 已安装；`origin` = `https://github.com/wochenlong/lora-scripts-next.git` |
| 7-Zip | `C:\Program Files\7-Zip\7z.exe` 或 PATH 中有 `7z` |
| Python | **官方 CPython 3.10**（带 `tcl/`），用于给 embed 补 tkinter。优先 `C:\Program Files\Python310\`。**不要用**缺 tcl 的 conda |
| 权限 | 能在仓库旁写 `build/`；正式上传需 GitHub Release / 魔搭权限（见 §6） |
| 可选 | 本机已有旧整合包或完整 `tagger-models/`，作 `-TaggerCacheSource` 种子，避免重复下 ONNX |

**不要用「正在开发、脏工作区」直接打进包。** 见 §3。

---

## 3. 代码基线（发包前）

```powershell
git fetch origin
# 正式稳定包（切 main 之后）：跟踪 main
# Vue3 / 3.0.0 候选与当前内测：跟踪 dev
git switch dev
git pull origin dev
git status   # 必须干净
Get-Content VERSION
git log -1 --oneline
```

检查清单：

- [ ] 工作区无未提交改动（或只用干净 worktree）  
- [ ] `VERSION` 与拟发布号一致  
- [ ] `frontend/dist` 与源码一致（改过 Vue 须先 `cd frontend && npm ci && npm run build`）  
- [ ] 未把本机 `data/`、`doc/`、`script/`、模型、密钥打进树  
- [ ] Fast：确认不会打包进维护机上的 `extensions/anima_lora/`（脚本已排除 `extensions/`）

推荐：单独 worktree 构建，避免踩开发目录。

```powershell
git worktree add D:\build\lora-scripts-next-portable origin/dev
cd D:\build\lora-scripts-next-portable
```

---

## 4. 构建命令

以下均在**仓库根目录**执行。把 `3.0.0` 换成实际版本号。

### 4.1 lite（体积小、首次启动再装依赖）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\build_portable.ps1 `
  -Clean -Version 3.0.0 `
  -TaggerCacheSource D:\path\to\seed-with-tagger-models
```

| 输出 | 路径 |
|------|------|
| 目录 | `build\SD-Trainer-Portable\` |
| 7z | `build\SD-Trainer-v3.0.0.7z`（当前 lite 脚本仍用此文件名；上传时可改名或说明） |

常用参数：`-Skip7z`、`-SkipTaggerPrefetch`、`-TaggerCacheSource <含 tagger-models 的旧包或仓库>`。

入口：用户双击 **`run_gui.bat`**（首次联网装主环境）。

### 4.2 kohya-musubi（满配）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\build_portable_2026_full.ps1 `
  -Clean -Version 3.0.0 `
  -TaggerCacheSource D:\path\to\seed-with-tagger-models
```

| 输出 | 路径 |
|------|------|
| 目录 | `build\SD-Trainer-Portable\`（根目录为 `启动.bat` / `检查更新.bat` / `说明.txt`） |
| 7z | `build\Next-Trainer-v3.0.0-kohya-musubi.7z` |
| 日志 | `build\portable-2026-logs\` |

耗时长（装 Torch ×2），需稳定网络。

### 4.3 kohya-only

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\build_portable_kohya_only.ps1 `
  -Clean -Version 3.0.0 `
  -TaggerCacheSource D:\path\to\seed-with-tagger-models
```

输出：`build\Next-Trainer-v3.0.0-kohya.7z`。

### 4.4 musubi-only（Krea2 分轨）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\build_portable_musubi_only.ps1 `
  -Clean -Version 3.0.0 `
  -TaggerCacheSource D:\path\to\seed-with-tagger-models
```

输出：`build\Next-Trainer-v3.0.0-musubi.7z`。  
本包主环境不烤满 Kohya Torch；常规 SDXL/Flux/Anima 请用 kohya 包。

---

## 5. 构建后验收（上传前必做）

### 5.1 自动

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\portable\verify_portable_release.ps1 `
  -PortableRoot .\build\SD-Trainer-Portable `
  -ArchivePath .\build\Next-Trainer-v3.0.0-kohya-musubi.7z `
  -ExpectedVersion 3.0.0

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\portable\verify_portable_updaters.ps1
```

（lite 的 `-ArchivePath` 换成实际 7z 名；`-ExpectedVersion` 与 `VERSION` 一致。）

### 5.2 手工冒烟（至少）

1. 解压到**干净路径**（非构建目录亦可）。  
2. 双击入口：lite → `run_gui.bat`；2026 根 → `启动.bat`。  
3. 打开 `http://127.0.0.1:28000`，侧栏 / `/api/version` = 预期版本。  
4. 设置 → 引擎状态可读；满配包 Musubi 应为就绪或可修复。  
5. **P0**：能提交一次训练或至少 `POST /api/run` 不因缺 `config/autosave` 等 500（见打包规范历史教训）。  
6. 确认包内**无**维护机 `extensions/anima_lora/.venv`、无训练底模、无个人数据。

把 commit、`PORTABLE_BUILD` 内容、7z 大小/SHA256 记在 Release 说明或内部验收帖。

---

## 6. 上传与发布权限

| 渠道 | 谁 | 怎么做 |
|------|-----|--------|
| GitHub Release | 默认 **@wochenlong**；获授权维护者可用 `gh release` | tag 如 `v3.0.0`；资产挂 7z；正文写包型与体积 |
| 魔搭数据集 | 需有 `windsing/next-trainer-portable`（或指定仓库）写权限 | 路径建议 `releases/v{VERSION}/Next-Trainer-v{VERSION}-*.7z` |

**未获 Release 权限的成员**：把验收过的 7z + SHA256 + 构建 commit 交给有权限者上传，或开 Discussion/Issue 交接。

`gh` 示例（有权限时）：

```powershell
gh release create v3.0.0 `
  -R wochenlong/lora-scripts-next `
  --title "Next Trainer v3.0.0" `
  --notes-file release-notes.md `
  .\build\Next-Trainer-v3.0.0-lite.7z `
  .\build\Next-Trainer-v3.0.0-kohya.7z `
  .\build\Next-Trainer-v3.0.0-kohya-musubi.7z
```

（文件名以实际产出为准。）

---

## 7. 禁止事项

- 改名/移动契约：`python_embeded/`、`SD-Trainer/`、`gui.py`、`run_gui.bat` 等（见 [`repo-layout.md`](repo-layout.md)）  
- 把完整 `.git` 历史打进包（应用浅克隆元数据；体积异常大要返工）  
- 用脏工作区、本机模型、Token、`doc/local` 私货进包  
- 预装 Fast venv「图省事」  
- 未跑 §5 就上传对外链接  

---

## 8. 故障速查

| 现象 | 处理 |
|------|------|
| tkinter / 文件选择器挂 | 构建机换官方 CPython 3.10；或从旧包复制 tcl / `_tkinter` |
| 打标模型重复下载慢 | `-TaggerCacheSource` 指向已有 `tagger-models` |
| 满配 pip/Torch 失败 | 换镜像、查 `build/portable-2026-logs/`；可先 lite 再本机装引擎对比 |
| 7z 过大 | 确认未打入 `data/`、完整 git、Fast venv；满配用 solid 7z（脚本已 `-ms=on`） |
| 用户「无法连接后端」 | 查包内日志与 `config/autosave`；勿只当端口问题 |

---

## 9. 3.0.0 阶段建议节奏

1. `dev` 技术验收（Discussion 协作清单）无阻断  
2. 按本文打 **候选包**（版本号可带 rc/日期）→ **内测群**  
3. 修阻断后再打正式号 → 切 `main` / 发 Release / 公开发链接  

教程与首页视觉**不阻塞**打包技术验收，但正式对外说明里建议链到用户文档。
