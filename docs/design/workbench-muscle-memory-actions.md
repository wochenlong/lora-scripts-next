# 设计计划 — 工作台肌肉记忆：配置类动作收拢到右栏

> **来源**：产品反馈（关联 Issue #215；阶段：工作台肌肉记忆）
> **范围**：训练工作台按钮归位；后端零改动。

---

## 1. 需求

配置类动作（导入 / 导出 / 重置 / 保存配置 / 预设 / 历史）目前散落两处：中栏表单顶部的 `.training-toolbar` 和 `WorkbenchHeader`（保存/导入/重置）。全部收拢到**右栏 TOML 预览下方的操作区**，与「开始训练」同区，形成固定肌肉记忆位：

> 预览 → 配置动作（预设 / 保存 / 导入 / 历史 / 导出 / 重置）→ 校验 → 开始训练

同区同逻辑即可，不追求像素级按钮网格；中栏顶栏去掉重复入口，避免两处找按钮。

## 2. 现状调研

| 位置 | 内容 |
| --- | --- |
| `TrainingPage.vue` 中栏 `.training-toolbar` | 预设 / 导入(`!bare`)/ 保存(`!bare`)/ 历史 / 导出 / 重置(`!bare`) |
| `components/WorkbenchHeader.vue` | 标题 + 保存 / 导入 / 重置三个 `ghost-button`，经 `TrainingWorkbenchPage` 的 `childRef` 调 `TrainingPage` expose 的 `saveConfig/openImport/resetConfig` |
| `TrainingPage.vue:231-263` 右栏 | 诊断 → started-task → 预览面板 → 校验 → 开始训练（收起态为 rail：把手 + 提交） |
| `features.css:54` | `.training-toolbar` 样式，仅 TrainingPage 使用 |
| 路由 | `/training` 只经 `TrainingWorkbenchPage`，均以 `bare` 渲染；非 bare  standalone 已无入口 |

即工作台态下：预设/历史/导出在中栏 toolbar，保存/导入/重置在中栏顶栏 header——正是反馈说的两处分散。

## 3. 方案

### 3.1 右栏新增配置动作区（`TrainingPage.vue`)

- 在预览面板与校验按钮之间插入 `.panel-actions`，包含：预设 / 保存 / 导入 / 历史 / 导出 / 重置，handler 全部复用现有函数（`openPresets`、`saveHistory`、`openImport`、`historyOpen = true`、`exportConfig`、`resetConfig`)，逻辑零变化。
- 删除中栏 `.training-toolbar`（隐藏的文件 input 保留，位置不变）。
- 动作在 bare / 非 bare 下一致显示（不再按 `!bare` 隐藏保存/导入/重置），消除两套可见性逻辑。

### 3.2 中栏顶栏去重（`WorkbenchHeader.vue` / `TrainingWorkbenchPage.vue`)

- `WorkbenchHeader` 删除三个动作按钮与 `save/import/reset` emit，只保留标题/副标题。
- `TrainingWorkbenchPage` 移除 `@save/@import/@reset` 绑定、`callChild`、`childRef` 与 `TrainingChildActions` 接口；`TrainingPage` 的 `defineExpose` 同步删除（无调用方后）。
- AnimaFastPage 的 `form-top` 插槽同样只渲染精简后的 header，无需改它本身。

### 3.3 样式（`features.css`)

- 新增 `.panel-actions`：一行/两行小按钮网格（如 `grid-template-columns:repeat(3,1fr)` 或 flex-wrap)，复用现有 toolbar 按钮视觉（surface 底、border、hover accent);margin 与右栏节奏一致。
- 删除 `.training-toolbar` 样式块（无其他使用方）。

### 3.4 抽屉收起态

收起（rail）时配置动作随 `.panel-full` 隐藏，rail 维持「把手 + 开始训练」。配置动作属低频操作，展开后用右栏固定位置即可；如产品后续要求收起态也可达，再评估 rail 加图标位。

### 3.5 i18n / 测试

- 文案全部复用现有 key(`training.toolbar.*`、`training.actions.*`)，无新增。
- 无组件测试断言这些按钮；验证走 `npm run check` + 手工。

## 4. 实施步骤

1. `TrainingPage.vue`：右栏插入 `.panel-actions`，删除中栏 toolbar 与 `defineExpose`。
2. `WorkbenchHeader.vue`：删按钮与 emit;`TrainingWorkbenchPage.vue`：清理绑定与 childRef 管线。
3. `features.css`：新增 `.panel-actions`，删除 `.training-toolbar`。
4. 验证：`npm run check`；手工确认六个动作在右栏可用、预设/历史弹窗与导入文件选择正常、收起态 rail 不受影响、移动端堆叠正常。
5. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 右栏自上而下：预览 → 配置动作（预设/保存/导入/历史/导出/重置）→ 校验 → 开始训练。
- 中栏顶栏与表单区不再出现任何配置类按钮，全站仅此一处。
- 各动作行为与迁移前一致（弹窗、确认框、ElMessage 反馈不变）;bare 与非 bare 可见性一致。
