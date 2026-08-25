# Issue #286 任务工作台补齐（P0+P1）实现说明

> 分支：`feat/task-workbench-p0`
> 范围：Issue #286 的 P0（1-3）与 P1（4-7）；P2（8-11）留待后续 PR。

## 完成度总览

| # | 条目 | 状态 | 说明 |
|---|------|------|------|
| 1 | 删除/清理历史 | ✅ 完成 | 单条删除（终态任务，确认框）+「清理历史」保留最近 N 条 |
| 2 | 导入参数再训 | ✅ 完成 | 详情页「导入再训」→ 载入该任务 TOML 直达对应训练模块页 |
| 3 | 成功任务也能再动 | ✅ 完成 | FINISHED 开放「导入再训」+「重新排队」（后端本就支持） |
| 4 | 可识别任务名 | ⚠️ 部分 | output_name 优先显示（原有）；uuid 缩短为前 8 位；「自定义标题」未做 |
| 5 | 打开/复制输出目录 | ⚠️ 部分 | 「复制」已做；「打开」未做（浏览器无法打开服务器目录，远程无意义） |
| 6 | 筛选与搜索 | ✅ 完成 | 状态/训练类型下拉 + 关键字搜索（名称/ID/路径） |
| 7 | 导出/复制本任务 TOML | ✅ 完成 | 「导出 TOML」下载文件 +「复制 TOML」到剪贴板 |
| 8 | 队列优先级/插队 | ❌ 未做 | P2，留后续 PR |
| 9 | 多任务 loss/预览对比 | ❌ 未做 | P2 |
| 10 | 备注、标签、置顶 | ❌ 未做 | P2（「自定义标题」建议并入此条） |
| 11 | 维护/训练任务分区 | ❌ 未做 | P2 |

## 后端实现

### 新增 API（`mikazuki/app/api.py`）

| 端点 | 说明 |
|------|------|
| `DELETE /api/tasks/{task_id}` | 删除单个终态任务（FINISHED/FAILED/TERMINATED）；进行中/排队任务拒绝 |
| `POST /api/tasks/purge` | 批量清理终态任务，body `{"keep_last": int}`，0 表示全清；返回 `{"removed": n}` |
| `GET /api/tasks/{task_id}/config` | 读取任务 autosave TOML 返回 JSON；回注 `model_train_type`（按 backend/trainer_file 反推），附 `backend`/`train_type`/`output_name`；文件丢失时优雅报错 |

### TaskManager（`mikazuki/tasks.py`）

- `delete_task(task_id)`：仅允许终态；从任务表与 compute 队列摘除，同步 `_persist()`，并清理 log hub 缓冲。
- `purge_tasks(keep_last)`：按 `finished_at`（缺省回退 `created_at`）倒序保留最近 N 条，其余删除。
- 进行中任务不可删，worker 线程无并发风险（删除全程持 `self._cond`）。

### TrainLogHub（`mikazuki/train_log_hub.py`）

- 新增 `drop_task(task_id)`：删除任务时同步清理内存日志/事件缓冲，避免只增不减。

### 测试

- `tests/test_task_maintenance_api.py`：11 个用例覆盖删除拒绝活跃任务、purge 保留语义、purge 参数校验、config 端点 train_type 反推（standard/musubi）、配置文件丢失报错。

## 前端实现（`frontend/src/pages/TasksPage.vue` 等）

- **删除**：详情头部对终态任务显示「删除」，`ElMessageBox` 确认（明确不影响输出文件）。
- **清理历史**：recent tab 列表上方入口，弹窗选「保留最近 N 条」（0=全清）。
- **导入再训**：详情操作区按钮 → `GET /tasks/{id}/config` → 写入 `sessionStorage["mikazuki-pending-import"]` → 按 `moduleForTrainType(train_type)` 路由到对应训练模块页；复用训练页既有 pending-import 消费与 validate-import 校验/重定向链路，`TrainingPage` 零改动。
- **重新排队**：按钮条件从 FAILED/TERMINATED 扩展到全部终态（含 FINISHED）。
- **导出/复制 TOML**：详情操作区两个按钮，分别下载 `<output_name>.toml` 与复制 TOML 文本到剪贴板。
- **输出目录复制**：meta 区输出目录行内「复制」按钮。
- **任务名**：列表 uuid 缩短为前 8 位（title 悬停显全），完整 ID 仍在详情页。
- **筛选搜索**：状态（六种状态）与训练类型（从任务 metadata 动态收集）下拉 + 关键字输入，对 running/recent 两个 tab 均生效。
- **API 层**：`frontend/src/api/tasks.ts` 新增 `remove`/`purge`/`config` 及类型。
- **i18n**：zh-CN / en-US 文案同步补齐。

## 已知限制

- 导入再训载入的是 autosave 的**运行时配置**（sanitize/adapt 后），UI-only 字段不保证完全 round-trip；musubi 的 dataset TOML 为独立文件，导入走 validate-import 校验，异常配置会被拒绝或提示。
- 「自定义标题」「打开输出目录」未实现，理由见上表；建议分别并入 P2 的「备注、标签」与不做。

## 验证

- 后端：`pytest tests -q`，失败 25 个均为环境相关预置基线（tagger/anima installer/portable 等；`test_task_lanes` 两条计时敏感用例在 dev 上同样随机失败，与本改动无关），无新增失败。
- 前端：`npm run typecheck`、Vitest 56 通过、`npm run build` 通过。
