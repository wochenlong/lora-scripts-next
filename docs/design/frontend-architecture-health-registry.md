# 前端架构健康登记与「顺势优化」策略

> 性质：这不是重构计划。前端已接近其功能极限，**不为架构评审分数动刀**。
> 本文档只做两件事：① 登记当前健康状况与已知债务（防止继续恶化）；② 定义「顺手才修」的触发条件（feature 改动碰到该区域时才允许顺带处理）。
>
> 基线快照：2026-08-11，`dev` 分支 + `feat/issue-227`。健康分自评 7.5/10。

---

## 1. 当前健康快照

### 守住的防线（继续守，不许退）

| 防线 | 现状 | 守卫方式 |
|------|------|---------|
| 网络层单点 | `fetch` 仅在 `api/client.ts`，无硬编码后端地址 | 新增请求必须走 `api/` |
| 领域逻辑外置 | `dataset/`、`training/`、`engines/` 纯函数层带单测 | 新逻辑先进纯函数层，组件保持哑 |
| store 克制 | 仅 3 个（app/tasks/tagger），14-32 行 | 页面私有状态禁入 Pinia |
| 页面体积 | 最大 320 行（TasksPage），无 500+ 巨石 | 超过 ~400 行才考虑拆 |
| 动态 import | 所有路由页面按需加载 | 新增页面保持 |

### 已知债务登记（只登记，不主动修）

| # | 债务 | 位置 | 严重度 | 触发修复条件（碰到才修） |
|---|------|------|--------|--------------------------|
| D1 | api 层不纯：向上依赖领域层、聚合兄弟 api | `api/engines.ts`（→ engines/catalog、training/modules、animaFast、musubi）；`api/training.ts`（→ schema/adapter） | 中 | 给这两个文件加新接口时，把新接口放进纯 api 形态；不回头改存量 |
| D2 | `schema/adapter.ts` 是最大枢纽（in-degree 9） | `schema/adapter.ts` | 低 | 不改。它是成熟核心，动它风险 > 收益；只加测试 |
| D3 | 容器页直接 import 子页，无抽象边界 | DatasetPage、SettingsContainerPage、TrainingWorkbenchPage；TrainingPage 被 3 个页面嵌入 | 低 | 新增 tab/子页时沿用现状；子页 props 变更才整理 |
| D4 | components 直连 api，数据流不单向 | ModelAssetsTools、SchemaField、TaskLogPanel | 低 | 组件需要第二个数据源时才上提 |
| D5 | `/settings/engines` 路由重复注册两行 | `router.ts:28-29` | 微 | **下次碰 router.ts 时顺手删一行** |
| D6 | i18n 消息文件单文件 731 行，持续膨胀 | `i18n/messages/*.ts` | 微 | 单文件过 1200 行再按页面拆命名空间 |
| D7 | 测试环境既有失败 13 个（jsdom localStorage） | theme/prefs/i18n 测试 | 中 | 换 jsdom 版本或 CI 需要全绿时统一修；不要逐个 patch |

### 明确不做（Non-goals）

- 不拆 `schema/adapter`、不抽象页面容器层、不引入 lint 架构规则（dependency-cruiser 等）
- 不为 D1-D4 开独立重构 PR
- 不追求分层「纯度」评分；以「新代码不加深缠绕」为唯一标准

---

## 2. 新代码的守卫规则（唯一强制执行项）

1. **新功能先进纯函数层**（`src/<domain>/*.ts` + 单测），组件只渲染——#227 的 `tagFilter.ts` 是范本
2. **composables 编排响应式**，不掺网络请求；网络请求走 `api/`
3. **不复制 D1 模式**：新 api 模块只做「路径 + method + 类型」，聚合/转换逻辑去领域层
4. **不复制页面嵌套模式**：新页面组合优先 props/组件拆分，不 import 整个页面当组件用
5. 顺手修复仅限「正在改的文件 + 同区域」，禁止借机扩大 diff

---

## 3. #210（beta-tagger-ui）特别预警

新应用是最大的一次性耦合输入源，开工前对照此清单：

| 风险 | 对策 |
|------|------|
| 复用 `api/engines.ts` 的聚合模式 | 新应用 api 层独立，从 `api/client.ts` 复用 envelope 即可 |
| 复制 TrainingPage 页面嵌套模式 | 三栏壳用组件组合；复用 #227 的 `dataset/` 纯函数层 + `TagFilterPanel` 这类哑组件 |
| 共享代码放错位置 | 共享层 = `src/dataset/`、`src/composables/`、（可选）`src/components/dataset/`；以 npm workspace 引用，禁止复制粘贴 |
| i18n 单文件继续膨胀 | tagger-ui 的词条考虑独立文件起步（对照 D6 触发线） |

---

## 4. 复审节奏

- 每个大 feature（如 #210 各期）合入后，更新本文档 §1 快照与债务表
- 债务被顺手修掉时在 §1 表格标记 ✅ 并记录 PR 号
- 本文档不追求「清零」，追求「不新增」
