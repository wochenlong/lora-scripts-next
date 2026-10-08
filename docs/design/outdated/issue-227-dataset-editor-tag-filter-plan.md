# Issue #227 实施方案：数据集编辑器 tag 筛图与多维排序

> **执行状态（2026-08-11 更新）：已实施完成并推送，待手测验收。** 分支 `feat/issue-227`，已推送远端，PR 未开（建议手测后开 draft）。
>
> **P0 六项全部完成；P1 全部完成**（检索缩小列表、NONE、轻量排除、OR 多词检索均落地；仅「caption 写回排序扩展」按方案标注砍掉）。
>
> 提交记录：
> - `e018436` feat：P0 筛图 + AND/OR/NONE + 四维排序 + 全选闭环（含单测、i18n、样式、dist）
> - `920e9d1` feat：轻量排除 tag 输入框（与任意逻辑叠加，逗号分隔）
> - `3fcbab9` perf：图库缩略图（后端 PIL 内存缓存缩略图端点，零新依赖；scan 增加 `thumb_url`）
> - `d6d8a7b` feat：详情图点击开全屏灯箱（Esc/点击关闭；详情面板同时改用缩略图）
> - `8a29991` feat：详情预览升级 512px 缩略图（三级加载：图库 256 / 详情 512 / 灯箱全图）
> - `60df285` feat：检索框逗号/空格分隔多词 OR 缩小列表
> - `c4dfd05` docs：本方案 + #210 联合计划 + 架构健康登记
>
> 与设计文档的偏差：
> - 排序方向键只作用于主指标、平级回退恒为字母升序（更可预期）
> - 词元长度估算规则按 `tokenLength.ts` docstring 实现，UI 标注「估算值」
> - 缩略图/灯箱为方案外的性能与体验优化（用户反馈驱动），后端改动仅限 `dataset_editor.py` image 端点，无契约破坏（`thumb_url` 为新增字段）
>
> 验证：`typecheck` ✅ `lint` 0 error ✅ `tagFilter.test.ts` 17/17 ✅；缩略图函数经 stub 绕过 cv2 缺失实测通过；全量前端测试 13 个失败确认为基线既有 jsdom 环境问题；`tests/test_dataset_editor_api.py` 新增缩略图端点测试**因本机缺 cv2 未执行**，需在有完整依赖的环境（CI/整合包）跑
>
> 遗留：
> - [ ] 浏览器手测回归清单（§5）
> - [ ] 开 draft PR → 手测通过转 ready
> - [ ] （可选）caption 写回排序扩展（频率/长度），P1 可砍项，未做
> - [ ] （可选）词元长度精确计数后端接口，当前为前端估算

