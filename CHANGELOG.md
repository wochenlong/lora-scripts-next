# 更新日志

本文件记录 **wochenlong/lora-scripts-next** 面向镜像与 AutoDL 的发行说明；上游 kohya-ss/sd-scripts 的变更请见其仓库。

---

## v2.7.1 — 2026-06-14

### Bug 修复（前端 dist）

- **#121** 侧栏中英文切换不再丢失：语言选择由 `sessionStorage` 改存 `localStorage`，关闭重开浏览器后保持；启动时一次性迁移旧 `sessionStorage` 值并清理，检测逻辑改为纯读取无副作用。
- **#121** 英文模式下底部主题按钮残留中文「灯泡」：新增 `灯泡 → Theme` 映射，将 `.sidebar-bottom` 纳入文本替换范围，并翻译主题按钮 `title`（`toggle color mode`）提示。

### 资源版本

- `sd-nav-i18n.js` / `sd-trainer-brand.js` 的 cache 查询参数随 `VERSION` 统一为 `?v=2.7.1`（由 `scripts/patch-ui-brand-version.py` 生成），确保旧缓存的客户端加载到修复后的脚本。

---

## v2.7.0 — 2026-05-28

### Anima LoRA Fast 模式（可选插件）

- **训练入口**：WebUI 侧栏「Anima LoRA → Fast 模式」（`/lora/anima-fast.html`），`model_train_type: anima-lora-fast` 路由至 `extensions/anima_lora/` 独立 venv 与 `train.py`。
- **页内安装器**：一键克隆/快照上游 [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora)（MIT），创建 cu130 插件环境；未就绪时拒绝开训。
- **训练监控**：Loss / ETA / Epoch 与 Fast 专用 `*.progress.jsonl` 同步；预览图按活动任务 `output_dir` 发现。
- **文档与对标**：[`docs/anima-fast.md`](docs/anima-fast.md)、[`docs/examples/anima-lora-benchmark-*.toml`](docs/examples/)；4090 同参约 **2.5×** 加速（标准 Kohya ≈7.1 s/step vs Fast ≈2.8 s/step）。
- **归属**：[`NOTICE.md`](NOTICE.md) § Anima LoRA Fast Mode；Fast 页与文档致谢 upstream。

### 前端（dist）

- Fast 页安装引导、开源致谢（`anima-fast-credit`）；首页/更新日志 v2.7.0 条目。

### 整合包说明

- **不预装** Fast 插件 venv（`extensions/anima_lora/.venv`）；用户首次在 Fast 页点击「开启插件」安装，避免 7z 体积暴增。

### 环境变量

- `LORA_ENABLE_ANIMA_FAST=1`（默认开启 Fast 入口；设为 `0` 可隐藏侧栏与 API）。

### v2.7.0 整合包热更新 — 2026-06-02（第三次重发）

> 同 tag **v2.7.0** 重发 7z（`PORTABLE_BUILD` **`65df2ba`**，约 **381.3 MB**）。相对 **`18e15cc`** 构建新增下列内容；更早相对初版 7z 的修复见上一节历史说明。

#### 整合包 / 更新器

