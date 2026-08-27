# Issue #226 调研报告：任务页体验问题根因核实

> 调研日期：2026-08-10；现场实例：`http://10.200.0.6:28000`（spark-4ac3，musubi Krea2 真实训练中）。
> 范围：#226 全部 9 项。§1-§4、§6-§8 为代码层面核实；§5/§9 结合现场实测定位。

## 总览

| 项 | 优先级 | 结论 | 根因位置 |
| --- | --- | --- | --- |
| §1 预览图跳裸图 | P0 | 属实，无 lightbox | `TasksPage.vue:193` |
| §2 安装任务假提交中 | P0 | 属实，kind 元数据未被前端利用 | `environment.py:435` / `TasksPage.vue:87` |
| §3 三阶段扁平罗列 | P0 | 属实，stage 元数据未被前端利用 | `process.py:308-336` |
| §4 失败原因不展示 | P0 | 属实，后端已写 error/last_log_lines，前端未渲染 | `tasks.py:100-102` / `TasksPage.vue:182-186` |
| §5 Loss 图空白 | P1 | **根因：musubi 子环境缺 tensorboard，无事件文件** | 见下文专项 |
| §6 TB 无返回任务 | P1 | 属实 | `TasksPage.vue:189` |
| §7 预览串台 | P0 | 属实，前端竞态实锤（无 taskId 守卫/abort） | `TasksPage.vue:45-67,102-110` |
| §8 信息密度不足 | P1 | 属实，后端 metadata 有料前端没渲染 | `TasksPage.vue:182-186` |
| §9 监控指标条 `-` | P1 | 与 §5 同根因（进度类指标正常，LOSS 类无数据） | 见下文专项 |

---

## 一、代码层面核实（§1-§4、§6-§8）

### §1 预览图跳裸图 — 属实

`frontend/src/pages/TasksPage.vue:193`：缩略图直接 `<a :href="image.url" target="_blank">`，整页跳裸 PNG，无 lightbox/modal。

### §2 安装任务"假提交中" — 属实

- 后端：`mikazuki/engines/musubi/environment.py` 创建安装任务，`metadata={"kind": "musubi_install"}`，**kind 元数据已存在**；`start_log_only()` 直接置 RUNNING。
- 前端：`TasksPage.vue:87` `taskName()` 只认 `output_name/trainer_file/backend`，安装任务三者皆无 → 显示默认名"训练任务"；且按状态进"进行中"标签页，与训练任务无法区分。
- 修复素材现成：前端读 `metadata.kind` 打标签/分栏即可，无需后端改动。

### §3 Musubi 三阶段不好认 — 属实

- 后端：`process.py:308-336` 一次提交创建 3 个任务（`{id}-cache_latents`、`{id}-cache_text_encoder`、`{id}`），每个 stage 的 metadata 均带 `stage` 字段与 `train_task_id`；后台线程串行 execute，cache 阶段父任务长时间停在 CREATED。
- 前端：扁平罗列，未消费 `stage`/`train_task_id` 做聚合。
- 修复素材现成：按 `train_task_id` 聚合 + `stage` 步骤条即可，无需后端改动。

### §4 失败原因展示弱 — 属实

- 后端：`mikazuki/tasks.py:100-102` 失败时已写 `metadata.error` + `metadata.last_log_lines`。
- 前端：任务详情（`TasksPage.vue:182-186`）只有 taskId/config/returncode 三格，错误区块未渲染。

### §6 TB 无"返回任务" — 属实

`TasksPage.vue:189`：RouterLink 到 `/tensorboard.html`（IntegrationPage iframe 整页），无返回链接、无任务上下文。

### §7 预览串台 — 前端竞态实锤

`TasksPage.vue:45-67` 的 `loadInsights()`：

- 无 taskId 守卫、无 AbortController。`watch(selectedId)`（102-110）先清空再发请求，但**上一任务的响应若晚返回，会把旧任务的 previews/metrics 写进新任务详情**。
- 轮询（136-143）只覆盖 active 任务，"已完成任务仍在变"主要来自上述竞态；多任务同 `output_name` 时后端按前缀+mtime 过滤（`task_insights.py:146-178`）也可能互相捞到，需实测确认。

### §8 信息密度不足 — 属实

详情仅 id/config/returncode。后端 metadata 已有 `backend`、`train_type`、`created_at`（`tasks.py:53`）、`output_dir` 等，前端未渲染；elapsed/ETA 可由 `created_at` + progress 推算。

---

## 二、专项：§5 Loss 空白 / §9 监控指标条 `-`

