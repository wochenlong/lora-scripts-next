# 设计计划 — 数据集 Tab 顺序：模型打标在前

> **来源**：产品反馈（关联 Issue #215)
> **范围**：前端数据集页顶栏 Tab 顺序与默认落点；后端零改动。

---

## 1. 需求

数据集顶栏 Tab 顺序调整为 **模型打标（左/前）→ 标签编辑（右/后）**，贴合「先打标再改标」的工作流。默认落点可落到「模型打标」或保留上次 Tab，细交互可后定，但**展示顺序必须调整**。

## 2. 现状调研

| 位置 | 内容 | 影响 |
| --- | --- | --- |
| `frontend/src/pages/DatasetPage.vue:15-16` | Tab 渲染顺序：标签编辑（`/dataset/editor`）在前，模型打标（`/dataset/tagger`）在后 | **必改**：交换两个 `RouterLink` |
| `frontend/src/router.ts:22` | `/dataset` redirect → `/dataset/editor` | 默认落点决策点 |
| `frontend/src/pages/HomePage.vue:9` | 首页数据集 portal 卡片直链 `/dataset/editor` | 随落点决策同步 |
| `frontend/src/layouts/AppShell.vue:17` | 侧栏「数据集」入口指向 `/dataset`,match 列表已覆盖两个子路径 | 无需改 |
| `frontend/src/pages/GuidePage.vue:10` | 指南页分别直链两个 Tab | 无需改（直链语义不变） |
| `tests/test_vue_spa_routes.py:10-12` | 只断言 SPA fallback，不断言 redirect 目标 | 无需改 |
| i18n `dataset.tab.editor/tagger` | 文案不变，仅顺序调整 | 无新增 key |

前端无任何测试固化 Tab 顺序或 `/dataset` redirect 目标，改动自由度高。

## 3. 方案

### 3.1 展示顺序（必做）

`DatasetPage.vue` 交换两个 `RouterLink`：模型打标渲染在前（左），标签编辑在后（右）。路由路径、props、激活逻辑全部不变。

### 3.2 默认落点（推荐一次做掉）

推荐 **方案 B**:`/dataset` redirect 改为 `/dataset/tagger`，首页 portal 卡片改为指向 `/dataset`（落点逻辑单一出处）。理由：

- 贴合「先打标再改标」流程，新用户从打标开始；
- 改动极小（router 一行 + HomePage 一行），无兼容风险——旧外部链接（`/tagger.html`、`/dataset-editor.html`）均直链具体 Tab，不受影响；
- 已在「上次 Tab」记忆之前提供正确的默认定向。

备选 **方案 C**（可后续单独迭代）：记住上次 Tab——tab 切换时写 `ui-configs.dataset_last_tab`,`/dataset` redirect 用函数读取该 key 回退到 tagger。引入持久化状态与读取时机复杂度，本期不做。

### 3.3 明确不动

- 两个 Tab 页内部（`TaggerPage`、`DatasetEditorPage`）零改动；
- 路由表两条具体路由、i18n 文案、侧栏 match 列表、指南页直链均不变；
- 后端与 SPA fallback 测试不涉及。

## 4. 实施步骤

1. `DatasetPage.vue`：交换 Tab 渲染顺序。
2. `router.ts`:`/dataset` redirect → `/dataset/tagger`。
3. `HomePage.vue`：数据集 portal `to` 改为 `/dataset`。
4. 验证：`npm run check`；手工确认顶栏顺序、侧栏/首页入口落点、两个 Tab 各自直链与激活态。
5. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 数据集页顶栏顺序：模型打标（左）→ 标签编辑（右），激活态跟随路由正确。
- 从侧栏「数据集」或首页卡片进入，默认落在模型打标。
- `/dataset/editor`、`/dataset/tagger` 直链及旧 URL redirect 行为不变。
