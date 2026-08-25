# Next Trainer

<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
</p>

<p align="center">
  <strong>面向未来与 Agent 的本地训练器</strong><br />
  熟悉上手 · 一个训练器覆盖常见模型 · 持续更新<br />
  <sub>专业玩家与平台可用 · 未来支持 Agent 接入 · 仓库 <code>lora-scripts-next</code></sub>
</p>

<p align="center">
  <a href="README.md">English</a>
  ·
  <a href="docs/credits.md">开源引用</a>
  ·
  <a href="CHANGELOG.md">更新日志</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

---

## 这是什么

**Next Trainer** 是一款**面向未来与 Agent 的本地训练器**：  
界面仍然熟悉，解压就能上手；能力上却按专业工作台来设计——**一个训练器覆盖大部分常见模型**，并持续跟上新模型与新引擎。

对人来说，它是本地训练器：打标、开训、盯任务、换引擎，都在同一套专业 UI 里完成。Windows 与 Linux 都能用。  
对平台和 Agent 来说，目标是做成可拆开的模块：可以整包使用，也**计划**支持在自动化流程里接入训练这一环。

你仍在本机 NVIDIA 显卡上训 LoRA 或全量微调。  
底层站在成熟训练栈上：主路径基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)；训 Krea 2 时可按需接入 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner)。  
对外品牌名是 **Next Trainer**，发布包一般是 `Next-Trainer-v*.7z`。当前默认是 Vue 3 工作台 **3.0.0**，分成训练、数据集、任务、设置四块。

---

## 能做什么

一句话：从打标、改标签，到选模型开训、盯进度、看日志，尽量在同一个本地训练器里完成。

覆盖这些常见训练路线：

1. Anima LoRA  
2. Anima Fast  
3. Anima 全量微调  
4. SD 1.5、SDXL、Flux  
5. 可选的 Krea 2

也带本地打标、训练监控页，以及 TensorBoard。

### 相比其它训练器，为什么值得试

如果别的工具让你在「熟悉」和「先进」里二选一，Next Trainer 想两边都要。

1. **UI：熟悉，能一键上手**  
   路径刻意保留对 Akegarasu / SD-Trainer 用户熟悉的操作习惯（并向 Akegarasu 致谢，见 [开源引用](docs/credits.md)）。整合包解压即用；选模型、填参数、导入 TOML、开训、看预览，不用为了换壳重新学一遍。

2. **能力：专业，一个训练器训常见模型**  
   Anima、SD 1.5、SDXL、Flux，以及可选的 Krea 2，收进同一套工作台。Kohya 是基线，Anima Fast、Musubi 等引擎按需安装与切换。

3. **节奏：及时更新**  
   新模型和常用训练路径会持续跟进，而不是停在某一版脚本外壳上。个人跟整合包，开发者和平台可跟 `main` / `dev`。

4. **代码：模块化，未来支持 Agent 接入**  
   设计目标不是只能点网页。模块可拆、配置可导入导出、任务与日志可被程序读取。人可以走完整 UI；后续也会让 Agent 或平台只接入训练这一环，嵌进自己的流水线。

5. **过程：任务看得见**  
   状态、日志、预览和 Loss 收在任务页。训起来之后，盯盘不必再开一堆外部窗口。

它不是云端一键平台，也不假装替代所有专用工具。  
它要成为：面向未来与 Agent、对常见模型够全、又能持续更新的本地训练器。

---

## 有什么功能

### 训练

1. 选基础模型  
2. 选训练引擎  
3. 选训练目标  
4. 右侧看 TOML 预览  
5. 可以校验、导入导出，然后开始训练

### 数据集

1. 用 WD14 做模型打标  
2. 用标签编辑器改标签，界面以图片为主  
3. 筛选和批量操作在右侧面板

### 任务

看任务列表、状态、日志、预览图和 Loss。日常盯训练主要看这一页。

### 设置

1. 主题和界面偏好  
2. 训练引擎管理  
3. 下载源镜像  
4. 关于页和更新日志

### 各模式大概要多少显存

1. **Anima LoRA**  
   支持 LoRA、LoKr、T-LoRA。大约 12GB 起。

