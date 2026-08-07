# Next Trainer

**Next Trainer** 是 Windows 本地训练 WebUI（GitHub 仓库名：`lora-scripts-next`）。  
支持 Anima / SD 1.5 / SDXL / Flux 的 LoRA 与全量微调；基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) 与秋叶系训练体验。

> 产品品牌与发布归档一律为 **Next Trainer** / `Next-Trainer-v*.7z`。整合包内目录名 `SD-Trainer/`（及 `Update-SD-Trainer*.bat`）仍为兼容旧安装的启动契约，暂不改名。

[English](README.md) · [开源引用](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## 分支与版本（请先读）

| 分支 | 用途 | 界面 | 版本号 |
|------|------|------|--------|
| **`main`** | 稳定发布 | 旧版前端（预编译 dist） | 当前稳定 **v2.9.1** |
| **`dev`** | **Vue3 内测线**（本 README 默认对应此线） | Vue 3 四栏工作台 | **`2.9.x-beta.*`**（如 `2.9.2-beta.1`） |

**版本约定：** 内测一律使用 **`2.9.x`**；**正式版才用 `3.0.0`**，便于按版本号定位问题。反馈 Issue 时请附上侧栏显示的完整版本号。

---

## 下载 Next Trainer 整合包

| 包 | 内容 | 下载 |
|----|------|------|
| **lite** | 不含 Anima Fast 运行时；内置 WD 打标模型；约 **0.38 GB** | [GitHub Release v2.9.2-beta.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-beta.1) |
| **full** | 预装 Anima Fast `.venv` + 同上打标模型；约 **2.3 GB** | [魔搭数据集 windsing/next-trainer-portable](https://modelscope.cn/datasets/windsing/next-trainer-portable) |

魔搭路径示例：

```text
releases/v2.9.2-beta.1/Next-Trainer-v2.9.2-beta.1-full.7z
releases/v2.9.2-beta.1/Next-Trainer-v2.9.2-beta.1-lite.7z
```

稳定版（旧 UI）整合包仍见 [Releases](https://github.com/wochenlong/lora-scripts-next/releases) 中 **v2.9.1** 及更早条目。

---

## 怎么用

### A. 整合包（推荐内测用户）

1. 下载 **lite** 或 **full**，用 7-Zip 解压到**非中文、非空格**路径  
2. 双击根目录 **`run_gui.bat`**（首次会联网安装主环境依赖）  
3. 浏览器打开 **http://127.0.0.1:28000**  
4. 侧栏确认版本为 **`v2.9.2-beta.1 · 内测`**

要求：Windows 10/11，NVIDIA GPU（建议 RTX 20+）。

补充说明：[整合包补充说明](docs/portable-getting-started.md) · [打标模型目录](docs/tagger-models.md)

### B. 从源码运行 `dev`（Vue3）

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# 切换到 Vue3 内测分支
git fetch origin
git checkout dev
git pull origin dev

# Windows：准备环境后启动（需本机 Python 3.10）
.\run_gui.bat
# 或：python gui.py --dev
```

查看当前分支与版本：

```powershell
git branch --show-current   # 应为 dev
Get-Content VERSION         # 如 2.9.2-beta.1
```

前端源码在 `frontend/`（Vue 3 + Vite）。日常开发：

```powershell
cd frontend
npm install
npm run dev          # 热更新（需后端 gui 已启动）
npm run build        # 产物写入 frontend/dist，供 gui 静态托管
```

### C. 从 `main` 切到 `dev`（已有克隆）

```powershell
git fetch origin
git switch dev
# 若本地已有旧分支名，也可：git checkout -B dev origin/dev
git pull
```

回到稳定线：

```powershell
git switch main
git pull
```

> **注意：** `main` 与 `dev` 前端架构不同，不要混用未提交的 `frontend/dist` 热修。整合包用户以整包版本为准，不必手动切分支。

---

## Vue3 内测版功能（`dev`）

相对旧版侧栏多页 dist，**`dev` 为 Vue 3 单页工作台**：

| 模块 | 能力 |
|------|------|
| **训练** | 基础模型 × 训练引擎 × 训练目标；右侧 TOML 预览；校验 / 导入导出 / 开始训练 |
| **数据集** | 模型打标（内置 WD14）+ 标签编辑入口 |
| **任务** | 任务列表、状态、日志与监控入口；日常盯盘以任务页为主 |
| **设置** | UI 偏好、**训练引擎管理**（Kohya 内置 / Anima Fast 可选安装）、关于、更新日志 |
| **品牌与版本** | 产品名统一为 **Next Trainer**；内测号显示「内测」徽标 |
| **开源致谢** | 设置 → 关于；仓库另有 [开源引用](docs/credits.md) 子页 |

训练能力（引擎侧）与稳定线一致，包括：

- Anima LoRA / LoKr / T-LoRA、Anima Fast（插件）、Anima 全量微调  
- SD 1.5 / SDXL LoRA 与全量微调、Flux LoRA  
- 本地打标、训练监控（`/train-monitor`）、TensorBoard  

Anima Fast 文档：[docs/anima-fast.md](docs/anima-fast.md)

---

## 支持一览

| 模式 | 说明 |
|------|------|
| Anima LoRA | LoRA · LoKr · T-LoRA · 约 12GB 显存起 |
| Anima Fast | 可选独立运行时 · 建议 16GB+ · lite 包需页内安装，full 包已预装 |
| Anima 全量微调 | 完整 DiT · 建议约 24GB |
| SD 1.5 / SDXL | LoRA / 全量微调 |
| Flux | LoRA |

显存与进阶参数见 [docs/anima-training.md](docs/anima-training.md)。

---

## 文档

| 主题 | 链接 |
|------|------|
| **开源引用（子页）** | [docs/credits.md](docs/credits.md) |
| 法律向完整 NOTICE | [NOTICE.md](NOTICE.md) |
| 整合包补充 | [docs/portable-getting-started.md](docs/portable-getting-started.md) |
| 打标模型 | [docs/tagger-models.md](docs/tagger-models.md) |
| Anima Fast | [docs/anima-fast.md](docs/anima-fast.md) |
| 训练监控 | [docs/train-monitor.md](docs/train-monitor.md) |
| 仓库布局契约 | [docs/repo-layout.md](docs/repo-layout.md) |

---

## 常见问题（简）

**反馈 Bug 要带什么？**  
版本号（含 beta）、训练类型（模型/引擎/目标）、复现步骤、相关日志。→ [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite 和 full 怎么选？**  
只要 Kohya 标准训练 → lite；要开箱 Anima Fast → full（魔搭）。

**内测和稳定版能混用配置吗？**  
多数 TOML 可导入；导航与存储 key 有差异，以当前页「导入配置」为准。

---

<p align="center"><sub>维护：<a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">开源引用</a> · <a href="CONTRIBUTORS.md">贡献者</a></sub></p>