- **Bootstrap 自更新（`UPDATER_VERSION=2`）**：运行 `Update-*.bat` 前先从 GitHub `main` 同步最新更新脚本（SHA256 比对），有变更则自动重启后再执行 Git / Release 更新；网络失败回退本地 bundled 脚本。
- **版本信息展示**：更新开始时打印 **本地 VERSION / PORTABLE_BUILD / git**、**线上 main VERSION**、**最新 Release**、**本地 vs 线上 UPDATER_VERSION**。
- 团队约定与变迁索引：[Discussion #73](https://github.com/wochenlong/lora-scripts-next/discussions/73)。

#### Bug 修复（相对 `18e15cc` 7z 新增）

- **#72** Anima Fast 插件安装：`EnvironmentInstallPlan` 为 frozen dataclass，改用 `dataclasses.replace` 设置 `source_root`，修复 `cannot assign to field 'source_root'`。

#### 升级指引

| 场景 | 操作 |
|------|------|
| 已装 **v2.7.0 整合包**（任意 `PORTABLE_BUILD`） | **`Update-SD-Trainer-Release.bat`**（推荐）或 **`Update-SD-Trainer.bat`** |
| 从 v2.5.x / v2.6.x | 保留用户数据目录后 Release 更新或下载本 7z |
| 无 `.git` 的旧包 | **Release 更新** 或整包下载 |

更新后确认 **`SD-Trainer/PORTABLE_BUILD`** 第一行为 **`65df2ba`**，`scripts/portable/UPDATER_VERSION` 为 **`2`**。

### v2.7.0 整合包热更新 — 2026-06-01（第二次重发，已 supersede）

> 同 tag **v2.7.0** 重发 7z（`PORTABLE_BUILD` **`18e15cc`**，约 **381.6 MB**）。初版 Release 7z 为 `7841f19` 前后构建，不含下列修复。**已被 2026-06-02 `65df2ba` 构建取代。**

#### 整合包 / 更新器

- **同 VERSION 重发无法更新**：Release 合并去掉 `robocopy /XO`，改用 `/IS /IT`，确保重发 7z 能覆盖本地较新的文件时间戳。
- 新增 **`SD-Trainer/PORTABLE_BUILD`**（git short SHA + `built_at` + version），便于对比是否已同步最新构建。
- Release 更新后写入 **`config/.portable_release_sync.json`**（Release 资产 id / 更新时间）。
- 修复 **`update_from_release.ps1`** PowerShell 字符串解析（尾随 `\`、方括号等导致脚本后半段未执行）。
- Release 合并后**显式同步** `SD-Trainer/.git`；打包时写入 `scripts/portable/templates/Update-*.bat`，避免根目录仍为 v2.5 时代「仅 `git pull`、无 `.git` 检查仍显示完成」的旧脚本。

#### Bug 修复（本重发包相对初版 7z 新增）

- **#66** Anima Fast：SPA 进入 Fast 页侧栏「开启插件」、安装报 `Anima source root does not exist`、CLI 安装后一直「检查中」；统一 `source_root` / 安装前 clone 逻辑。
- **#71** SDXL LoRA 使用 State resume 报 `KeyError: 'step'`；将 accelerate resume step fallback port 到 `scripts/stable/`。
- **#70** 训练页移动端布局堆叠与导航折叠按钮。
- **#69** 预览图 multiline sample prompt 文件合并修复。
- **#68** Anima Finetune 训练监控 Loss 曲线显示。
- **训练**：`mixed_precision` 从 TOML 正确转发到 accelerate launch。

#### 升级指引

| 场景 | 操作 |
|------|------|
| 已装 **初版 v2.7.0 整合包** | **`Update-SD-Trainer-Release.bat`**（推荐）或 **`Update-SD-Trainer.bat`**（Git 快进；有本地差异时会自动 stash） |
| 从 v2.5.x / v2.6.x | 保留 `sd-models/`、`output/`、`logs/`、`SD-Trainer/extensions/`，解压新版或 Release 更新 |
| 无 `.git` 的旧包 | 必须用 **Release 更新** 或下载本 7z |

更新后确认 **`SD-Trainer/PORTABLE_BUILD`** 第一行为 **`18e15cc`**。

---

## v2.6.0 — 2026-05-28

### Anima 全量微调（Finetune）

- **训练入口**：WebUI 侧栏「全量微调 → Anima Finetune」（`/lora/anima-finetune.html`），`model_train_type: anima-finetune` 路由至 `scripts/dev/anima_train.py`（上游 `anima_train.py`）。
- **Schema 与适配**：新增 `mikazuki/schema/anima-finetune.ts`；`adapt_anima_config(finetune=True)` 剥离 LoRA 网络字段；默认学习率 `1e-5`。
- **导航与首页**：「全量微调」分组（Anima Finetune 在 Stable Diffusion / Dreambooth 之前）；首页 portal、新手上路引导同步。
- **训练监控**：识别 `anima_train.py` 时显示 **Anima Finetune**（不再误标为 Anima LoRA）。
- **文档与示例**：`docs/anima-backend.md`、`docs/examples/anima-full-finetune.toml`；单元测试覆盖路由、wrapper、adapter、监控类型推断。

### 前端（dist）

- 修复 SPA 页面组件 `i0` 映射缺失导致的右栏 **404 Not Found**。
- Anima Finetune 页右栏标语与说明文案（进阶玩家、充足样本与高显存）。

### 实测参考

- RTX 4090 24GB、1024 分辨率：全量微调专用显存约 **23–24 GB**（与 LoRA 的 12 GB 档不同，需单独规划显存）。

---

## v2.5.3 — 2026-05-27

### 整合包热修复（[#54](https://github.com/wochenlong/lora-scripts-next/issues/54)）

- **依赖健康检查**：便携启动不再仅以 `torch` 目录是否存在判断「已安装」；启动前会探测 `torch`、`torchvision`、`accelerate`、`diffusers`、`gradio` 等关键包，不完整时自动执行 `setup_environment.py` 修复安装，缓解「网页能开、点开始训练提示无法连接训练端」。
- **侧栏版本号**：WebUI 侧栏「Next Trainer」旁显示当前版本（读取 `/api/version`），便于确认是否已升级到 2.5.3。

### 升级说明

- **v2.5.2 整合包用户请整包升级到 v2.5.3**（不要覆盖 `sd-models/`、`output/`、`config/` 等用户目录）。详见 [`docs/portable-upgrade-2.5.2-to-2.5.3.md`](docs/portable-upgrade-2.5.2-to-2.5.3.md)。

---

## v2.5.2 — 2026-05-25

### 整合包修复

- **Git 更新可靠性**：`Update-SD-Trainer.bat` 对浅克隆仓库会自动 `--deepen=50` 补齐历史，避免新版整合包更新时报 `fast-forward update failed`。
- **GitHub 网络回退**：主仓 fetch 与 `dataset-tag-editor` 子模块更新均支持直连、`ghfast.top`、`ghproxy`、`gitmirror` 多路回退，缓解国内网络 `Connection was reset`。
- **子模块容错**：整合包已内置 `dataset-tag-editor` 文件时，更新脚本会直接复用已有文件，避免 Git 因“目录已存在且非空”导致子模块 clone 失败。
- **启动脚本路径修复**：修复 `launch_portable.bat` 与 `sync_portable_root_launchers.bat` 相对路径层级错误，确保根目录 `run_gui.bat`、`run_gui_portable.bat` 能被正确刷新。
- **PyTorch 下载源测速**：首次安装依赖时改为按实际 wheel 下载吞吐量（最多 32MB / 15 秒）选择 PyTorch 源，避免直连快的用户被误切到慢速国内镜像。
- **tkinter 打包说明**：明确整合包需要完整 CPython 3.10 的 Tcl/Tk 文件，避免文件/目录选择器不可用。

### 训练稳定性

- **SDXL 训练签名兼容**：同步 `assert_extra_args` 参数签名，修复新版 `sd-scripts` 下 SDXL LoRA / Textual Inversion 训练启动时报 `TypeError`。
- **Windows torch_compile 保护**：Windows 上自动禁用 `torch_compile` / `dynamo_backend`，避免 PyTorch 编译路径依赖 Triton 导致训练中断。

### 标签编辑器

- **默认可用性恢复**：源码和整合包用户默认启用原生标签编辑器入口。
- **启动自修复**：标签编辑器缺失时会尝试自动初始化子模块；嵌入式 Python 环境下通过 bootstrap 修复 `sys.path`，避免 `/proxy/tageditor` 404。

---

## v2.5.0 — 2026-05-21

### UI 焕新

- **侧栏导航重构**：新增分组式侧栏，训练类型（LoRA / Dreambooth）、工具（Tensorboard / 数据集打标 / 标签编辑）、帮助文档等分区清晰，支持层级折叠。
- **首页传送门**：新增 Next Trainer 首页，卡片式入口快速跳转到训练、监控、新手上路等常用功能。
- **训练监控仪表盘**：新增 GPU 实时指标（型号、负载、显存、温度、功耗），总步数大字卡片，训练参数速查（学习率、优化器、调度器、Rank/Alpha、分辨率、精度）。
- **新手上路页面**：新增指南页，帮助新用户快速了解训练流程。
- **CSS 去重清理**：清理 PR 合并产生的 7 倍重复 CSS 规则（~1660 行），`sd-trainer-ui-polish.css` 和 `style.css` 均已精简。
- **README 截图更新**：替换为最新 UI 截图（WebUI 三栏布局、训练监控仪表盘、Loss 曲线 + 预览图、训练日志）。

### 改进

- **训练监控前后端分离**：`train_status_server.py` 拆分为 `train_monitor/` 目录（`server.py` + `index.html` + `monitor.css` + `monitor.js`），便于独立维护和迭代。

---

## v2.4.0 — 2026-05-21

### 训练稳定性（整合包 + 源码）

- **训练子进程环境隔离**：设置 `PYTHONNOUSERSITE=1`，防止系统用户级 site-packages（如残缺的 sklearn）污染训练子进程，修复 `No module named 'joblib'` 等 import 链断裂崩溃（[#16](https://github.com/wochenlong/lora-scripts-next/issues/16)）。
- **NaN 值过滤**：`network_args` / `optimizer_args` 中 `key=NaN` 的无效项现在被自动剥离，修复 LyCORIS `int("NaN")` 导致训练崩溃。
- **采样保护**：若最终配置无 `sample_prompts`，自动移除 `sample_at_first` 等采样参数，避免 sd-scripts 在 step 0 因 `sample_prompts=None` 崩溃。
- **attn_mode 自动降级**：配置中指定 `xformers` / `flash` 但对应后端未安装时，自动降级到可用方案（xformers → torch SDPA），并打印 WARNING 而非直接崩溃。
- **路径规范化**：配置中的模型/数据/输出等路径字段自动将 `\` 转为 `/`，修复 Windows 手动粘贴路径时反斜杠导致的兼容性问题。

### 整合包改进

- **tkinter 支持**：`build_portable.ps1` 打包时自动复制 tkinter + Tcl/Tk，修复文件夹选择器（`/pick_file`）无法弹出（[#20](https://github.com/wochenlong/lora-scripts-next/issues/20)）；缺失时 API 返回明确错误。
- **xformers 一键安装**：新增 `install_xformers.bat`，整合包用户双击即可安装 xformers 0.0.30。
- **config.json 启动修复**：空文件不再导致 JSON 解析报错。

---

## v2.3.0 — 2026-05-20

### 训练监控体验升级

- **TensorBoard 同源 Loss 曲线**：6008 训练监控页改为读取 TensorBoard event scalar，默认展示 `loss/average`、`loss/current`、`loss/epoch_average` 与 `lr/unet` 四宫格曲线，避免相对 Loss 曲线含义不清。
- **曲线交互优化**：移除小图底部滑动条，改为 `全部 / 最近 50% / 最近 20% / 最近 10% / 恢复最新` 视野按钮；保留滚轮缩放与拖拽平移。
- **训练参数速查**：监控页顶部显示学习率、优化器、总步数、分辨率、保存频率、精度、seed 等关键参数，方便启动后快速核对配置。
- **终端日志同步**：训练日志同时输出到 CMD 终端与 6008 监控页；终端 echo 失败不会影响监控页日志采集。
- **后台更干净**：静默 6008 监控页正常轮询的 `200/304` access log，只保留真实异常与训练输出。

### 启动稳定性

- **端口冲突回退**：GUI、TensorBoard 与训练监控启动前会严格检测端口；当 6008 被占用时自动切换到可用端口，并避免多个子服务 fallback 到同一个端口。
- **清理测试入口**：移除测试用 `run_gui_anima.bat`，正式包统一使用 `run_gui.bat` 启动。

---

## v2.2.0 — 2026-05-19

### 整合包与启动

- **flash-attn / triton（治本）**：便携包不再安装 `flash-attn`；启动时自动卸载已装但不可用的 `flash-attn` / `triton`；训练使用 **xformers** 或 **PyTorch SDPA**；子进程设置 `TRANSFORMERS_ATTN_IMPLEMENTATION=sdpa`，避免 `No module named 'triton'`（[#14](https://github.com/wochenlong/lora-scripts-next/issues/14) 相关）。
- **triton-windows**：便携包嵌入式 Python 不再安装/保留 `triton-windows`，修复因 triton 编译失败导致的崩溃。
- **run_gui.bat**：纯 cmd 启动（不依赖 `run_gui.ps1`，避免 PowerShell 执行策略报错）；增加 `sd-trainer-log.txt` 启动日志；失败时明确提示日志路径。
- **requirements.txt**：修复 PEP 508 环境标记在 `launch_utils` 中的解析（[#13](https://github.com/wochenlong/lora-scripts-next/issues/13)）。

### 训练监控与 UI

- **跨盘 output_dir**：监控页（6008）在输出目录位于其他盘符时不再断联（[#12](https://github.com/wochenlong/lora-scripts-next/issues/12)）。
- **品牌**：前端作者/链接改为本项目；临时 logo 与 favicon；监控页页头显示 logo。
- **CONTRIBUTORS.md**：贡献者单独文档；README 精简致谢链接。

---

## v2.1 — 2026-05-09

### 训练监控页（端口 6008）

- **Loss 趋势图**：参考 Weights & Biases 风格——16:10 比例、`preserveAspectRatio` 保持比例、网格与坐标轴刻度、100% 基线强调、曲线末端数值标注。
- **指标侧栏**：当前 / 最低（含 step 提示）/ 初始 / 累计下降 / 最近 Δ（着色）/ 趋势 pill；与曲线底部对齐，宽屏下主体仍为左侧曲线。
- **响应式**：窄屏（约 820px 以下）单列堆叠。
