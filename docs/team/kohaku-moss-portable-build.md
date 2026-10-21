# KohakuMoss 专用版整合包打包方案

> 面向接手打包的协作者。该整合包是 `KohakuMoss` 独立分支的专用产品，不属于 `main` / `dev` 通用整合包，也不合并回 `dev`。包内必须带完整 KohakuMossTrainer 训练环境；MOSS 底模通过魔搭 BAT 下载，不塞进 7z。

## 0. 可复制的任务卡

> 按 `docs/team/kohaku-moss-portable-build.md` 从干净的 `KohakuMoss` 独立分支构建 Windows 专用整合包。包内必须预装 KohakuMossTrainer 源码、独立 Python 3.12、Torch cu130、kogine 与 LyCORIS，并通过跨目录重定位测试；不预装 Kohya、Musubi 或 Anima Fast 训练环境。`tools/Download-MOSS-Model.bat` 必须可从魔搭断点续传并生成训练兼容的 MOSS-Image Base BF16 Comfy 单文件布局。完成双路径解压启动、内置环境审计、模型预检和 50 steps 真机短训，输出 7z、SHA256、文件清单及验收记录。禁止打入模型权重、训练集、输出、日志、Token、`doc/local` 或本机配置。

## 1. 交付目标

推荐文件名：

```text
Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z
Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z.sha256
kohaku-moss-preview.1-build-report.md
```

包型采用 **KohakuMoss 专用 GUI + 完整内置训练环境**：

- 这是 MOSS-Image / KohakuMossTrainer 专用包，不以通用 `main` / `dev` 包兼容性为定位。
- 不预装 Kohya、Musubi、Anima Fast 的训练环境。
- 预装 KohakuMossTrainer 钉版源码、独立 Python 3.12、Torch cu130、kogine、LyCORIS 和 CUDA 训练依赖。
- 用户首次启动时引擎必须直接为 `ready`，不能再要求联网安装训练环境。
- 不预装 MOSS 模型；提供魔搭一键下载 BAT。
- “完整训练环境”不等于内置训练底模；模型权重、训练集和输出仍与程序包分离。
- 默认模型和默认引擎固定为 MOSS-Image + KohakuMossTrainer。
- 根目录 `README.md` / `README-zh.md`、`docs/README.md`、`docs/getting-started*.md` 与
  `docs/MOSS.md` 必须是专用版内容，不得沿用通用版 Kohya、Musubi、Anima 或 Qwen 教程。

## 2. 已核实的技术结论

### 2.1 引擎状态

真实 RTX 4090 短训已经跑通：

- MOSS-Image Base
- 1024×1024、BF16、BS=1
- LoRA rank/alpha 32
- 50 steps，退出码 0
- 总耗时约 115 秒
- step 1 后显存约 8.52 GiB
- 同时导出 LyCORIS 与 Comfy 权重

训练成功依赖一个 Windows 回退修复：`triton-windows` 调用编译器失败时，
`subprocess.CalledProcessError` 必须被识别为可回退的构建错误。打包分支中的安装器会在钉版上游检出后自动应用该补丁，并在环境审计中检查补丁是否存在。

### 2.2 MOSS 模型下载组合

训练器默认读取：

```text
Next-Trainer/sd-models/moss-image/
  dit.safetensors
  text_encoder.safetensors
  vae.safetensors
  tokenizer/
    tokenizer.json
    tokenizer_config.json
    chat_template.jinja
```

不能直接下载 Comfy 常用的 INT8 / GPTQ 组合进行训练：

- INT8 ConvRot DiT 不是当前训练底模路径。
- GPTQ / INT8 文本编码器不满足当前 KohakuMoss 训练键名契约。
- `Comfy-Org/MOSS-Image` 的 BF16 文本编码器使用 `model.language_model.*` 前缀，当前引擎需要原生 `language_model.*` 前缀。

因此下载器采用以下可训练组合，全部来自魔搭：

| 目标 | 魔搭来源 | 处理 |
|---|---|---|
| `dit.safetensors` | `Comfy-Org/MOSS-Image` 的 Base BF16 DiT | 原样下载；融合 QKV 由引擎直接支持 |
| `text_encoder.safetensors` | `openmoss/MOSS-Image-Base` 原生 4 个 BF16 分片 | 流式合并为单文件，保留 `language_model.*` |
| `vae.safetensors` | `Comfy-Org/MOSS-Image` 的 `flux2-vae_small` | 原样下载 |
| `tokenizer/` | `openmoss/MOSS-Image-Base` | 原样下载 |

