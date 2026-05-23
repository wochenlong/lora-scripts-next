# Anima 训练提示“底模不是 Stable Diffusion / Flux / Lumina 模型”

## 现象

使用 **SD-Trainer v2.3.0 或更早整合包**训练 Anima LoRA 时，即使使用官方提供或 `Download-Anima-Model.bat` 下载的 Anima 模型，启动训练仍可能失败，并提示类似：

```text
Pretrained model is not a Stable Diffusion, Flux or Lumina checkpoint
校验失败：底模不是 Stable Diffusion, Flux 或 Lumina 模型
```

终端日志通常还能看到：

```text
Can't match model type from .../anima_baseV10.safetensors
```

## 原因

这不是 Anima 模型文件下载错误。

Anima 主模型本来就不是 Stable Diffusion / Flux / Lumina checkpoint。旧版整合包的 WebUI 启动链路在进入 Anima 训练脚本前，可能先把 Anima 底模误交给普通 SD / Flux / Lumina 校验逻辑，导致官方 Anima 模型也被拦截。

## 解决办法

推荐处理方式：

1. 关闭 WebUI。
2. 下载最新 Release 整合包。
3. 保留旧整合包里的 `sd-models/`、`output/`、`logs/`，如需保留历史配置也备份 `SD-Trainer/config/autosave/`。
4. 用新版整合包替换旧版后，重新双击 `run_gui.bat` 启动。
5. 浏览器按 `Ctrl+F5` 强刷页面，再重新提交训练。

`Update-SD-Trainer.bat` 只适用于 `SD-Trainer/` 本身是 git 仓库的安装方式。**v2.5.1 起新版整合包会保留 `.git` 元数据**，可以使用该脚本原地更新；更早发布版 7z 通常不包含 `.git`，运行该脚本会出现：

```text
fatal: not a git repository (or any of the parent directories): .git
```

这种情况下不是用户操作错误，而是该旧整合包不能通过 `git pull` 原地更新，请改为下载最新 Release 整合包。

## 如何确认已修复

新版中，Anima 训练请求会按 `anima-lora` 处理，不会再用普通 SD / Flux / Lumina 底模校验拦截 Anima 模型。

训练启动后应进入 Anima 后端，终端日志会继续输出 Anima 训练相关加载信息，而不是停在 `Can't match model type from ... anima_baseV10.safetensors`。