2. **Anima Fast**  
   可选独立运行时。建议 16GB 及以上。在设置页安装。

3. **Anima 全量**  
   完整 DiT。建议大约 24GB。

4. **SD 1.5 和 SDXL**  
   支持 LoRA 和全量微调。

5. **Flux**  
   支持 LoRA。

6. **Krea 2**  
   经 Musubi 训 LoRA。推荐直接下 **musubi** 整合包，或在 kohya/lite 包的设置页安装 Musubi。Linux 可以多卡。

更细的显存和参数说明见 [Anima 训练文档](docs/anima-training.md)。

相关文档：

1. [Anima Fast 说明](docs/anima-fast.md)  
2. [Krea 2 多卡说明](docs/krea2-linux-multigpu.md)

### 界面长什么样

下面截图来自 Vue 3，中文界面。

<details open>
<summary><strong>训练</strong></summary>

| Kohya 或 Anima 标准 | Anima Fast | Krea 2 |
|---|---|---|
| ![训练标准](assets/readme/vue3/01-training-standard.png) | ![训练 Fast](assets/readme/vue3/02-training-fast.png) | ![训练 Krea 2](assets/readme/vue3/08-training-krea2.png) |

</details>

<details>
<summary><strong>数据集</strong></summary>

| 模型打标 | 标签编辑 |
|---|---|
| ![打标](assets/readme/vue3/03-dataset-tagger.png) | ![标签编辑](assets/readme/vue3/04-dataset-editor.png) |

</details>

<details>
<summary><strong>任务</strong></summary>

![任务](assets/readme/vue3/05-tasks.png)

</details>

<details>
<summary><strong>设置</strong></summary>

| 界面偏好 | 训练引擎 |
|---|---|
| ![设置界面](assets/readme/vue3/07-settings-ui.png) | ![设置引擎](assets/readme/vue3/06-settings-engines.png) |

</details>

---

## 下载、安装与其它说明

### 下载整合包

**正式版 [v3.0.0](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0)** 已发布（Vue 3 工作台）。国内用户优先走魔搭。

| 包 | 预装 | 适合 | 大约体积 | 下载 |
|----|------|------|----------|------|
| **kohya**（默认） | Kohya（cu128） | Anima / SD / SDXL / Flux | ~2.5 GB（分两卷） | [GitHub](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) · [魔搭](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases) |
| **musubi** | Musubi | **Krea 2** LoRA | ~2.2 GB | **[魔搭](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases)**（`releases/v3.0.0/Next-Trainer-v3.0.0-musubi.7z`） |
| **lite** | 几乎无训练环境 | 自备依赖 / 源码党 | ~0.4 GB | GitHub · 魔搭 |

- Kohya 分卷：`Next-Trainer-v3.0.0-kohya.7z.001` + `.002`，**两卷放同一目录**用 7-Zip 解压。  
- 魔搭数据集：[`Next-Lab/next-trainer-releases`](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases)，路径 `releases/v3.0.0/`。  
- 训练底模与 Anima Fast **不预装**（Fast 在设置页安装）。Krea 2 步骤见 [Krea 2 上手](docs/portable-1.5-krea2-guide.md)。  
- 仍想用旧界面：下 [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)。

运行环境：

1. Windows 10 / 11，或 Linux  
2. NVIDIA 显卡，建议 RTX 20 系列及以上  
3. 整合包解压路径尽量不要带中文，也不要带空格（主要面向 Windows；Linux 更建议从源码启动）

更多说明：

1. [整合包说明](docs/portable-getting-started.md)  
2. [打标模型](docs/tagger-models.md)  
3. [构建与发包](docs/portable-build-guide.md)

### 用整合包启动

1. 解压  
2. 双击根目录 **`启动.bat`**（或 `run_gui.bat`；以包内说明为准）  
3. 浏览器打开 http://127.0.0.1:28000  
4. 侧栏版本应显示 **`v3.0.0`**

### 从源码跑 `main`

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout main
git pull