最终约 27 GB。下载器具有：

- 断点续传
- 文件尺寸与 SHA256 校验
- 文本编码器低额外磁盘占用流式合并
- DiT / 文本编码器 / VAE 关键权重形状检查
- 已有兼容文件自动跳过

## 3. 构建机要求

- Windows 10/11 x64
- NVIDIA GPU；最终验收建议 24 GB 显存
- PowerShell 5.1+
- Node.js 22.17.1
- Git、Git LFS、7-Zip
- 至少 80 GB 构建空间；若同时执行模型短训验收，建议预留 150 GB
- 网络可访问 GitHub、PyPI/PyTorch 源和魔搭

开始前确认：

```powershell
node --version
npm --version
git --version
7z
nvidia-smi
```

## 4. 构建来源

必须从干净工作树构建，不得直接打包维护者日常工作目录。

```powershell
git fetch origin
git worktree add D:\build\next-trainer-kohaku-moss KohakuMoss
Set-Location D:\build\next-trainer-kohaku-moss
git status --short
git rev-parse HEAD
```

要求：

- `git status --short` 为空。
- 记录构建 commit，禁止用未提交文件打包。
- 只能从 `KohakuMoss` 独立分支或其明确 tag 构建；禁止替换为 `origin/main`、`origin/dev` 或通用 Release。
- `KohakuMoss` 保持独立分支，不向 `dev` 合并。
- 包内更新通道只能跟踪 `KohakuMoss`；不得使用 Release 更新器把通用 `main` 版本覆盖进来。
- 工作日 09:00–18:00（Asia/Shanghai）禁止 push 或其它远程写入；本地构建与测试不受影响。

## 5. 构建前门禁

```powershell
python -m pytest `
  tests/test_kohaku_moss_engine.py `
  tests/test_portable_moss_downloader.py `
  tests/test_portable_packaging_scripts.py -q

Set-Location frontend
npm ci
npm test -- --run `
  src/i18n/index.test.ts `
  src/training/modules.test.ts `
  src/training/moss.test.ts
npm run build
Set-Location ..

git diff --check
```

必须全部通过。大 bundle 警告可记录，不作为本预览包阻断项。

## 6. 生成便携目录

先生成目录，不急于压缩：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\build-scripts\build_portable.ps1 `
  -Version "3.3.0-kohaku-moss-preview.1" `
  -Clean `
  -Skip7z `
  -PackageSuffix "kohaku-moss"
```

这里使用 GUI/lite 骨架，再把完整 KohakuMoss 运行时安装进便携树；不得调用
`build_portable_kohya_only.ps1` 或 `build_portable_2026_full.ps1`，避免混入 Kohya / Musubi 训练环境。

完成 §7 后的预期目录：

```text
build/Next-Trainer-Portable/
  启动.bat
  检查更新.bat
  说明.txt
  python_embeded/
  Next-Trainer/
    README.md
    README-zh.md
    docs/
      README.md
      getting-started.md
      MOSS.md
    extensions/
      kohaku-moss/
        source/
        .python/
        .venv/
        install_state.json
  tools/
    Download-MOSS-Model.bat
```

完成环境安装后重点检查：

```powershell
Test-Path .\build\Next-Trainer-Portable\tools\Download-MOSS-Model.bat
Test-Path .\build\Next-Trainer-Portable\Next-Trainer\scripts\portable\download_moss_model.py
Test-Path .\build\Next-Trainer-Portable\Next-Trainer\mikazuki\engines\kohaku_moss\patch_upstream.py
Test-Path .\build\Next-Trainer-Portable\Next-Trainer\extensions\kohaku-moss\.python
Test-Path .\build\Next-Trainer-Portable\Next-Trainer\extensions\kohaku-moss\.venv\Scripts\python.exe
```

五项必须都是 `True`。

## 7. 在便携树内安装完整 KohakuMoss 训练环境

必须直接安装到待压缩的便携树，禁止从维护者日常工作区复制现成 venv：

```text
build/Next-Trainer-Portable/Next-Trainer/extensions/kohaku-moss/
```

步骤：

1. 从 `build/Next-Trainer-Portable/run_gui.bat` 启动未压缩便携树。
2. 进入 MOSS-Image 训练页，点击“安装实验性引擎”。
3. 等待状态变为 `ready`，关闭 WebUI 和终端。
4. 确认环境包含：
   - `source/.git` 与钉版 KohakuMossTrainer 源码
   - `.python/` 下的 uv 托管 Python 3.12
   - `.venv/` 下的 Torch cu130、kogine、KohakuMoss、KohakuEngine、LyCORIS
   - `install_state.json`
5. 确认上游 Windows Triton 回退补丁已应用。
6. 删除下载缓存、`__pycache__`、测试输出和临时日志，但不得删除 `.python`、`.venv`、`source/.git`。

检查命令：

```powershell
$root = Resolve-Path .\build\Next-Trainer-Portable
$trainer = Join-Path $root "Next-Trainer"
$runtime = Join-Path $trainer "extensions\kohaku-moss"
$python = Join-Path $runtime ".venv\Scripts\python.exe"

