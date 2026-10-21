<p align="center">
  <img src="frontend/src/assets/moss-kohaku-poster-16-9.svg" alt="Next Trainer KohakuMoss 专用版" width="760" />
</p>

<p align="center">
  <strong>MOSS-Image × KohakuMossTrainer 专用训练器</strong><br />
  面向 MOSS-Image Base / SFT 的本地 LyCORIS 训练工作台。
</p>

<p align="center">
  <a href="docs/getting-started.md">快速开始</a> ·
  <a href="docs/MOSS.md">训练教程</a> ·
  <a href="docs/team/kohaku-moss-portable-build.md">整合包打包方案</a> ·
  <a href="README.md">English</a>
</p>

> [!IMPORTANT]
> 这是 `KohakuMoss` 独立分支，定位为 MOSS-Image / KohakuMossTrainer 专用版本，不是 `main` 或 `dev` 的通用训练器，也不会合并回 `dev`。

## 这个版本包含什么

- **唯一主线模型**：MOSS-Image Base / SFT。
- **默认训练引擎**：KohakuMossTrainer，使用官方 `kogine` CLI。
- **LyCORIS 网络**：LoKr、LoRA、LoCon、LoHa、OFT、BOFT、GLoRA、DyLoRA、T-LoRA 等。
- **两种模型输入**：整合包下载器生成的 Comfy 单文件布局，或完整 Hugging Face 原生目录。
- **两种导出**：训练结束同时生成 LyCORIS 与 ComfyUI 权重。
- **独立环境**：Python 3.12、CUDA PyTorch、KohakuMoss、KohakuEngine 与 LyCORIS，不与其他引擎混用。

本专用版不提供 Kohya、Musubi、Anima Fast、AI Toolkit 或 DiffSynth 训练入口。需要多模型通用训练器时，请使用项目的 `main` / `dev` 分支。

## Windows 整合包

专用整合包应内置完整 KohakuMossTrainer 训练环境，但不内置约 27 GB 的 MOSS 权重。

**百度网盘下载**：[Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z](https://pan.baidu.com/s/1owF17doNHaccZhHwfoStrw?pwd=uqsh)（提取码：`uqsh`）

1. 解压整合包并双击 `启动.bat`。
2. 双击 `tools\Download-MOSS-Model.bat`，从魔搭下载训练兼容的 Base BF16 权重。
3. 把图片和同名 `.txt` 标注放入 `Next-Trainer\train\moss-image\`。
4. 打开训练页；模型和引擎默认即为 **MOSS-Image / KohakuMossTrainer**。
5. 先用 50 steps 短训验证，再开始正式训练。

完整参数、目录结构、显存档位与故障排查见 [MOSS-Image 训练教程](docs/MOSS.md)。

## 源码运行

```powershell
git clone --branch KohakuMoss https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
.\run_gui.bat
```

源码方式仍需在训练页安装独立 KohakuMossTrainer 环境；专用整合包则必须预装完整环境。

## 上游与致谢

核心训练能力来自 [KohakuBlueleaf/KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer) 与 [KohakuBlueleaf/LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS)。MOSS-Image 模型由 OpenMOSS 团队发布。

---

[训练教程](docs/MOSS.md) · [使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md)
