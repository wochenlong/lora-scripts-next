# KohakuMoss 专用版快速开始

[返回首页](../README-zh.md) · [训练教程](MOSS.md) · [English](getting-started.en.md)

> `KohakuMoss` 是 MOSS-Image 专用分支，不是 `main` / `dev` 通用版本。

## Windows 整合包

要求 Windows 10/11 64 位、NVIDIA 显卡和足够的模型存储空间。整合包应内置完整训练环境；MOSS 模型另需约 27 GB。

下载：[Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z（百度网盘）](https://pan.baidu.com/s/1owF17doNHaccZhHwfoStrw?pwd=uqsh)，提取码 `uqsh`。

1. 把 7z 解压到本地磁盘，建议保留至少 60 GB 可用空间。
2. 双击根目录 `启动.bat`，浏览器默认打开 `http://127.0.0.1:28000`。
3. 训练页应直接显示 **MOSS-Image / KohakuMossTrainer / LoRA**，引擎状态为“就绪”。
4. 双击 `tools\Download-MOSS-Model.bat`，等待魔搭模型下载和 SHA256 校验完成。
5. 把训练图片与同名 `.txt` 标注放到 `Next-Trainer\train\moss-image\`。
6. 先按 [50 steps 短训](MOSS.md#42-第一次先跑-50-steps) 验证，再增加正式训练步数。

如果首次启动要求安装 KohakuMossTrainer，说明拿到的不是完整专用整合包，应联系打包者。

## 从源码运行

源码版需要 Git、主程序 Python 环境和 NVIDIA GPU。克隆时必须指定专用分支：

```powershell
git clone --branch KohakuMoss https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
.\run_gui.bat
```

进入训练页后安装 KohakuMossTrainer。它会在 `extensions/kohaku-moss/` 创建独立 Python 3.12、venv、钉版上游源码和 LyCORIS，不会污染主程序环境。

## 模型与数据目录

```text
Next-Trainer/
├── sd-models/moss-image/
│   ├── dit.safetensors
│   ├── text_encoder.safetensors
│   ├── vae.safetensors
│   └── tokenizer/
├── train/moss-image/
│   ├── 001.png
│   └── 001.txt
└── output/
```

## 更新

整合包只允许跟踪 `KohakuMoss` 分支。不要使用通用 Release 更新器覆盖 `main` / `dev` 文件，也不要把 Kohya、Musubi 或 Anima Fast 环境复制进此包。

## 下一步

[完整训练教程](MOSS.md) · [界面导览](interface-tour.md) · [打标模型](tagger-models.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues)