& $python -c "import torch, kohakumoss, kohakuengine, lycoris; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
& git -C (Join-Path $runtime "source") rev-parse HEAD
Get-Content (Join-Path $runtime ".venv\pyvenv.cfg")
Get-Content (Join-Path $runtime "install_state.json")
```

要求：

- Python 为 3.12。
- Torch 为 cu130 训练环境，`torch.cuda.is_available()` 为 `True`。
- 上游 commit 与 `mikazuki/engines/kohaku_moss/manifest.py` 一致。
- `install_state.json` 为 `ready`。
- 环境审计事实含 `windows_build_fallback=true`。

### 7.1 便携重定位要求

`.venv/pyvenv.cfg` 会记录构建目录的绝对 Python 路径。专用分支已在状态检查中接入
`portable_venv.repair_venv_base()`：解压路径变化且旧路径失效时，自动把 venv 指向包内
`extensions/kohaku-moss/.python/`。

打包者必须验证：

1. 把整个便携目录复制到另一盘符和中文空格路径。
2. 临时确保原构建目录不可见，防止误用旧 Python。
3. 启动 WebUI，读取 KohakuMoss 状态。
4. 状态必须直接为 `ready`。
5. 新位置的 `pyvenv.cfg` 必须已改写为新目录下的 `.python`。
6. 运行 `.venv\Scripts\python.exe` 导入 Torch / KohakuMoss / LyCORIS。

任一步失败都不得发布。禁止用“用户首次启动后重新安装环境”规避重定位问题。

### 7.2 应用专用版根目录布局

完整环境安装并停止进程后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\build-scripts\apply_portable_2026_root.ps1 `
  -PortableRoot .\build\Next-Trainer-Portable