.\run_gui.bat
```

也可以用：

```powershell
python gui.py --dev
```

确认一下版本：

```powershell
git branch --show-current
Get-Content VERSION
```

前端源码在 `frontend/`，技术栈是 Vue 3 和 Vite。

```powershell
cd frontend
npm install
npm run dev
npm run build
```

`npm run dev` 需要后端已经启动。  
`npm run build` 会把产物写到 `frontend/dist`。

### 分支怎么选

1. **`main`**  
   当前默认稳定线。Vue 3 工作台，版本 **3.0.0**。

2. **`dev`**  
   继续试验新功能的地方。也是 Vue 3，可能比 `main` 更新一点。

3. **`legacy/v2.9.1`**  
   旧界面备份。需要老 UI 时再来这里。

跟着试验线：

```powershell
git fetch origin
git switch dev
git pull
```

注意：`main`、`dev`、`legacy` 的前端不一样。  
不要把未提交的 `frontend/dist` 热修混着提。  
整合包用户直接用整包版本就行，不必自己切分支。

### `main` 为什么从旧 UI 换成了 Vue 3

Vue 3 已经在 `dev` 上测过一轮，也修完关键问题。  
转正是为了统一品牌和页面结构，让稳定修复和后面的正式整合包走同一条线。

有些东西暂时没动：整合包里的目录名还是 `SD-Trainer/`，更新脚本的文件名也先保留，方便老安装继续用。

源码合进 `main`，不等于每次改动都立刻出新 7z。正式整合包看 [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) 与 [魔搭](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases)；**v3.0.0** 的 lite / kohya / musubi 已上线。

还想用旧界面：

1. 源码分支：[legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1)  
2. 转正前快照：[legacy-v2.9.1-pre-vue3](https://github.com/wochenlong/lora-scripts-next/releases/tag/legacy-v2.9.1-pre-vue3)  
3. 旧整合包：[v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)

```powershell
git fetch origin
git switch legacy/v2.9.1
```

### 文档入口

1. [开源引用与致谢 Akegarasu](docs/credits.md)  
2. [NOTICE](NOTICE.md)  
3. [整合包说明](docs/portable-getting-started.md)  
4. [构建与发包](docs/portable-build-guide.md)  
5. [打标模型](docs/tagger-models.md)  
6. [训练监控](docs/train-monitor.md)  
7. [仓库布局](docs/repo-layout.md)

### 致谢 Akegarasu

Next Trainer 感谢 **Akegarasu** 与 [Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)（SD-Trainer / 秋叶一键训练包）长期公开的本地训练 WebUI 与整合包实践。本项目在这一谱系上继续演进。完整说明见 [开源引用](docs/credits.md) 与 [NOTICE.md](NOTICE.md)。

### 常见问题

**Bug 反馈要带什么**

请尽量带上这些：

1. 侧栏里的完整版本号  
2. 你选的基础模型、引擎、训练目标  
3. 复现步骤  
4. 相关日志  

然后到 [Issues](https://github.com/wochenlong/lora-scripts-next/issues) 提交。

**lite / kohya / musubi 怎么选**

1. 网络一般，或者只想先轻量启动，选 **lite**。第一次运行会装依赖。  
2. 日常 Anima / SD / SDXL / Flux，选 **kohya**（默认）。  
3. 要训 **Krea 2**，选 **musubi**（魔搭已上；引擎也可用设置页安装）。  
4. Anima Fast 都要到设置页单独装，任何包都不预装 Fast。

**3.0.0 和旧稳定版的配置能一起用吗**

多数 TOML 还是可以导入的。  
但导航结构和本地存储的 key 有差别，最终以当前页面导入后的结果为准。

**更新后界面怎么全变了**

这是预期现象。现在的 `main` 就是 Vue 3。

还想用旧界面，可以：

1. 切到 [legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1)  
2. 或者安装 [v2.9.1 整合包](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)

---

## 更新日志

完整变更见 [CHANGELOG.md](CHANGELOG.md)。  
正式发布记录见 [Releases](https://github.com/wochenlong/lora-scripts-next/releases)。

---

<p align="center">
  <sub>
    维护 <a href="https://github.com/wochenlong">@wochenlong</a>
    ·
    <a href="docs/credits.md">开源引用</a>
    ·
    <a href="CONTRIBUTORS.md">贡献者</a>
  </sub>
</p>
