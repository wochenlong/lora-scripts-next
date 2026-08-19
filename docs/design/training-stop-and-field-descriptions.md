# 设计计划 — 停止训练入右栏 + 中栏说明书感

> **来源**：产品反馈（关联 Issue #215；阶段：工作台肌肉记忆）
> **范围**：训练页右栏加「停止训练」；中栏字段「key + 说明 + 控件」说明书式呈现。后端零改动。

---

## 1. 需求

1. **右栏加「停止训练」**：与「开始训练」同区（右下开/停）；默认停当前/最近一次运行中任务，无运行中任务则 disabled；任务页保留「停止任务」，两边都能停、不互相替代。
2. **中栏说明书感**：每个参数 = 字段名（key)+ 简短中文说明 + 控件；单列布局正适合放描述，不为省高度砍说明；老用户扫表即懂。

## 2. 现状调研

### 停止能力（全部为现成件）

| 位置 | 内容 |
| --- | --- |
| `stores/tasks.ts` | 已有 `runningTasks` computed、`terminate(taskId)`（内部静默刷新）、`terminatingId` |
| `api/tasks.ts` | `terminate` 为后端既有 GET mutation（不擅自改 POST) |
| `TasksPage.vue` | 停止按钮 + 确认框文案链路完整，可对照复用 |
| `features.css:35` | `.danger-action` 基础样式现成 |
| i18n | `tasks.terminate.*`（确认/成功/失败）、`tasks.detail.stopping` 均可复用；仅需新增「停止训练」入口文案 |

后端任务列表按时间正序返回（TasksPage 为展示做了 reverse),「最近一次运行中」= `runningTasks` 末尾元素。

### 中栏字段呈现

`SchemaField.vue:44-60` 当前渲染顺序已是 **label(key + 必填徽标)→ description → 控件**，方向符合；差距在可读性细节：

- `.field-description` 为 11px(`features.css:52`)，低于 AGENTS.md 正文不低于 12px 的约定；
- Schema 描述中残留的 `<br>`（如 `shared.ts` 采样参数说明）会以纯文本字面显示；该字段前端实际被 `adapter.ts:72` 的 i18n 覆盖（纯文本），全 schema 仅余个别 `<br>`，需清点并统一为纯文本；
- adapter 的 description 提取（`adapter.ts:97-99,117,130`）链路完整，无需改动。

## 3. 方案

### 3.1 右栏「停止训练」(`TrainingPage.vue`)

1. 引入 `useTasksStore`:`onMounted` 执行 `refresh()`，并以 2s `refresh({ silent: true })` 轮询（与任务页同节奏）,`onBeforeUnmount` 清理定时器。
2. `currentRunning = computed(() => store.runningTasks.at(-1))`（最近一次运行中）。
3. `submit()` 成功后 `store.refresh({ silent: true })`，使「停止训练」立即可用。
4. `stopTraining()`:ElMessageBox 确认（复用 `tasks.terminate.*`)→ `store.terminate(currentRunning.id)`；成功/失败提示复用现有 key；取消不报错。
5. 模板：提交区改为 `.submit-row` —— 「开始训练」+「停止训练」(`danger-action`)并排；停止按钮 `:disabled="!currentRunning || store.terminatingId"`。
6. 抽屉收起态 rail：在 rail 提交按钮下加同式竖排「停止训练」（小尺寸、danger)，无运行中任务 disabled；与「固定入口」原则一致。
7. 新增 i18n:`training.stop` = 停止训练 / Stop Training（双语）;`stopping` 等复用 tasks 现有 key。

### 3.2 中栏说明书感（`SchemaField.vue` / `features.css` / schema 文本）

1. 渲染结构保持不变（key → 说明 → 控件），本次只增强可读性，不改 DOM 顺序。
2. `features.css`:`.field-description` 字号 11px → 12px、行高 1.45 → 1.6，去掉为两列对齐遗留的 `min-height:30px`（单列下无对齐需求，无说明的字段不再留空白）。
3. 说明文本清点：`mikazuki/schema/*.ts` 中残余 `<br>` 改为纯文本（前端按 `{{ }}` 插值渲染，不引入 v-html，避免放开 HTML 注入面）。
4. 不砍说明：字段无 description 属后端 schema 缺失，逐字段补文案是后端 schema 议题，列入后续，不在本期硬编。

### 3.3 明确不动

- 任务页「停止任务」与列表轮询逻辑不变；两边共用同一 store 与 `terminate` 通路。
- adapter、Schema AST、校验逻辑零改动；后端 API 零改动。

## 4. 实施步骤

1. `TrainingPage.vue`：接入 tasks store 轮询 + `.submit-row` 开/停 + rail 停止按钮。
2. i18n：新增 `training.stop`（双语）。
3. `features.css`:`.submit-row` 布局、`.rail-stop`、`.field-description` 可读性调整。
4. schema 文本：清点并去除残余 `<br>`（后端 `mikazuki/schema/*.ts`，纯文案改动）。
5. 验证：`npm run check` + 仓库根 `pytest tests/test_vue_spa_routes.py` 不受影响（无路由变化）；手工：启动任务后训练页可停、无任务时 disabled、任务页停止仍正常、字段说明 12px 呈现。
6. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 训练页右下：开始训练 / 停止训练同区；有运行中任务时可停（带确认与反馈），无则 disabled；任务页停止功能不变。
- 抽屉收起态 rail 同样具备开/停固定入口。
- 中栏每个字段 = key + 中文说明 + 控件；说明 12px 易读，无 `<br>` 字面值残留，无说明字段不留多余空白。
