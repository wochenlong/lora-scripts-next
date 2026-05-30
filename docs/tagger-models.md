# 打标模型目录（tagger-models）

WebUI「数据集打标」会**优先**使用项目根目录下 `tagger-models/` 中的本地文件。若目录内文件齐全，**不会**再访问 Hugging Face 下载。

适用于：整合包用户、在线下载失败、或希望手动管理 ONNX 模型的用户。

## 目录结构

```text
<项目根或整合包根>/
  tagger-models/
    wd14/
      wd14-convnextv2-v2/          ← 默认 WD 模型
        model.onnx
        selected_tags.csv
      wd14-convnext-tagger-v3/     ← 其它 WD 模型（示例）
        model.onnx
        selected_tags.csv
    vlm/
      <model-key>/                 ← 预留：VLM / 自然语言描述模型
```

- **WD14 / CL 系列**：放在 `tagger-models/wd14/<model-key>/`
- **VLM 系列**：放在 `tagger-models/vlm/<model-key>/`
- **兼容旧布局**：`tagger-models/<model-key>/`（一层目录）仍可识别

`<model-key>` 与 WebUI 打标页下拉框中的模型 ID 一致（如 `wd14-convnextv2-v2`）。

## 默认模型

| 项 | 值 |
|---|---|
| 模型 ID | `wd14-convnextv2-v2` |
| Hugging Face | `SmilingWolf/wd-v1-4-convnextv2-tagger-v2`（revision `v2.0`） |
| 本地路径 | `tagger-models/wd14/wd14-convnextv2-v2/` |
| 必需文件 | `model.onnx`、`selected_tags.csv` |

**整合包**：新版 7z 会内置上述目录；一般无需再下载。

**源码安装**：`install-cn.ps1` 或 `python scripts/prefetch_default_tagger.py` 会尝试写入 `tagger-models/`；每次 `run_gui.bat` 启动前若缺失也会自动补全。

## 手动放置模型（下载失败时）

1. 从 Hugging Face（或镜像）下载对应模型的 `model.onnx` 与标签 CSV（通常为 `selected_tags.csv`）。
2. 在项目根（整合包为 `run_gui.bat` 同级）创建目录，例如：
   ```text
   tagger-models/wd14/wd14-convnextv2-v2/
   ```
3. 将两个文件放入该目录，**文件名需与 interrogator 要求一致**（默认 WD 为上述两个文件名）。
4. 重启 WebUI 或刷新打标页，选择对应模型后直接「启动」——不应再触发下载。

若文件不完整，程序会回退到 `huggingface/hub/` 缓存或在线下载（可在打标页选择镜像源）。

## 自定义根目录（高级）

设置环境变量 `MIKAZUKI_TAGGER_MODELS_DIR` 指向其它绝对路径，可覆盖默认的 `<项目根>/tagger-models`。

## 相关文档

- 打标 API 与进度：[docs/api/dataset-tagging.md](api/dataset-tagging.md)
- 整合包目录契约：[docs/portable-packaging-git-update.md](portable-packaging-git-update.md)
- 便携包说明：[scripts/portable/README.md](../scripts/portable/README.md)
