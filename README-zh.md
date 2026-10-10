# Next Trainer

**多引擎 AI 模型训练工作台。**

[English](README.md) · [下载](https://github.com/wochenlong/lora-scripts-next/releases) · [使用文档](#开始使用) · [更新记录](docs/dev-progress.md) · [未来规划](docs/roadmap.md)

## 是什么

Next Trainer 把数据集管理、打标、标签编辑、训练配置与任务监控放进同一个 Web 界面，面向需要本地训练或通过浏览器操作远程训练服务器的用户。

项目延续秋叶训练器的使用体验，接入 Kohya、Anima Fast、Musubi、DiffSynth、AI Toolkit 等训练引擎，目标是一个专业、可扩展的训练工作台，而不是为每个模型维护一套独立界面。

> 你正在阅读 **`dev` 开发分支**。这里的能力可能尚未进入正式整合包；日常使用请优先选择 [Release](https://github.com/wochenlong/lora-scripts-next/releases)，不要把开发分支进度等同于已发布版本。

![Qwen-Image 训练界面](assets/readme/screenshot-qwen-ui.png)

*界面示例；实际选项以所用版本及引擎为准。*

## 能做什么

| 工作环节 | 当前能力 |
| --- | --- |
| 数据集 | 创建与自动发现数据集，上传图片及 TXT、多层文件夹，冲突预检、失败重试、ZIP 导出与回收站 |
| 打标与编辑 | 本地 WD 系列打标；标签编辑提供标签 / 自由两种模式与批量操作；内置离线中文词典，可批量译出中文释义；同一数据集在管理、打标、编辑间流转 |
| 训练 | 按模型、引擎和训练目标组织参数，TOML 预览与导入导出，LoRA 或受支持模型的全量微调 |
| 任务监控 | 训练队列、任务状态、日志、Loss 与预览图；保留 TensorBoard 作为查看方式 |
| 引擎管理 | 按需管理训练环境，搜索与筛选引擎；偏好与顺序保存在服务器 |

### 模型与引擎

设置页按 **UI 设置 / 训练引擎 / API / 插件市场 / 高级设置 / 关于** 组织：接口配置与本地翻译模型集中在「设置 → API」，网络与下载源在「高级设置」，项目介绍、更新与更新日志在「关于」。

各引擎能力不同，**接入引擎不等于支持其上游的所有模型和训练模式**。

| 引擎 | 主要训练入口 | 说明 |
| --- | --- | --- |
| Kohya | SD 1.5、SDXL、Flux、Anima | 支持范围随模型而异；已接入独立环境管理 |
| Anima Fast | Anima 2B / 2.9B LoRA | 独立运行环境；两种规格有明确的底模路径入口 |
| Musubi | Krea 2 LoRA | 可选安装；Linux 多卡见专项指南 |
| DiffSynth | Qwen-Image-2.1 文生图 / 图像编辑 LoRA | 当前为单卡 BF16；Edit 使用 Batch 1 |
| AI Toolkit | SDXL、Flux.1 Dev、Klein 4B / 9B、Krea 2 RAW、Anima、Qwen-Image-2.1 LoRA | 可选安装、独立环境；Klein 支持 base / distilled，Klein 与 Qwen 提供图像编辑入口 |

AI Toolkit 可在「设置 → 训练引擎」按需安装，训练时选择对应模型与引擎。按所选模型填写本地模型目录、单文件或组件路径，并准备所需的文本编码器、VAE、配置与 tokenizer；启动前检查模型组件和数据集。图像编辑使用目标图与参考图目录，预览可分别设置提示词、尺寸、种子与参考图。

AI Toolkit 验收：Qwen-Image-2.1 文生图与图像编辑均通过 3 步真机训练、LoRA 保存及预览生成检查；不代表所有模型或长时间训练均已验收。详见[验收报告](docs/team/pr399-acceptance-2026-10-03.md)。

Anima 默认路径仅用于引导，**不代表已下载权重**。模型、数据集、GPU 显存及依赖仍需按所选引擎准备。

使用细节：[Anima](docs/anima-training.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2](docs/krea2-linux-multigpu.md) · [DiffSynth / Qwen](docs/diffsynth.md)

## 开始使用

**使用整合包：** 从 [Releases](https://github.com/wochenlong/lora-scripts-next/releases) 选择适合的包，按包内说明启动，然后打开 `http://127.0.0.1:28000`。不同包预装的环境不同，底模通常需要另行准备。

**使用开发源码：** 参考环境说明后切换到 `dev`，Windows 使用 `run_gui.bat`；已准备好 Python 环境时可运行 `python gui.py`。前端开发与构建见 [frontend/README.md](frontend/README.md)。

| 需要什么 | 去哪里 |
| --- | --- |
| 安装与整合包说明 | [快速开始](docs/portable-getting-started.md) |
| 数据集路径、上传与删除规则 | [开发版功能说明](docs/dev-progress.md#dataset-workspace) |
| 打标模型与存放位置 | [打标模型](docs/tagger-models.md) |
| 监控与命令行使用 | [训练监控](docs/train-monitor.md) · [CLI](docs/cli-args.md) |
| 开发与整合包构建 | [仓库布局](docs/repo-layout.md) · [构建指南](docs/portable-build-guide.md) |

### 用户数据

引擎偏好与排序保存在项目根目录的 `user_data/`，更换浏览器或端口后仍可使用。本分支还增加了用户预设的创建、修改、删除，以及新训练任务的参数快照和回填入口。GUI、训练监控与 TensorBoard 的启动配置集中管理，优先保留 GUI 端口。

目录结构、配置示例与实现边界见 [用户数据说明](docs/user-data.md)。旧历史不迁移，目前也并非所有浏览器设置都已迁入。

## 我们做了什么

近期已合入 `dev` 的重点：

- **数据集工作区：** 托管目录、保留层级的上传、冲突集中处理、导出、重命名与可恢复删除。
- **标签编辑与中文释义：** 标签 / 自由两种编辑模式与批量操作；内置 Danbooru 中文词典（约 33 万条，离线可用），翻译来源为词库 / 本地模型 / API。
- **设置结构：** 顺序调整为 UI 设置 → 训练引擎 → API → 插件市场 → 高级设置 → 关于，新增「API」页统一管理接口与本地翻译模型。
- **图像编辑训练：** DiffSynth / Qwen-Image-2.1 接入目标图与参考图训练流程。
- **AI Toolkit 多模型入口：** 在统一训练页配置 LoRA，提供量化、显存卸载和采样预览等模型适用选项，沿用现有任务队列、日志与 Loss 监控。
- **Anima 路径引导：** Anima 2B / 2.9B 分别记住默认与自定义路径，导入配置保留原路径。
- **引擎环境与界面：** Kohya 独立环境管理；引擎列表支持搜索筛选，偏好与顺序持久化。
- **可靠性：** 加固环境安装检查、配置边界与整合包更新流程。

详见 [开发进展与当前限制](docs/dev-progress.md)；历史版本说明见 [CHANGELOG](CHANGELOG.md) 和 [Releases](https://github.com/wochenlong/lora-scripts-next/releases)。

### 接下来做什么

| 阶段 | 方向 |
| --- | --- |
| **3.2.0** | 完善数据集、预处理、打标和标签编辑工作流，持续接入模型 |
| **3.3.0** | 完善 AI Toolkit 的模型格式支持与训练体验 |
| **后续 3.x** | 更新机制、EXE 客户端、API 打标、训练产物发布；具体版本待定 |
| **4.0.0** | Agent 正式支持从数据准备到训练、测试的完整工作流 |

以上是目标，不是完成声明或发布日期承诺。已合入部分与待完成项见 [路线图](docs/roadmap.md)。

## 参与项目

遇到问题请在 [Issues](https://github.com/wochenlong/lora-scripts-next/issues) 提供版本或提交号、模型与引擎、复现步骤和日志。分享日志前请移除令牌与私人数据。

感谢原项目与各训练引擎作者，以及所有贡献者。[开源致谢](docs/credits.md) · [NOTICE](NOTICE.md) · [贡献者](CONTRIBUTORS.md)
