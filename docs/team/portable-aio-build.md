# 合作者任务：打 AIO 整合包（All In One = Kohya + Musubi + Anima Fast）

> **给有构建机 / 有百度网盘的合作者**（可把本文整份丢给 Codex 执行）。  
> 仓库：[`wochenlong/lora-scripts-next`](https://github.com/wochenlong/lora-scripts-next)  
> 产品名：Next Trainer  
> **系列后缀：`AIO`**（**A**ll **I**n **O**ne）  
> 目标制品名：`Next-Trainer-v3.0.0-AIO.7z`  
> 分发渠道：**百度网盘**（体积常约 **数 GB～10GB+**，不适合 GitHub / 魔搭整包强传）

### 命名硬约束（必读）

| 项 | 正确写法 |
|----|----------|
| 完整包系列后缀 | **`AIO`**（All In One），例：`Next-Trainer-v3.0.0-AIO.7z` |
| 未压缩构建目录 | `build\Next-Trainer-Portable\` |
| 应用副本（含 `gui.py`） | `build\Next-Trainer-Portable\Next-Trainer\` |
| 更新脚本（进 tools） | `Update-Next-Trainer.bat` / `Update-Next-Trainer-Release.bat` |

**不要**再用 `kohya-musubi-fast` 当发布后缀；那只是内容描述，对外文件名统一 **`-AIO`**。  
**不要**再写 / 再找 `SD-Trainer` 应用目录；当前 **`main` 统一用 Next-Trainer**。必须以干净 `origin/main` 为准。

---

## 0. 给 Codex 的一句话任务卡（复制即用）

> 读 `docs/team/portable-aio-build.md`，按文档从干净 `main` 工作树打出 **AIO**（All In One = Kohya + Musubi + Anima Fast）整合包。路径一律用 **`Next-Trainer-Portable` / `Next-Trainer`**。发布文件命名 **`Next-Trainer-v3.0.0-AIO.7z`**，算 SHA256，整理百度网盘上传说明；禁止打入训练底模、个人数据、Token、`doc/local`。所有 `gh` 若用到必须 `-R wochenlong/lora-scripts-next`。

---

## 1. 产品定位（先读，避免做错包）

| 项 | 说明 |
|----|------|
| **AIO** 是什么 | **All In One**：主环境 Kohya（cu128）+ Musubi（cu128）+ Anima Fast 独立 venv（cu130），解压即可三类能力开训（仍不含训练底模） |
| AIO 不是什么 | **不是**默认产品线。正式对外仍以 lite / kohya / musubi 为主；Fast 默认仍是「设置页安装」 |
| 为何单独打 | Fast 的 cu130 栈体积大，三栈叠在一起后压缩包往往 **很大**，魔搭/GitHub 难传；**百度网盘**更合适 |
| 禁止打入 | 训练底模、个人 `data/`、输出、Token、`doc/local`、维护机私货 |

包型对照：

| 文件名模式 | 预装 | 备注 |
|------------|------|------|
| `*-lite.7z` | 几乎无训练环境 | 默认渠道 |
| `*-kohya.7z` | 仅 Kohya | 默认渠道 |
| `*-musubi.7z` | 仅 Musubi（Krea2） | 默认渠道 |
| `*-kohya-musubi.7z` | Kohya + Musubi，无 Fast | 可选双引擎 |
| **`*-AIO.7z`**（本文） | Kohya + Musubi + **Anima Fast** | **AIO 系列**；网盘分发 |

---

## 2. 前置条件

### 2.1 机器

- Windows（构建脚本为 PowerShell）
- 磁盘：建议空闲 **≥ 80GB**（源码树 + 未压缩便携目录 + 7z + Fast 下载缓存）
- NVIDIA 驱动可用（装 Fast / 验 torch 时更稳）
- 稳定外网（Kohya / Musubi / Fast 首次都会下数 GB 依赖）
- 已装：[7-Zip](https://www.7-zip.org/)（默认 `C:\Program Files\7-Zip\7z.exe`）、Git

### 2.2 源码基线

- 以发布基线为准：分支 **`main`**，版本号与 `VERSION` 文件一致（例如 `3.0.0`）
- **不要**在脏工作区（有大量未提交改动的日常目录）上直接打正式包
- 推荐：单独 worktree / 干净 clone，例如：

```powershell
cd D:\ai
git clone https://github.com/wochenlong/lora-scripts-next.git lora-scripts-next-aio-3.0.0
cd lora-scripts-next-aio-3.0.0
git checkout main
git pull
# 核对：git rev-parse HEAD；Get-Content VERSION
# 核对脚本：Select-String -Path .\build-scripts\build_portable.ps1 -Pattern 'Next-Trainer-Portable'
```

可选加速：若本机已有默认打标模型缓存，构建时可传 `-TaggerCacheSource`（见下文）。

### 2.3 本任务不要求

- 不要求把 AIO 传到 GitHub Release / 魔搭（除非维护者另说）
- 不要求改 README 默认下载表（AIO 属加码 / 网盘渠道）

---

## 3. 构建步骤（推荐流水线）

整体顺序：

```text
干净 main
  → build_portable_2026_full.ps1（Kohya + Musubi，先 Skip7z）
  → 在便携树 Next-Trainer 内安装 Anima Fast
  → 改「说明.txt」写明本包为 AIO（含 Fast）
  → 清理不该进包的目录
  → 7z 打成 Next-Trainer-v*-AIO.7z
  → 算 SHA256 / 体积
  → 上传百度网盘并回报链接
```

### 3.1 打出 Kohya + Musubi（先不要最终 7z）

在**干净源码根**执行：

```powershell
cd D:\ai\lora-scripts-next-aio-3.0.0   # 换成你的干净树

# 可选：Clean 清掉旧 build\Next-Trainer-Portable
# 可选：-TaggerCacheSource 'D:\path\to\tagger-models' 复用打标缓存

powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\build_portable_2026_full.ps1 `
  -Version '3.0.0' `
  -Clean `
  -Skip7z
```

成功标志：

- 目录存在：`build\Next-Trainer-Portable\python_embeded\python.exe`
- 目录存在：`build\Next-Trainer-Portable\Next-Trainer\gui.py`
- Musubi 已装（见引擎状态 / `Next-Trainer\vendor\musubi-tuner` + 引擎 venv）
- 日志在：`build\portable-2026-logs\`

若 Kohya 已烤好、只差续跑 Musubi / 根目录 UX，可用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-scripts\resume_portable_2026_full.ps1 `
  -Version '3.0.0' `
  -Skip7z
```

> `build_portable_2026_full.ps1` 产物内容是 Kohya+Musubi，**还不是 AIO**；必须再执行 §3.2 装 Fast 后才可命名为 `-AIO`。

### 3.2 在便携树内安装 Anima Fast

把「项目根」指到便携包里的 **`Next-Trainer`**，用旁边的 `python_embeded` 跑安装脚本（与用户页内安装同源逻辑）：

```powershell
$portable = 'D:\ai\lora-scripts-next-aio-3.0.0\build\Next-Trainer-Portable'
$app = Join-Path $portable 'Next-Trainer'
$py = Join-Path $portable 'python_embeded\python.exe'

if (-not (Test-Path (Join-Path $app 'gui.py'))) {
    throw "Missing Next-Trainer\gui.py — wrong tree or legacy SD-Trainer layout"
}

$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $app

# 预检（可选）
& $py -s (Join-Path $app 'scripts\cli\install_anima_fast.py') --project-root $app --dry-run

# 正式安装（下载数 GB，耗时长；需稳定网络）
& $py -s (Join-Path $app 'scripts\cli\install_anima_fast.py') --project-root $app
if ($LASTEXITCODE -ne 0) { throw "Anima Fast install failed: $LASTEXITCODE" }
```

也可用便携树内 bat（在 `Next-Trainer` 语境下）：

```powershell
cd $app
.\scripts\cli\install_anima_fast.bat
```

成功标志：

- 存在：`Next-Trainer\extensions\anima_lora\.venv\`
- 存在：`Next-Trainer\extensions\anima_lora\.venv\Scripts\python.exe`
- 安装脚本打印 Fast 状态为可训 / ready（措辞以脚本输出为准）

可选冒烟：

```powershell
& (Join-Path $app 'extensions\anima_lora\.venv\Scripts\python.exe') -c "import torch; print(torch.__version__)"
```

### 3.3 更新根目录「说明.txt」

`build_portable_2026_full` + `apply_portable_2026_root.ps1` 会生成三入口 UX：`启动.bat` / `检查更新.bat` / `说明.txt`。  
AIO 包务必改说明，避免用户以为「不含 Fast」：

路径示例：`build\Next-Trainer-Portable\说明.txt`

建议写明：

- 本包为 **AIO（All In One）**
- 已预装 Kohya（cu128）
- 已预装 Musubi（cu128）
- **已预装 Anima Fast**（`Next-Trainer\extensions\anima_lora\.venv`，cu130）
- 仍不含训练底模（模型放 `Next-Trainer\sd-models\`）
- 体积大，属网盘加码包，非默认下载项

### 3.4 打包前清理（必做）

在 `build\Next-Trainer-Portable` 内检查并删除（若存在且非空/含隐私）：

| 路径 / 模式 | 原因 |
|-------------|------|
| `Next-Trainer\data\` 下个人数据集 | 隐私 / 体积 |
| `Next-Trainer\output\`、训练日志缓存 | 体积 |
| `**/__pycache__`、无用深层垃圾 | 体积 |
| Token、`.env`、含密钥配置 | 安全 |
| `doc\local\`（若被拷入） | 本地交接勿外发 |
| 训练底模 `*.safetensors`（非默认打标模型） | 体积与许可 |

**保留**：

- `python_embeded\`（Kohya 主环境）
- Musubi 引擎目录与其 venv
- `Next-Trainer\extensions\anima_lora\`（含 `.venv`）
- 默认打标模型缓存（若构建流程已预置）
- 浅层 `Next-Trainer\.git`（若构建脚本嵌入，供 `Update-Next-Trainer.bat` 使用）

### 3.5 打 7z（solid，利于重复 torch 树压缩）

```powershell
$portable = 'D:\ai\lora-scripts-next-aio-3.0.0\build\Next-Trainer-Portable'
$out = 'D:\ai\lora-scripts-next-aio-3.0.0\build\Next-Trainer-v3.0.0-AIO.7z'
$7z = 'C:\Program Files\7-Zip\7z.exe'

if (Test-Path $out) { Remove-Item $out -Force }

# solid LZMA2；耗时长、吃内存与磁盘
& $7z a -t7z -mx=9 -m0=LZMA2:d=64m -ms=on -mmt=on $out "$portable\*"
if ($LASTEXITCODE -ne 0) { throw "7z failed: $LASTEXITCODE" }

Get-Item $out | Select-Object FullName, Length
Get-FileHash $out -Algorithm SHA256
```

预期：压缩包体积常在 **数 GB～约 10GB+**（视 Fast / Torch 重复与压缩率而定）。  
若单文件对某网盘不友好，可用 7z 分卷（例如 `-v4g`），文件名保持 `Next-Trainer-v3.0.0-AIO.7z.001` 这类分卷，并在回报里写清列表与校验方式。

---

## 4. 验收清单（上传前）

- [ ] 文件名：`Next-Trainer-v3.0.0-AIO.7z`（后缀必须是 **AIO**）
- [ ] 解压根目录可见：`启动.bat`、`检查更新.bat`、`说明.txt`（说明写明 AIO / 含 Fast）
- [ ] 应用目录名是 **`Next-Trainer\`**（不是 `SD-Trainer\`）
- [ ] Kohya：能 `启动.bat` 打开 WebUI（`http://127.0.0.1:28000`）
- [ ] Musubi：设置 / 引擎页显示 Musubi 可用（可训 Krea 2）
- [ ] Fast：`Next-Trainer\extensions\anima_lora\.venv` 存在；设置或 Fast 页不再要求「从零安装环境」（允许轻微状态刷新）
- [ ] **无**训练底模、无个人数据、无 Token
- [ ] 已记录：**字节大小** + **SHA256**

---

## 5. 分发：百度网盘（主渠道）

1. 上传 `Next-Trainer-v3.0.0-AIO.7z`（或分卷）到合作者 / 项目约定网盘目录。  
2. 开启可分享链接（按项目习惯设提取码）。  
3. 向维护者 [@wochenlong](https://github.com/wochenlong) 回报（Issue / Discussion / 群均可），模板：

```text
AIO 整合包已上传（百度网盘）

文件: Next-Trainer-v3.0.0-AIO.7z
含义: All In One = Kohya + Musubi + Anima Fast
大小: <bytes 与 GiB>
SHA256: <哈希>
源码: main @ <完整 commit SHA>
VERSION: 3.0.0
布局: Next-Trainer-Portable / Next-Trainer（非 SD-Trainer）
预装: Kohya cu128 + Musubi cu128 + Anima Fast (.venv cu130)
网盘链接: <URL>
提取码: <若有>
备注: 未打底模；说明.txt 已写明 AIO
```

**不要默认**：把 ~10GB AIO 塞进 GitHub Release 或魔搭单 blob（易失败）。若维护者之后要镜像，由维护者另安排。

---

## 6. 常见失败与处理

| 现象 | 处理 |
|------|------|
| 找不到 `SD-Trainer\` | **正常**：现应用目录是 `Next-Trainer\`；若脚本仍写旧名，说明没用干净 `main` |
| `setup_environment.py` / torch 下载中断 | 重跑；必要时清 `build\Next-Trainer-Portable` 后 `-Clean` 重来 |
| Musubi clone / install 失败 | 查网络与 `Next-Trainer\vendor\musubi-tuner`；可 `resume_portable_2026_full.ps1 -Skip7z` |
| Fast 安装失败 / uv 报错 | 看终端完整日志；确认用的是便携树的 `python_embeded` + `--project-root` 指向 `Next-Trainer`；稳定镜像后重试 |
| 7z 磁盘不足 | 换大盘；或先删源码树外缓存；分卷输出到其它盘 |
| 包内误带 `data/` | 重新清理后重打 7z，勿直接外传 |

相关参考（不必先读完也能按本文做）：

- [`docs/design/portable-2026.md`](../design/portable-2026.md) — 默认包不含 Fast 的设计原因  
- [`docs/anima-fast.md`](../anima-fast.md) — Fast 安装与 cu130 说明  
- [`docs/portable-1.5-krea2-guide.md`](../portable-1.5-krea2-guide.md) — kohya-musubi（无 Fast）用户说明  
- [`build-scripts/build_portable_2026_full.ps1`](../../build-scripts/build_portable_2026_full.ps1) — Kohya+Musubi 脚本（`main` 上输出 `Next-Trainer-Portable`）  
- [`scripts/cli/install_anima_fast.py`](../../scripts/cli/install_anima_fast.py) — Fast CLI 安装  

---


