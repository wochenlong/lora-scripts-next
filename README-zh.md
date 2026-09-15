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
  <a href="#310-更新了什么">3.1.0 更新</a>
  ·
  <a href="docs/credits.md">开源引用</a>
  ·
  <a href="CHANGELOG.md">更新日志</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

<p align="center"><sub>产品：<strong>Next Trainer</strong> · 为兼容旧安装，整合包继续保留 <code>SD-Trainer/</code> 目录和更新脚本名称。</sub></p>

## 这是什么

**Next Trainer** 是一款面向未来与 Agent 的本地训练器：界面保持熟悉，同时按专业工作台来组织常见模型与多个训练引擎。

你可以在本机 NVIDIA 显卡上训练 Anima、SD 1.5、SDXL、Flux、FLUX.2 Klein 和 Krea 2 的 LoRA 或全量微调，也可以在同一个工作台里完成数据集打标、caption 编辑、TOML 导入、开训，以及日志、预览图和 Loss 查看。

主路径基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，并可选接入 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) 与 [AI Toolkit](https://github.com/ostris/ai-toolkit)。

---

## 分支与版本（请先读）

| 分支 | 用途 | 界面 | 版本号 |
|------|------|------|--------|
| **`main`** | 稳定发布 | Vue 3 工作台 | **`3.1.0`** |
| **`dev`** | 下一版本集成与验收 | Vue 3 工作台 | 跟随开发进度 |

反馈 Issue 时请附上侧栏或 `VERSION` 中的版本号。旧 UI 基线保留在 `legacy/v2.9.1`。

---

## 下载 Next Trainer 整合包

| 包 | 内容 | 下载 |
|----|------|------|
| **3.0.0 正式包** | lite / Kohya 分轨 | [GitHub Release v3.0.0](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) |
| **3.1.0** | 代码发布候选；整合包将在验收后发布 | [Releases](https://github.com/wochenlong/lora-scripts-next/releases) |

---

## 怎么用

### A. 整合包

1. 下载对应版本的正式包并解压到**非中文、非空格**路径
2. **lite** 用 `run_gui.bat`，满配/分轨包按包内说明（如 `启动.bat`）
3. 打开 **http://127.0.0.1:28000**  
4. 侧栏版本应与下载的 Release 一致

要求：Windows 10/11，NVIDIA GPU（建议 RTX 20+）。

补充说明：[整合包](docs/portable-getting-started.md) · [打标模型](docs/tagger-models.md) · [构建与发包](docs/portable-build-guide.md)

### B. 从源码运行

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# Windows：准备环境后启动（需本机 Python 3.10）
.\run_gui.bat
# 或：python gui.py --dev
```

开发者请看：[命令行与 TOML](docs/cli-args.md)、[仓库布局](docs/repo-layout.md) 和 [构建与发包](docs/portable-build-guide.md)。

---

## 3.1.0 更新了什么

3.1.0 的源码发布已经进入 `main`。主要更新：

- **Anima Fast** 支持 Anima 2.9B 与 T-LoRA，使用独立运行时，补充更清晰的预检、安装进度和更安全的默认值。已在 RTX 4090 上使用 `AdamW` 完成 100 步真机训练验证。
- **统一引擎**：Kohya、Anima Fast、Musubi、AI Toolkit 现在共享统一的引擎模型。
- **新增路径**：AI Toolkit / Klein、插件市场和 Pi Agent 基础能力。
- **运维增强**：任务队列、持久化、清理、重试、配置导出、日志、预览图和 Loss 隔离。
- **稳定性**：改进参数映射、TOML 步数/epoch 处理、多卡启动和 Windows 安装行为。

详情见：[完整更新日志](CHANGELOG.md) · [Anima Fast](docs/anima-fast.md) · [任务工作台](docs/issues/286-task-workbench.md)。

---

portable / AIO 整合包仍需完成最终构建、验收和发布。

---

## 界面预览

Vue 3 工作台覆盖训练、数据集、任务和训练引擎设置。更详细的使用流程见上面的文档入口。

截图来自中文界面：

#### 训练

| 标准（Kohya / Anima LoRA） | Anima Fast | Krea 2（Musubi） |
|---|---|---|
| ![训练 · 标准](assets/readme/vue3/01-training-standard.png) | ![训练 · Fast](assets/readme/vue3/02-training-fast.png) | ![训练 · Krea 2](assets/readme/vue3/08-training-krea2.png) |

#### 数据集

| 模型打标 | 标签编辑 |
|---|---|
| ![数据集 · 打标](assets/readme/vue3/03-dataset-tagger.png) | ![数据集 · 标签编辑](assets/readme/vue3/04-dataset-editor.png) |

#### 任务

![任务](assets/readme/vue3/05-tasks.png)

#### 设置

| 界面偏好 | 训练引擎 |
|---|---|
| ![设置 · 界面](assets/readme/vue3/07-settings-ui.png) | ![设置 · 训练引擎](assets/readme/vue3/06-settings-engines.png) |

---

## 支持的模型

Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2。
训练目标和显存说明：[Anima 训练](docs/anima-training.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2 多卡](docs/krea2-linux-multigpu.md)。

---

## 延伸阅读

[整合包](docs/portable-getting-started.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2](docs/krea2-linux-multigpu.md) · [TOML / CLI](docs/cli-args.md) · [构建与发包](docs/portable-build-guide.md) · [开源引用](docs/credits.md)

---

## 常见问题（简）

**反馈 Bug 要带什么？**  
完整版本号（侧栏）、训练类型（模型/引擎/目标）、复现步骤、相关日志。→ [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite 和 kohya-musubi 怎么选？**  
弱网 / 轻量入口 → lite（首次启动装依赖）。要开箱 Kohya + Musubi（可训 Krea 2）→ **kohya-musubi**（魔搭）。Anima Fast 两包都需在设置页安装。

**3.x 和旧 UI 版本能混用配置吗？**
多数 TOML 可导入；导航与存储 key 有差异，以当前页「导入配置」为准。

---

<p align="center"><sub>维护：<a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">开源引用</a> · <a href="CONTRIBUTORS.md">贡献者</a></sub></p>