```

此后用户只看到 `启动.bat`、`检查更新.bat`、`说明.txt`；模型下载器位于 `tools\`。

## 8. BAT 下载器验收

在便携目录中双击：

```text
tools\Download-MOSS-Model.bat
```

验收流程：

1. 下载到一半关闭窗口。
2. 再次运行，确认从 `.part` 文件续传，而非清零重下。
3. 下载结束后确认约 27 GB，且没有残留完整的四个文本编码器分片。
4. 再运行一次，确认兼容文件被跳过。
5. 删除一个 tokenizer 小文件，再运行，确认只补缺失文件。

结果目录必须符合 §2.2。运行：

```powershell
Get-ChildItem .\build\Next-Trainer-Portable\Next-Trainer\sd-models\moss-image -Recurse
```

下载器必须生成 `download-manifest.json`，并报告布局校验通过。

## 9. 解压与启动验收

至少测试两处完全不同的解压路径：

```text
C:\NT-KohakuMoss-Test\
D:\测试 空格\Next Trainer KohakuMoss\
```

每处均执行：

1. 双击 `启动.bat`。
2. 浏览器能打开 WebUI。
3. 首页首张海报为 MOSS，无乱码、无黑屏。
4. 点击“训练”，默认模型为 MOSS-Image。
5. 默认推荐引擎为 KohakuMossTrainer。
6. KohakuMossTrainer 无需联网安装，首次启动直接显示 `ready`。
7. `tools\Download-MOSS-Model.bat` 能正确定位该解压目录。

## 10. 内置训练环境验收

在每个最终解压路径中直接审计内置 KohakuMossTrainer。

验收：

- 包内独立 Python 3.12 可直接运行。
- Torch / CUDA / LyCORIS / kogine 导入审计通过。
- 状态为 `ready`。
- 审计事实中 `windows_build_fallback=true`。
- `pyvenv.cfg` 已自动改写到当前解压目录内的 `.python`。
- 重启 WebUI 后仍为 `ready`。
- 断网重启时环境仍为 `ready`，不得触发依赖下载。

## 11. 真机短训验收

使用可公开的 2 张测试图，配置：

```text
模型：MOSS-Image Base
输入：ComfyUI files
分辨率：1024×1024
精度：BF16
Batching：count
Batch size：1
训练步数：50
网络：LoRA
Rank / Alpha：32 / 32
学习率：1e-4
Warmup：5
Triton tune：table（用于验证编译失败可自动回退）
```

通过标准：

- 进程退出码 0。
- step 从 1 运行到 50。
- loss 为有限值，无 NaN/Inf。
- Windows 无可用编译器时自动回退 eager，而不是终止训练。
- 输出同时存在：
  - `*-lycoris.safetensors`
  - `*-comfy.safetensors`
- 任务页状态、日志链接和输出目录正确。

同时记录：

- GPU 型号与驱动
- Torch / CUDA 版本
- 峰值显存
- 总耗时
- 最后一步 loss
- 两个输出文件大小与 SHA256

## 12. 隐私与内容审计

压缩前禁止包含：

```text
sd-models/moss-image/*.safetensors
train/*
output/*
logs/*
config/autosave/*
doc/local/*
*.token
*.env
个人 preset
浏览器数据
```

检查：

```powershell
Get-ChildItem .\build\Next-Trainer-Portable -Recurse -Force |
  Where-Object {
    $_.FullName -match '\\(output|logs|autosave|doc\\local)\\' -or
    $_.Name -match '\.(safetensors|ckpt|pt)$'
  } |
  Select-Object FullName, Length
```

仅允许项目自身必要的小型测试/资源文件；发现模型权重或个人数据立即停止发布。

## 13. 便携包验证与压缩

先执行仓库已有验证器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\portable\verify_portable_release.ps1 `
  -PortableRoot .\build\Next-Trainer-Portable
```

验证通过后压缩：

```powershell
7z a -t7z -mx=9 -mmt=on `
  .\build\Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z `
  .\build\Next-Trainer-Portable\*

Get-FileHash `
  .\build\Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z `
  -Algorithm SHA256
```

再把 7z 解压到新的临时目录，重复 §9 的启动检查。禁止只测未压缩构建目录。

## 14. 最终验收清单

- [ ] 来源是干净的 `KohakuMoss` 独立分支 commit
- [ ] 未混用 `main` / `dev` / 通用 Release 代码或更新通道
- [ ] Python、前端和整合包定向测试通过
- [ ] 包内没有 MOSS 底模与用户数据
- [ ] 包内完整包含 KohakuMossTrainer 源码、Python 3.12、Torch cu130、kogine 与 LyCORIS
- [ ] 包内未预装 Kohya、Musubi、Anima Fast 训练环境
- [ ] `tools\Download-MOSS-Model.bat` 存在
- [ ] BAT 可断点续传、校验 SHA256、生成兼容布局
- [ ] 首页 MOSS 海报和中英文文案无乱码
- [ ] 根 README、快速开始与 `docs/MOSS.md` 均为 KohakuMoss 专用内容
- [ ] `说明.txt` 能正确指向 `Next-Trainer\docs\MOSS.md`
- [ ] MOSS-Image / KohakuMossTrainer 为默认选择
- [ ] 两个不同路径均可启动
- [ ] KohakuMoss 首次启动、重定位、断网重启审计均为 `ready`
- [ ] 50 steps 真机短训通过
- [ ] LyCORIS 与 Comfy 两种输出存在
- [ ] 7z 二次解压 smoke test 通过
- [ ] SHA256、文件清单和构建报告齐全

## 15. 构建报告模板

```markdown
# KohakuMoss Preview Build Report

- Branch:
- Commit:
- Build host:
- GPU / driver:
- Package:
- SHA256:
- Uncompressed / compressed size:

## Gates
- Python tests:
- Frontend tests/build:
- Portable verifier:
- Privacy scan:

## Model downloader
- Resume tested:
- Re-run skip tested:
- Layout validation:
- Final model bytes:

## Engine
- Bundled runtime:
- Python 3.12:
- Torch / CUDA:
- kogine / KohakuMoss / LyCORIS:
- Audit:
- windows_build_fallback:
- Relocation:
- Offline restart:
- Restart:

## 50-step smoke
- Exit:
- Duration:
- Peak VRAM:
- Final loss:
- LyCORIS output SHA256:
- Comfy output SHA256:

## Known limitations
- MOSS model is not included in the 7z.
```
