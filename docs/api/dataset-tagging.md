# 数据集打标 API（Phase 1）

> 打标页进度条与后台任务状态。完整 #40 范围见 `docs/issues/40-dataset-tagging-backend-alignment.md`。

## POST `/api/tagger/jobs` 自然语言并发参数

自然语言 Caption 批量请求支持 `concurrency`：默认 `3`，必须是 `1` 到 `16` 的整数。`0`、超上限、小数、布尔、字符串和 `null` 返回校验错误（HTTP 422）。Tag 请求不支持此参数，显式传入会返回 HTTP 400；Tag 的 ONNX 推理继续串行。

```json
{
  "path": "/data/datasets/images",
  "mode": "natural",
  "concurrency": 3,
  "max_tokens": 1024,
  "temperature": 0.7
}
```

`concurrency` 限制同一任务内并行处理的图片数，任务快照及失败重试保存该值。远程生成可以重叠，本地及本地兜底仍按共享资源上限一次执行一项；完成后的文件写回、备份与报告登记保持串行。此参数不发送给 LLM provider，不改变提示词或描述缓存指纹。`/api/tagger/jobs/preview` 接受同样的参数，但仍只预览一张图片。

## GET `/api/tagger/status`

轮询打标/下载任务状态。

**响应示例**

```json
{
  "status": "success",
  "message": null,
  "data": {
    "phase": "tagging",
    "message": "正在打标 foo.jpg (3/128)",
    "model": "wd14-convnextv2-v2",
    "download": { "current": 0, "total": 0, "filename": "" },
    "tagging": { "current": 3, "total": 128, "filename": "foo.jpg" },
    "error": null,
    "updated_at": 1710000000.0
  }
}
```

`phase`：`idle` | `downloading` | `tagging` | `cancelling` | `done` | `error`

## GET `/api/tagger/download-status`

仅返回下载相关字段（与 `status.download` 一致，便于 #40 对齐）。

## POST `/api/tagger/reset`

清空打标/下载进度状态（`phase` → `idle`）。若任务仍在进行会先请求取消。打标页「全部重置」会调用此接口。

## POST `/api/tagger/cancel`

中止当前进行中的模型下载或打标任务（协作式取消：在下载块/每张图打标前检查）。

**成功**：`status: success`，`message: 正在中止任务…` 或 `当前无运行中的任务`  
中止完成后 `GET /api/tagger/status` 的 `phase` 为 `idle`，`message` 为 `已中止`。

## POST `/api/tagger/prefetch`

后台下载所选 HF 模型文件（按 interrogator 的 `model.onnx` + 标签文件，分步更新 `download.current/total`）。

打标页「预下载」在下载进行中会变为「中止」，与「启动」共用 `POST /api/tagger/cancel`。

**请求体**

```json
{
  "interrogator_model": "wd14-convnextv2-v2",
  "download_endpoint": "默认"
}
```

`download_endpoint` 可选值：

- `默认`（官方源）
- `https://hf-mirror.com`
- `https://modelscope.cn`

**成功**：缺少资产时返回 `message: 已提交 Tag 模型下载任务`，并在 `data.already_downloaded` 返回 `false`；资产已完整存在时返回 `message: Tag 模型已下载，无需重复下载`，并返回 `data.already_downloaded: true`。已下载时不会创建后台任务，也不会进入 busy 状态。
**失败**：已有任务进行中、未知模型等返回 `status: fail`。

## 本地打标模型目录

WebUI 会优先检查本地 `tagger-models/<family>/<model-key>/`，文件齐全时不会访问 Hugging Face。默认模型目录为：

```text
tagger-models/wd14/wd14-convnextv2-v2/
  model.onnx
  selected_tags.csv
```

整合包会把默认 WD 模型放入该目录。用户也可以手动下载其它模型并放到对应的分类子目录：

- `tagger-models/wd14/<model-key>/`：WD14 / CL 系列，主要用于 tag 打标。
- `tagger-models/vlm/<model-key>/`：预留给 VLM / 自然语言描述模型。

为兼容已安装用户，旧的一层目录 `tagger-models/<model-key>/` 仍可识别。如果文件不完整，系统会继续回退到原有 `huggingface/` 缓存或在线下载流程。

用户向说明见 [`docs/tagger-models.md`](../tagger-models.md)。

## POST `/api/interrogate`

与现网兼容；提交后由后台任务更新 `tagging` 进度。若已有下载/打标任务则返回失败。

请求体字段见 `TaggerInterrogateRequest`（`mikazuki/app/models.py`）。  
其中 `download_endpoint` 同上，可用于打标前模型下载阶段选择加速源。
