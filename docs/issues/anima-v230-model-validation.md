# v2.3.0 及更早整合包中 Anima 官方模型被误判为非 SD/Flux/Lumina 模型

## 问题描述

用户使用 `SD-Trainer v2.3.0` 整合包训练 Anima LoRA 时，即使底模来自官方下载或整合包内 `Download-Anima-Model.bat`，点击「开始训练」后仍可能失败。

WebUI 报错：

```text
训练任务提交失败：Pretrained model is not a Stable Diffusion, Flux or Lumina checkpoint / 校验失败：底模不是 Stable Diffusion, Flux 或 Lumina 模型
```

终端日志：

```text
Can't match model type from .../anima_baseV10.safetensors
```

## 影响范围

- 已确认：`SD-Trainer v2.3.0` 整合包
- 可能影响：`v2.3.0` 及更早版本
- 不影响：更新到包含修复的新版本后，Anima 训练请求会按 `anima-lora` 处理

## 根因

Anima 主模型本来就不是 Stable Diffusion / Flux / Lumina checkpoint。

旧版整合包的 WebUI 请求在进入 Anima 训练脚本之前，可能缺失或未正确携带隐藏字段 `model_train_type = "anima-lora"`，后端因此 fallback 到普通 `sd-lora` 流程，并调用普通底模校验逻辑，导致 Anima 官方模型被误判。

## 解决办法

用户侧：

1. 关闭 WebUI。
2. 下载最新 Release 整合包。
3. 保留旧整合包中的 `sd-models/`、`output/`、`logs/`，如需保留历史配置也备份 `SD-Trainer/config/autosave/`。
4. 用新版整合包替换旧版后重新运行 `run_gui.bat`。
5. 浏览器按 `Ctrl+F5` 强刷页面后重试训练。

注意：v2.5.1 起新版整合包会保留 `.git` 元数据，可使用 `Update-SD-Trainer.bat` 原地更新；更早发布版 7z 通常不包含 `.git`。如果运行时出现 `fatal: not a git repository`，请直接下载最新整合包替换旧版。

维护侧：

- 已增加后端兜底：缺少 `model_train_type` 但请求包含 Anima 专用字段（如 `qwen3`、`llm_adapter_path`、`t5_tokenizer_path`、`networks.lora_anima`）时，自动推断为 `anima-lora`。
- 已调整错误文案，避免在当前无 Lumina 前端入口的情况下继续提示 “Flux or Lumina”。
- FAQ：[`docs/troubleshooting/anima-v230-model-validation.md`](../troubleshooting/anima-v230-model-validation.md)

## 建议

在 `v2.3.0` 及更早 GitHub Release 顶部追加旧版提醒：

```md
> ⚠️ 不推荐下载此旧版本
>
> v2.3.0 及更早版本存在 Anima 训练入口的模型校验问题：官方 Anima 底模可能会被误判为“不属于 Stable Diffusion / Flux / Lumina 模型”，导致无法从 WebUI 启动训练。
>
> 请下载最新版本整合包后再使用。v2.5.1 起新版整合包保留 `.git` 元数据，可使用 `Update-SD-Trainer.bat` 原地更新；更早 7z 通常需要下载新版替换。
```
