# 任务洞察 API 契约（previews / metrics / outputs）

按 task_id 取训练预览图、Loss 曲线与产出文件。三个端点均在主 API 进程内（`/api` 前缀，与 WebUI 同源），
不依赖独立监控页端口。未知 task_id 一律 `404 {"detail": "Unknown task_id"}`；任务无数据返回 200 空集合。

## GET /api/tasks/{task_id}/previews

返回 `{images: [{name, epoch, mtime, url, thumb_url}], preview_enabled}`：

- 图片按时间升序；`epoch` 从文件名解析，可能缺省。
- `url` / `thumb_url` 是同源相对路径，直接可用；`thumb_url` 带 `?thumb=1` 返回 JPEG 缩略图。
- `preview_enabled`：从任务 autosave 配置推断是否开了采样（有 `sample_prompts`），配置缺失时为 `null`。

## GET /api/tasks/{task_id}/previews/{filename}

返回图片本体（FileResponse）。**沙盒**：只允许任务 sample 目录内已知文件名，`..` / 绝对路径 / 未知文件名
一律 404（`Unknown preview image`）。`?thumb=1` 时优先返回缩略图，失败回退原图。

## GET /api/tasks/{task_id}/metrics

返回 `{tags, progress}`：

- `tags`：`{"loss/average": [{step, value}], "loss/current": [...], ...}`，来自 TensorBoard 事件文件，
  尾部均匀降采样；无事件文件或解析失败时为 `{}`（不报错）。
- `progress`：从日志尾部解析的进度（`{step, total_steps, epoch, ...}`）；engine pack 可自带
  `progress.py` 覆盖默认 kohya 风格解析器。

## GET /api/tasks/{task_id}/outputs

返回 `{files: [...]}`——任务输出目录里的 safetensors 等产出清单（名称/大小/mtime），
用于验收与下载引导。

## 配套实现

- `mikazuki/utils/task_insights.py`：纯函数（`resolve_task_dirs` / `list_preview_images` /
  `read_loss_scalars` / `list_output_files`），从 `metadata.config_path` 反解 output_dir/logging_dir。
- 测试：`tests/test_task_insights.py`（tmp 目录构造图片/配置/事件文件，含沙盒越权拒绝）。
- nt.py 对应子命令：`overview`（聚合状态+最新 loss+日志尾+预览数）、`metrics`、`preview`、`outputs`。
