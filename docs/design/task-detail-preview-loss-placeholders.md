# 设计计划 — 任务详情预留「预览图 / Loss」占位区

> **来源**：产品反馈（关联 Issue #215；用户标注：上 = 预览图，下 = 各种 loss 图表）
> **范围**：前端任务页详情主区；后端零改动，先留空状态块。

---

## 1. 需求

任务详情当前只有「任务头 + 元数据 + 日志/TB 外链 + 一句延后提示」，预览图与 Loss 曲线连占位都没有，用户不知道这些信息将来出现在哪。要求在详情主区自上而下固定为：

1. 任务头（状态 / 停止）+ 元数据 + 「查看日志」「TensorBoard」（现状保留）
2. **预览图区域**：横条占位，无数据显示「暂无训练预览」
3. **Loss 曲线区域**：更大高度占位，无数据显示「暂无 Loss」

后端未接通也要先留出这两个空状态块，避免详情页大片空白、方向不清。

## 2. 现状调研

| 位置 | 内容 |
| --- | --- |
| `frontend/src/pages/TasksPage.vue:96-112` | 详情主区：`task-detail-header` → `task-meta-grid` → `task-detail-actions`（日志/TB 外链）→ `task-deferred-note`（一句“日志与曲线内嵌视图将在下一阶段提供”) |
| `frontend/src/styles/features.css:131-141` | 详情区样式；`task-deferred-note` 已是虚线边框空态风格，可复用为占位块视觉语言 |
| `frontend/src/i18n/messages/zh-CN.ts:182-193`、`en-US.ts` 同构 | `tasks.detail.*` 文案块；无预览/Loss 相关 key |
| 前端测试 | 无 TasksPage 组件/样式断言，改动自由 |

结论：纯前端展示层改动，收敛在 `TasksPage.vue` 模板 + `features.css` + 双语文案。

## 3. 方案

### 3.1 模板结构（`TasksPage.vue` 详情区）

在 `task-detail-actions` 之后插入两个占位块，并用它们**替换**现有的 `task-deferred-note`（该提示所承诺的“曲线内嵌视图”已由结构化占位表达，保留会重复）:

```html
<section class="task-preview-strip task-placeholder">
  <header>{{ t("tasks.detail.previewTitle") }}</header>
  <p>{{ t("tasks.detail.previewEmpty") }}</p>
</section>
<section class="task-loss-panel task-placeholder">
  <header>{{ t("tasks.detail.lossTitle") }}</header>
  <p>{{ t("tasks.detail.lossEmpty") }}</p>
</section>
```

- 两个块使用稳定的独立类名（`task-preview-strip` / `task-loss-panel`)，后续接通后端时只在块内填内容，外层结构不变。
- 空态文案即占位内容，暂不区分任务状态（运行中/已完成都显示空态）。

### 3.2 样式（`features.css` 任务区）

- 公共 `.task-placeholder`：虚线边框、`surface-soft` 底色、居中空态文案——沿用 `task-deferred-note` 视觉；header 小标题 + 空态正文。
- `.task-preview-strip`：横条，`min-height` 约 120–140px。
- `.task-loss-panel`：更高，`min-height` 约 280–320px，承载将来多曲线图表。
- `margin-top` 与现有详情区间距一致（18px);≤900px 自然全宽，无需额外媒体查询。
- `task-deferred-note` 样式随模板删除一并清理。

### 3.3 i18n（双语同步新增 4 个 key)

| key | zh-CN | en-US |
| --- | --- | --- |
| `tasks.detail.previewTitle` | 训练预览图 | Training previews |
| `tasks.detail.previewEmpty` | 暂无训练预览 | No training previews yet |
| `tasks.detail.lossTitle` | Loss 曲线 | Loss curves |
| `tasks.detail.lossEmpty` | 暂无 Loss | No loss data yet |

同时删除不再使用的 `tasks.detail.logsDeferred`（双语）。

### 3.4 明确不动

- 任务列表、轮询、终止、日志/TB 外链逻辑；`api/tasks.ts` 与 store 零改动。
- 后端：`/api/tasks` 响应、日志 SSE、TensorBoard 代理均不涉及；将来接通预览/Loss 数据是独立后端议题。

## 4. 实施步骤

1. `TasksPage.vue`：插入两个占位块，移除 `task-deferred-note`。
2. `features.css`：新增 `.task-placeholder` / `.task-preview-strip` / `.task-loss-panel`，删除 `.task-deferred-note`。
3. i18n：双语新增 4 个 key，删除 `logsDeferred`。
4. 验证：`npm run check`；手工确认详情区三段式顺序、空态文案、移动端堆叠。
5. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 任务详情自上而下：任务头 + 元数据 + 外链按钮 → 预览图横条占位（「暂无训练预览」)→ Loss 曲线大占位（「暂无 Loss」)。
- 运行中与历史任务均展示空态块，详情页不再以一句提示收尾。
- ≤900px 布局正常堆叠；i18n 双语 key 保持 parity。