> 关联 Issue：[#227](https://github.com/wochenlong/lora-scripts-next/issues/227) feat(dataset-editor): 对齐秋叶 DTE——按 tag 筛图、多维排序与过滤逻辑
>
> 工作分支：`feat/issue-227`（从 `dev` 切出）
>
> 设计约束：本方案的所有抽取与组件拆分均以**可被 #210（beta-tagger-ui）直接复用**为前提——筛选/排序逻辑落在框架无关的纯函数层，面板做成独立组件，不焊死在 `DatasetEditorPage` 里。

---

## 1. 需求范围（以 Issue 拍板为准）

### P0（本 Issue 主验收）

| 项 | 说明 |
|----|------|
| 通过标签过滤图片 | 可勾选的 tag 频次列表；勾选后图库只显示含该（些）tag 的图 |
| 过滤逻辑 AND / OR | 多选 tag 时必须 |
| tag 列表多维排序 | 字母 / 频率 / 长度 / 词元长度 + 升序 / 降序 |
| 全选当前筛选结果 | 筛完 → 全选 → 批量删/加，闭环 |
| 与现有文本筛选叠加 | Caption / 文件名筛选与 tag 过滤同时生效 |
| 交互拆分 | 筛图用勾选区；加词继续用「快捷 tag」，一颗 chip 不身兼两职 |

### P1（可同 PR 或紧随）

| 项 | 说明 |
|----|------|
| 检索缩小 tag 列表 | 至少子串；前缀 / 后缀更好 |
| 过滤逻辑 NONE | 「不含所选 tag」 |
| 轻量排除 tag | 「必须不含」输入或第二组勾选，不上完整双面板 |
| caption 写回排序扩展 | 已有字母排序写回，可扩展频率/长度（次于列表排序） |

### 明确不做

页内嵌 WD 打标、移动/删除文件、Filter by Selection、批量 regex 替换、Kohya JSON 导出、Danbooru 真分类、改布局。

---

## 2. 现状与可行性

- 后端 `/api/dataset-editor/scan` 已返回：
  - `items[].tags: string[]`（每图 tag）
  - `tags: Array<{ tag, count }>`（全局频次表）
  - `categories`（现有目录分类筛选）
- 现有文本筛选：`query` 对 caption / 文件名做子串过滤（前端）。
- 现有批量编辑 / 撤销重做 API 完整，「全选筛选结果 → 批量改」无需新接口。

**结论：P0/P1 全部纯前端可闭环，零后端改动。**

唯一备选后端项：「词元长度」若验收要求精确 CLIP tokenizer 计数，再加 `/api/dataset-editor/token-count` 小接口；首版用前端估算（见 3.2），不进主路径。

---

## 3. 技术设计

### 3.1 分层结构（为 #210 复用而设计）

```
frontend/src/dataset/                     ← 领域纯函数层（无框架依赖，可单测）
├── caption.ts            # 已有：splitCaptionTags / addTagToCaption / removeTagFromCaption
├── tagFilter.ts          # 新增：筛图 + 排序 + 检索（本方案核心）
└── tokenLength.ts        # 新增：词元长度估算

frontend/src/composables/
└── useDatasetTagFilter.ts   # 新增：响应式状态 + computed 编排

frontend/src/components/dataset/
└── TagFilterPanel.vue       # 新增：筛图面板组件（只渲染，不含业务逻辑）

frontend/src/pages/DatasetEditorPage.vue   # 壳：布局 + 状态接线
```

为什么这样分：#210 的 beta-tagger-ui 三栏界面需要同一套「筛图 + 排序」能力，且其「打标范围 = 当前筛选」直接依赖过滤结果。纯函数层 + composable + 哑组件的组合，可以让 #210 以 npm workspace 方式原样复用，一行不改。

### 3.2 `tagFilter.ts` 领域层设计

```typescript
export type FilterLogic = "and" | "or" | "none"          // none 为 P1
export type TagSortBy = "alphabetical" | "frequency" | "length" | "tokenLength"
export type SortOrder = "asc" | "desc"

export interface TagFilterState {
  selectedTags: ReadonlySet<string>
  logic: FilterLogic
  search: string        // P1：缩小下方可勾选列表
  sortBy: TagSortBy
  order: SortOrder
}

/** 图库过滤：空选择直通；and=每图含全部所选；or=含任一；none=不含任何所选 */
export function filterItemsByTags<T extends { tags: string[] }>(
  items: T[],
  state: TagFilterState,
): T[]

/** tag 列表排序：frequency 按 count，length 按字符数，tokenLength 按估算词元数 */
export function sortTagList(
  tags: Array<{ tag: string; count: number }>,
  sortBy: TagSortBy,
  order: SortOrder,
): Array<{ tag: string; count: number }>

/** P1：检索缩小可勾选列表（子串起步，可配 prefix/suffix 模式） */
export function searchTagList(
  tags: Array<{ tag: string; count: number }>,
  search: string,
  mode?: "substring" | "prefix" | "suffix",
): Array<{ tag: string; count: number }>
```

**词元长度估算规则**（`tokenLength.ts`）：按 CLIP 习惯近似 —— 逗号/空格分词后按词计数，单词超长（>15 字符）按 `ceil(字符数 / 6)` 加算。规则写进代码 docstring 与 UI tooltip（标注「估算值」）。秋叶 DTE 的 token length 同样是估算口径，不要求逐 tokenizer 对齐。

**排序细节**：

- `alphabetical`：小写归一后按字典序（与秋叶一致，大小写不敏感）；
- `frequency`：按 `count`，同频回退字母序（保证稳定）；
- `length` / `tokenLength`：同值回退字母序；
- 所有排序先复制数组，不原地改。

### 3.3 `useDatasetTagFilter.ts` composable

```typescript
export function useDatasetTagFilter(
  items: Ref<DatasetItem[]>,
  globalTags: Ref<Array<{ tag: string; count: number }>>,
) {
  const state = reactive<TagFilterState>({ selectedTags: new Set(), logic: "and",
                                          search: "", sortBy: "frequency", order: "desc" })

  const filteredItems   = computed(() => filterItemsByTags(items.value, state))
  const visibleTagList  = computed(() =>                       // 排序 → 检索 两级加工
    searchTagList(sortTagList(globalTags.value, state.sortBy, state.order), state.search))
  const hasActiveFilter = computed(() => state.selectedTags.size > 0)

  function toggleTag(tag: string) { /* 勾选/取消 */ }
  function clearTags() { /* 清空勾选 */ }
  return { state, filteredItems, visibleTagList, hasActiveFilter, toggleTag, clearTags }
}
```

注意：`state.selectedTags` 用 `Set`，toggle 时整体替换新 Set 以保证响应式。

### 3.4 页面接线与数据流

```
scan → items + tags（全局频次）
           │
筛选管线（从左到右依次叠加，全部为交集）：
  items
   → category 筛选（现有）
   → query 文本筛选（现有：caption / 文件名子串）
   → tag 筛选（新增：filterItemsByTags）
   = displayItems → 分页（现有）→ 图库

「全选筛选结果」：selectedPaths = new Set(displayItems 全量 relative_path)
   → 走现有 batch API，无改动
```

**叠加优先级写清**（验收要求）：三个筛选是**交集（AND）关系**，无先后优先级差异；文本筛选针对 caption/文件名文本，tag 筛选针对解析后的 tag 集合，二者正交、互不干扰。

### 3.5 UI 设计（左栏新增区域，布局不变）

```
左栏
├── 路径 / 扫描                （现有）
├── 分类                       （现有）
├── Caption / 文件名筛选        （现有）
├── ┌─ 按 tag 筛图 ──────────┐  【新增 TagFilterPanel】
│   │ [检索 tag…          ]   │  ← P1，子串缩小列表
│   │ 排序[频率▾] [降序▾]     │  ← 字母/频率/长度/词元长度 × 升/降
│   │ 逻辑 (•)AND ( )OR       │  ← P1 再加 NONE
│   │ ☑ bplay          (128)  │
│   │ ☐ 1girl          (312)  │  ← checkbox + tag + 频次，滚动列表
│   │ ☐ masterpiece     (96)  │
│   │ [清空勾选] [全选筛选结果] │
│   └────────────────────────┘
├── 批量编辑                   （现有）
└── 快捷 tag                   （现有，保持「追加到当前图」语义不变）
```

交互要点：

- 勾选即时生效（无「应用」按钮），图库与计数同步刷新；
- 「全选筛选结果」按钮文案带数量：`全选筛选结果 (n)`，n=0 时禁用；
- 面板头部显示 `已选 k 个 tag`，提供「清空勾选」；
- 快捷 tag 区域标题不变，tooltip 注明「用于加词，不参与筛图」（消除歧义，验收项）。

### 3.6 i18n

新增词条（中/英，key 前缀 `dataset.tagFilter.`）：

```
title / searchPlaceholder / sortBy.{alphabetical,frequency,length,tokenLength}
order.{asc,desc} / logic.{and,or,none} / clear / selectAllFiltered
selectedCount(k) / tokenLengthEstimated（tooltip：词元长度为估算值）
quickTagHint（快捷 tag 区域提示）
```

---

## 4. 实施步骤（2 个 PR）

### PR-1：P0 主路径

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 领域层 `tagFilter.ts` + `tokenLength.ts` | 纯函数 + Vitest 单测（and/or、空选择直通、四种排序、同值回退、升降序、不可变输入） |
| 2 | `useDatasetTagFilter` composable | 状态管理 + computed 管线 |
| 3 | `TagFilterPanel.vue` | checkbox 列表、AND/OR、四维排序、清空 |
| 4 | 页面接线 | displayItems 管线接入图库与分页；「全选筛选结果」接现有 batch |
| 5 | i18n 词条 | 中/英 |
| 6 | 手测 | P0 验收 5 条 + 回归 5 条（见 §5） |

### PR-2：P1 增强（紧随，可独立评审）

| 步骤 | 内容 |
|------|------|
| 7 | 检索框缩小 tag 列表（子串；前缀/后缀下拉切换）+ 单测 |
| 8 | NONE 逻辑 / 轻量排除 tag（取实现成本低者：复用同一勾选区 + 逻辑切 NONE） |
| 9 | caption 写回排序扩展（频率/长度，时间紧可砍，不挡验收） |

---

## 5. 验收清单

### P0（对照 Issue）

- [ ] 勾选 tag（如 `bplay`）后图库只显示含该 tag 的图；AND / OR 多选符合预期
- [ ] 一键选中当前筛选结果，再批量删/加 tag（全链路跑通：筛选 → 全选 → 批量删除该 tag → 图库刷新）
- [ ] tag 列表可按频率 / 字母 / 长度 / 词元长度及升降序排列
- [ ] 快捷 tag 仍用于加词；筛图走独立勾选区，无歧义
- [ ] 文本筛选 + tag 过滤 + 分类筛选叠加生效（交集语义已在 UI/文档写明）
- [ ] 不破坏现有批量编辑、撤销/重做、单张 pill；布局保持现网风格

### P1（若本 PR 含则勾）

- [ ] 检索可缩小可勾选 tag 列表（至少子串）
- [ ] NONE 或轻量「排除 tag」可用

### 回归手测清单

- [ ] 扫描目录 / 切换分类 / 文本筛选 单独使用与叠加使用
- [ ] 单张 caption 编辑保存、撤销、重做
- [ ] 批量 追加（前/后）/ 删除 / 替换 / 清理 / 字母排序写回
- [ ] 快捷 tag 点击追加到当前图
- [ ] 分页在筛选结果变化后正确重置
- [ ] 图库多选（shift 连选）在筛选后行为正确

---

## 6. 风险与对策

| 风险 | 等级 | 对策 |
|------|------|------|
| 词元长度口径与秋叶不一致 | 低 | 双方都是估算；tooltip 标注「估算值」；精确接口留作备选 |
| 大数据集过滤性能 | 低 | 千级图 O(n·m) 无压力；万级再防抖/虚拟滚动，不预优化 |
| `DatasetEditorPage` 拆分引入回归 | 中 | 拆分与功能同 PR 分 commit；§5 回归清单逐项过 |
| 状态与现有 `query`/分页耦合出错 | 中 | 筛选管线统一收进一个 computed 链，分页 watch displayItems 重置 |
| #210 复用时发现抽象不合适 | 低 | 纯函数层无框架依赖是最低风险形态；composable 可整组替换 |

---

## 7. 工作量粗估

| 项 | 估时 |
|----|------|
| 领域层 + 单测 | 0.5d |
| composable + 面板组件 | 1d |
| 页面接线 + 全选闭环 + i18n | 0.5d |
| P0 手测与回归 | 0.5d |
| P1（检索 + NONE） | 0.5d |
| **合计** | **约 3d** |
