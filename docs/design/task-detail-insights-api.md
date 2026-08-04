# 设计计划 — 任务详情预览图 / Loss 曲线接通（正路）

> **来源**：产品反馈（关联 Issue #215)；占位块已落地（`docs/design/task-detail-preview-loss-placeholders.md`)
> **范围**：后端新增按 task 的预览图 + Loss 序列 API；前端填充既有占位块自绘。

---

## 1. 现状盘点

| 层 | 现状 |
| --- | --- |
| 训练产出 | 预览图由 sd-scripts 写入 `<output_dir>/sample/`;TensorBoard 事件写入 `logging_dir`（默认 `./logs`) |
| 独立监控页 | `train_monitor/server.py` 已有成熟实现：`newest_preview_images()`(roots = output_dir/sample、output_dir、LOG_DIR)、`tensorboard_loss_scalars()`(EventAccumulator 解析，tags = `loss/average`/`loss/current`/`loss/epoch_average`/`lr/unet`,limit 10000)、`/preview-image` 沙盒图片服务——但面向「最新任务」且跑在独立端口 |
| 主 API | 无按 task 的预览/Loss 端点；任务 metadata 含 `config_path`（绝对路径 TOML,`process.py:235-244`)，可解析出 `output_dir` / `logging_dir` / `output_name` |
| 前端 | 占位块 `.task-preview-strip` / `.task-loss-panel` 已就位；无图表库依赖（不引入新依赖，SVG 自绘） |

## 2. 后端方案（mikazuki)

### 2.1 新模块 `mikazuki/utils/task_insights.py`（纯函数，可单测）

从 `train_monitor/server.py` 移植/精简以下逻辑（不跨包 import 独立进程脚本）:

1. `resolve_task_dirs(task) -> {output_dir, logging_dir, output_name}`：读 `metadata.config_path` → `toml.load` → 取三项；缺 config_path 或文件不存在返回空。
2. `list_preview_images(output_dir, output_name, since) -> list[dict]`：扫描 `output_dir/sample`（其次 `output_dir`)，按 `output_name` 前缀 + mtime ≥ 任务创建时间过滤，解析 epoch（复用 `_parse_epoch_from_name` 思路），按时间升序返回 `{name, epoch, mtime}`。
3. `read_loss_scalars(logging_dir, output_name, since, limit=500) -> dict[str, list[{step, value}]]`：在 `logging_dir` 下匹配父目录名含 `output_name` 的 tfevents（多个取最新）,EventAccumulator 读取 4 个 tag，尾部均匀降采样到 ≤500 点/tag。tensorboard 解析失败/无文件 → 空 dict，不报错。

### 2.2 API(`mikazuki/app/api.py`，走现有 envelope)

| 端点 | 返回 |
| --- | --- |
| `GET /api/tasks/{task_id}/previews` | `{images: [{name, epoch, mtime, url}]}`;url 指向下述图片端点 |
| `GET /api/tasks/{task_id}/previews/{filename}` | FileResponse；严格沙盒：仅允许 `resolve_task_dirs` 得到的 sample 目录内的已知文件名（拒绝 `..`/绝对路径），效法 monitor `/preview-image` 与现有 `get_files` 白名单思路 |
| `GET /api/tasks/{task_id}/metrics` | `{tags: {"loss/average": [{step, value}], ...}}` |

未知 task_id → `APIResponseFail`（对齐 `/train/log/stream/{task_id}` 的 404 处理）。任务无数据 → 空列表/空 tags,**200**，由前端显示既有空态。

### 2.3 测试 `tests/test_task_insights.py`

- tmp 目录构造 sample 图片与 config TOML，验证过滤/排序/epoch 解析/沙盒拒绝；
- tfevents：若测试环境有 tensorboard，用 SummaryWriter 写真事件；否则对 `read_loss_scalars` 的解析层做 mock；
- **注意**：本机无 pytest，按 AGENTS.md 规范记录「未执行」，CI/整合环境补跑。

## 3. 前端方案

### 3.1 API client(`api/tasks.ts`)

新增类型化 client:`tasksApi.previews(taskId)`、`tasksApi.metrics(taskId)`，响应类型 `TaskPreviewImage` / `TaskMetrics`。图片 URL 直接使用后端返回的相对路径（同源）。

### 3.2 详情页填充（`TasksPage.vue`)

- 选中任务变化时拉取一次；任务 RUNNING 时并入现有 2s 轮询节奏（静默刷新，预览/Loss 可与任务列表同周期或降频到 ~5s，实现时择简）。
- **预览图横条**：`.task-preview-strip` 内有图时渲染横向滚动 `<img>` 列表（缩略图定高，点击新窗看原图）；无图保持「暂无训练预览」。
- **Loss 面板**:`.task-loss-panel` 内有数据时渲染 SVG 折线（`loss/average` 主线 + `loss/current` 细线，自绘 viewBox 折线 + 坐标极值标注 + 图例）；无数据保持「暂无 Loss」。
- 图表抽成小组件（如 `components/LossChart.vue`)，输入 `{step,value}[]`，零依赖；tooltip 等增强后置。
- i18n：复用既有 `previewTitle/lossTitle` 与空态；新增如图例/单位等少量 key（双语）。

### 3.3 明确不做

- 不替换独立监控页（`/train-monitor` 继续存在，详情块是内嵌轻量版）。
- 不引入图表库；不做 loss 多任务对比、不做 lr 曲线（占位块定位是 Loss，后续可扩展 tags)。

## 4. 实施步骤

1. 后端 `task_insights.py` + 三个端点 + 测试（pytest 本机缺，记录未执行）。
2. 前端 api client + `LossChart.vue` + `TasksPage.vue` 填充与轮询 + i18n。
3. 验证：`npm run check`；手工——运行中任务预览图/Loss 随训练增长、完成后定格、无数据任务空态不变、沙盒路径拒绝越权。
4. 提交：后端与前端源码一个 feat commit;dist 按惯例单独 `chore` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 任务详情：预览图横条实时出现训练采样图；Loss 面板显示 loss 曲线并随训练推进更新。
- 无预览/无事件文件的任务保持原空态文案，不报错。
- 图片端点无法越权读取 sample 目录外文件；未知 task_id 返回 fail。
- 独立监控页功能不受影响。
