# 设计计划 — TOML 预览面板向右抽屉式收起

> **来源**：产品反馈（关联 Issue #215 已定的 TOML 预览原则）
> **范围**：前端训练页右侧控制面板；后端与 Schema 零改动。

---

## 1. 需求

当前「收起」只是在右栏内把 `<pre>` 向上折叠（`v-show`)，右栏宽度不变、表单区不变宽，收起收益很小。期望改为**抽屉式向右边缘收起**:

1. 收起后右侧预览面板横向收进右边缘，主表单区变宽。
2. 右边缘保留窄把手 / 「预览」入口，点击再展开。
3. 「开始训练」在收起态仍保留固定入口，不随面板消失。

## 2. 现状调研

**唯一实现点**：`frontend/src/pages/TrainingPage.vue`(AnimaFastPage 只是它的包装，无独立预览面板），改动收敛在一个页面组件 + 两个 CSS 文件。

| 现状 | 位置 |
| --- | --- |
| `previewCollapsed = ref(false)`，仅控制 `<pre v-show>` | `TrainingPage.vue:32,235` |
| 右栏 `.control-panel`:sticky aside，内含 diagnostics、`started-task`、`.preview-panel`、校验按钮、`train-submit` 提交按钮 | `TrainingPage.vue:231-238` |
| 双栏布局 `.training-layout`:`grid-template-columns: minmax(0,1fr) clamp(340px,32%,460px)` | `styles/layout.css:5` |
| bare 模式（workbench 内嵌）:aside `position:sticky; top:20px; max-height:calc(100vh - 40px)` | `styles/features.css:178-182` |
| 移动端 ≤900px：单列，控制面板移到表单下方 | `styles/layout.css:8` |

**关键约束**:

- 右栏不只有预览：diagnostics（校验错误/警告）、`started-task`（任务启动后的日志入口）、校验按钮都在同一 aside 里。整栏收起时这些内容随之隐藏，需要补偿设计（见 3.3)。
- `submit()` 内部先调 `validate()`(`TrainingPage.vue:176`)，所以收起态隐藏「校验当前参数」按钮不丢功能。
- 移动端没有「右边缘」概念，抽屉语义只适用于桌面宽屏。

## 3. 方案

### 3.1 布局机制

在 `.training-layout` 根上加状态类 `preview-docked`:

```css
.training-layout{transition:grid-template-columns .25s ease}
.training-layout.preview-docked{grid-template-columns:minmax(0,1fr) 56px}
```

- 展开→收起：第二列由 `clamp(340px,32%,460px)` 动画到 `56px` 窄 rail，表单区自然变宽。
- `grid-template-columns` 过渡在 Chrome 107+ / Firefox 66+ / Safari 16+ 可动画；老浏览器瞬时切换，可接受的降级。
- bare 模式同样生效（同一 grid 容器）。

### 3.2 窄 rail 内容

收起态 aside 渲染为竖向 rail，自上而下：

1. **预览把手**：竖排文字（`writing-mode: vertical-rl`）显示 `training.preview.panelTitle`(“TOML 参数预览”)+ 参数计数 badge，点击展开；整根 rail 均可点击。
2. **诊断警示**：`diagnostics.errors/warnings` 非空时把手上显示红点/计数，提示有不可见诊断，引导展开查看（否则提交按钮 disabled 却看不到原因）。
3. **开始训练固定入口**:rail 底部固定竖排提交按钮，复用 `submit` 与现有 disabled 逻辑（`!schema || submitting || errors.length > 0`)，文案沿用 `training.start` / `training.submitting`。

展开态保持现有内容与顺序不变（diagnostics、started-task、预览面板、校验、提交）。

### 3.3 状态与边界

- `previewCollapsed` 语义不变（false=展开），模板由「隐藏 `<pre>`」改为「根容器加 docked 类 + aside 切换 rail/完整两种渲染」。
- **收起态隐藏**：diagnostics 详情、`started-task`、复制按钮、校验按钮。其中 `started-task` 含日志入口——任务运行中收起时用户可从任务页进入，可接受；把手红点仅对应 diagnostics。
- **移动端 ≤900px**：不启用抽屉，维持现有竖向折叠（media query 内 docked 类不生效，rail 不渲染）。
- **持久化**：收起状态写入 `ui-configs`（沿用现有设置 key)，刷新后保持。列为可选项，默认记忆。

### 3.4 i18n

- 复用现有 key:`preview.panelTitle`、`preview.count`、`preview.expand/collapse`、`start`、`submitting`，无需新增。
- 若把手需要更短文案（如仅“预览”)，新增 `training.preview.railLabel`，双语同步。

## 4. 实施步骤

1. `TrainingPage.vue`：根容器绑定 `preview-docked` 类；aside 内按 `previewCollapsed` 二分渲染 rail / 完整面板；rail 把手点击展开；rail 底部提交按钮复用 `submit`。
2. `styles/layout.css`:`.training-layout` 过渡与 `.preview-docked` 列宽；移动端 media query 中明确 docked 不生效。
3. `styles/features.css`:`.preview-rail`、竖排把手、badge、rail 提交按钮样式；bare 模式微调。沿用现有 token，不引入新设计系统。
4. （可选）`ui-configs` 持久化收起状态。
5. i18n：仅当采用 `railLabel` 时双语新增。
6. 验证：`npm run check`；手工桌面（展开/收起动画、表单变宽、rail 提交、errors 红点）与 ≤900px 移动布局检查。
7. dist 产物按仓库惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 桌面端点「收起」：预览面板向右动画收进边缘，表单区变宽；右缘保留可点击的「预览」把手。
- 收起态「开始训练」固定在 rail 底部，可正常提交（含 disabled 与 submitting 态）。
- 有校验错误时收起，把手出现警示标记；展开后诊断内容完整。
- 再点把手展开，面板恢复原宽与全部内容。
- ≤900px 布局行为与现状一致（无抽屉）。