> 结论：**不是前端问题，也不是读取端 bug——musubi 插件子环境缺 `tensorboard` 包，训练进程从未写出 TB 事件文件；读取端（主环境）无数据可读。**

### 1. 现场 API 采样

`GET /api/tasks/{train_id}/metrics`：

```json
{ "tags": {}, "progress": { "percent": 2, "step": 2, "total_steps": 92, "epoch": 1, "total_epochs": 1 } }
```

- `progress` 来自 stdout tqdm 正则（`task_insights.py:117-136`），不依赖 tensorboard → 正常。
- `tags` 来自 TB 事件解析（`task_insights.py:209 read_loss_scalars`）→ 空。

### 2. musubi 写入链路源码核实（均兼容）

- TOML 确认含 `log_with = "tensorboard"`、`logging_dir = "/home/brian/lora-scripts-next/logs"`（adapter 无条件写入，`mikazuki/engines/musubi/adapter.py`）。
- musubi `trainer_base.py:124` 每步 `accelerator.log({"loss/current", "loss/average"})`，tag 与 `task_insights.py:20` 的 `LOSS_TAGS` 匹配。
- 事件目录结构 `<logging_dir>/<ts>/network_train/` 与 `_select_run_dir` 选择逻辑兼容。
- 训练日志显示 `init_trackers` 无报错、训练正常推进（tqdm 每步有 `avr_loss`）。

### 3. 决定性证据（服务器实测）

```bash
# 全仓库今天没有任何新事件文件
find /home/brian/lora-scripts-next -name 'events.out.tfevents.*' -newermt '2026-08-10'  # 空

# musubi 子环境：有 accelerate，没有 tensorboard
extensions/musubi_tuner/.venv/bin/pip list | grep -iE 'tensorboard|accelerate'
# accelerate 1.6.0  （无 tensorboard）
```

- accelerate 对缺失的 tracker 库**不硬报错**：`init_trackers` 静默跳过，训练照常，loss 只留在 tqdm。
- 主环境 `tensorboard 2.10.1 + protobuf 3.19.6` 可正常 import `event_accumulator`，读取端无问题。

### 4. 根因

musubi-tuner 上游 `pyproject.toml` 主依赖**不含 tensorboard**（仅 dev group）；插件安装命令
`uv pip install "{source}[{cuda_extra}]"`（`mikazuki/engines/musubi/environment.py`）不带 dev 依赖
→ 子环境天然缺包 → 无事件文件 → §5/§9 空白。

### 5. 影响面与备注

- 影响所有 musubi/Krea2 任务的 Loss 展示；kohya/anima 老任务不受影响（TB 中 8 月 4 日前 run 齐全）。
- 主环境 `requirements.txt` 已于 `8ceba1b` 升 tensorboard 2.14（解决新装环境 protobuf 冲突）；本例主环境为旧 2.10.1，读取无碍。
- 顺带核实：`task_insights.py:117-136` tqdm 正则在 musubi 输出上工作正常，计划文档该待验证项可勾掉。
- 观察样本任务 `sample_at_first` 未出图（有 sample prompt TE 缓存但 previews 为空），采样预览链路待任务跑到采样点再确认。

---

## 三、修复方向（待决策，不在本报告实施）

### §5/§9

1. **插件 installer 补包**（推荐）：`mikazuki/engines/musubi/environment.py` 安装命令追加 `tensorboard`，不动上游。
2. 上游 pyproject 主依赖加 tensorboard：影响面大，不推荐。
3. 防御性改进（可选）：`read_loss_scalars` / `tensorboard_loss_scalars` 目前静默返回 `{}`，应暴露"暂无 TB 数据/读取失败原因"的降级文案，对应 §5/§9 的"明确降级"诉求。

> **修复状态（2026-08-11）**：方案 1 已实施——`environment.py` 新增 `MUSUBI_EXTRA_PIP_TARGETS = ("tensorboard",)` 并追加进 `uv pip install`；`IMPORT_PROBE` 增加 tensorboard 探测，缺包时 audit 失败（`_musubi_ready_gate` 会将环境置 broken，修复/重装即可补齐存量环境）。方案 3 未做。

### 其余各项（前端为主）

- §1 lightbox、§2 kind 标签、§3 stage 聚合、§4 错误区块、§6 TB 返回、§7 竞态守卫（AbortController + taskId 校验）、§8 详情字段扩充——后端元数据均已具备，纯前端可实现，建议按 #226 要求在 `dev` 分支独立 PR 推进。
