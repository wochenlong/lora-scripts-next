# Issue #227 + #210 实施计划：先改标签编辑器，再做独立打标工具

> 关联 Issue：
> - [#227](https://github.com/wochenlong/lora-scripts-next/issues/227) feat(dataset-editor): 对齐秋叶 DTE——按 tag 筛图、多维排序与过滤逻辑
> - [#210](https://github.com/wochenlong/lora-scripts-next/issues/210) [beta-tagger-ui] 独立打标+编辑工具（需求定稿 / 首版七条路径）
>
> 工作分支：`feat/issue-227`（从 `dev` 切出）。#210 开工前等维护者下达实现指令。

---

## 0. 总体策略

两个 Issue 都落在「数据集编辑」这个领域上：

- **#227** 给现网 `DatasetEditorPage` 加 tag 筛图 / 多维排序，范围清晰、纯前端可闭环；
- **#210** 要新建独立应用 `beta-tagger-ui/`，其「图库 / 清理 / 批量编辑」基线**就是对齐现网 dataset-editor**。

如果 #227 把筛选/排序逻辑直接写死在页面组件里，#210 就得重写一遍。因此总体顺序定为：

```
阶段 0  数据集领域层抽取（为两边共用打地基）
阶段 1  #227 标签编辑器改造（P0 → P1）
阶段 2  #210 beta-tagger-ui（按 Issue 五期推进，复用阶段 0/1 成果）
```

原则：

1. **#227 先行**，作为共享 composable 的试点，边做边把领域层抽干净；
2. **#210 不提前写代码**（Issue 明确「开 Issue ≠ 马上开工」），本计划只做技术预研与方案设计；
3. 每个阶段独立可 PR、可验收，不憋大招。

---

## 1. 现状盘点

### 1.1 前端

| 资产 | 位置 | 说明 |
|------|------|------|
| 数据集编辑器页面 | `frontend/src/pages/DatasetEditorPage.vue` | 三栏布局巨石组件，20+ 个 ref 状态 |
| caption 领域函数 | `frontend/src/dataset/caption.ts` | `splitCaptionTags` / `addTagToCaption` / `removeTagFromCaption`，纯函数，可直接复用 |
| API 层 | `frontend/src/api/dataset.ts` | scan 已返回**每图 tags** + **全局 tag 频次表** + categories |
| 打标页 | `frontend/src/pages/TaggerPage.vue` + `stores/tagger.ts` | 仅「追加触发词」式打标，#210 明确不作行为基线 |

### 1.2 后端

| 资产 | 位置 | 说明 |
|------|------|------|
| 数据集编辑 API | `mikazuki/dataset_editor.py` | scan / caption 保存 / batch / undo / redo / history；**不递归扫描** |
| 打标引擎框架 | `mikazuki/tagger/interrogators/` | `Interrogator` 基类 + WD14（含 eva02-large-v3）+ CL Tagger |
| 任务进度/取消 | `mikazuki/tagger/progress.py` | 协程式取消 + 进度上报模式 |
| 模型资产管理 | `mikazuki/tagger/local_models.py` | 本地 `tagger-models/` 目录优先、HF 缓存兜底 |

### 1.3 缺口速览

| 能力 | 现网 | #227 需要 | #210 需要 |
|------|------|-----------|-----------|
| tag 勾选筛图 | 无 | **P0** | 打标范围依赖 |
| AND/OR/NONE 过滤逻辑 | 无 | **P0**（P1 加 NONE） | 同 |
| tag 列表多维排序 | 无 | **P0** | 同 |
| 递归扫描 | 无 | 不需要 | **期 1** |
| 冲突策略（跳过/覆盖/末尾追加） | 无（现网插前面） | 不需要 | **期 2** |
| NL caption 模式 | 无 | 不需要 | **期 3** |
| PixAI / JoyCaption / Qwen / 云 API | 无 | 不需要 | **期 2/3/4** |

---

## 2. 阶段 0：数据集领域层抽取

**目标**：把「数据集编辑」的领域逻辑从页面/ API 里剥离，形成前后端各自的共享层，供 #227 和 #210 共同使用。

### 2.1 前端共享层

```
frontend/src/dataset/
├── caption.ts          # 已有：caption 拆分/加词/删词（纯函数）
├── tagFilter.ts        # 新增：tag 筛图 + 排序 + 过滤逻辑（纯函数，可单测）
└── tokenLength.ts      # 新增：词元长度估算（纯函数）
```

`tagFilter.ts` 核心设计（纯函数、与框架无关）：

```typescript
export type FilterLogic = "and" | "or" | "none"
export type TagSortBy = "alphabetical" | "frequency" | "length" | "tokenLength"
export type SortOrder = "asc" | "desc"

export interface TagFilterState {
  selectedTags: ReadonlySet<string>
  logic: FilterLogic
  search: string          // P1：缩小 tag 列表
  sortBy: TagSortBy
  order: SortOrder
}

// 图库过滤：与文本筛选叠加（交集，文本筛选先行）
export function filterItemsByTags<T extends { tags: string[] }>(
  items: T[], state: TagFilterState
): T[]

// tag 列表排序（词元长度用 tokenLength.ts 估算）
export function sortTagList(
  tags: Array<{ tag: string; count: number }>, state: TagFilterState
): Array<{ tag: string; count: number }>

// P1：检索缩小可勾选 tag 列表（子串起步，前缀/后缀可配）
export function searchTagList(tags: string[], search: string): string[]
```

词元长度估算规则（前端近似，避免新增后端接口）：按 `,` 分词后，CLIP 风格近似 `ceil(字符数 / 4)` 或直接按词数计，**规则写入文档并在 UI tooltip 注明「估算值」**；若验收要求精确 tokenizer 计数，再开后端 `/api/dataset-editor/token-count` 小接口（备选，不进首版）。

### 2.2 后端共享层（为 #210 预备，阶段 0 只做轻量剥离）

把 `mikazuki/dataset_editor.py` 中的纯领域逻辑抽成 `mikazuki/dataset/` 包：

```
mikazuki/dataset/
├── __init__.py
├── scanning.py     # 从 scan 抽出的文件枚举（预留 recursive 参数，默认 False 不改行为）
├── captions.py     # caption_path_for / read_caption / write_caption / parse_tags / format_tags
└── undo.py         # EditTransaction / undo-redo 栈（进程内字典实现原样搬入）
```

`mikazuki/dataset_editor.py` 改为薄 API 层，import 上述模块。**行为零变化**，由现有手测路径回归（scan → batch → undo → redo）。

### 2.3 阶段 0 验收

- [ ] `tagFilter.ts` / `tokenLength.ts` 有单元测试（Vitest，覆盖 and/or/none、四种排序、升降序、空选择直通）
- [ ] 后端 `mikazuki/dataset/` 抽取后，现有编辑页全部功能手测回归通过
- [ ] 无行为变化、无 API 契约变化

---

## 3. 阶段 1：#227 标签编辑器改造

**分支**：`feat/issue-227`。**布局保持现网三栏**，功能按 P0 → P1 分层。

### 3.1 UI 结构（左栏新增「按 tag 筛图」区）

```
左栏
├── 路径 / 扫描            （现有）
├── Caption / 文件名筛选   （现有文本筛选）
├── 【新增】按 tag 筛图
│     ├── 检索框（P1，缩小下方列表）
│     ├── 排序：字母/频率/长度/词元长度 + 升降序
│     ├── 逻辑：AND / OR（P1 加 NONE）
│     ├── tag checkbox 列表（tag + 频次）
│     └── 「全选筛选结果」按钮
├── 批量编辑               （现有）
└── 快捷 tag               （现有，保持「加词」语义不变）
```

**交互拆分原则**（#227 硬性要求）：筛图 checkbox 与快捷 tag 是**两个独立区域**，一颗 chip 不身兼两职。

### 3.2 组件拆分

`DatasetEditorPage.vue` 已 20+ ref，本次顺势拆出：

```
frontend/src/pages/DatasetEditorPage.vue       # 壳：布局 + 状态编排
frontend/src/components/dataset/
├── TagFilterPanel.vue    # 新增：筛图面板（props: tags；emits: 状态变更）
└── （后续可继续拆 BatchEditPanel / QuickTagPanel，不在本 Issue 强制）

frontend/src/composables/
└── useDatasetTagFilter.ts   # 新增：持有 TagFilterState，输出 filteredItems / sortedTagList
```

composable 内部全部委托阶段 0 的 `tagFilter.ts` 纯函数，组件只做渲染。

### 3.3 状态与数据流

```
scan → items（每图 tags）+ tags（全局频次）
              │
              ├─ 文本筛选（现有 query，子串，先行）
              ├─ tagFilter.selectedTags + logic（交集叠加）
              │        └─ filteredItems（computed）
              ├─ category 筛选（现有，继续叠加）
              └─ 分页（现有，对最终结果分页）

「全选筛选结果」→ selectedPaths = filteredItems 全量 relative_path
              → 接现有批量删/加 API（无改动）
```

排序只影响**左栏 tag 列表显示顺序**，不影响图库顺序；图库顺序维持现状（若用户提出再议）。

### 3.4 任务分解（建议 2 个 PR）

**PR-1（P0 主路径）**

1. 阶段 0 前端共享层 + 单测
2. `useDatasetTagFilter` composable
3. `TagFilterPanel.vue`（checkbox 列表 + AND/OR + 四维排序 + 升降序）
4. 页面接线：filteredItems 接入图库与分页；「全选筛选结果」按钮
5. i18n 词条（中/英）
6. 手测验收 P0 五条 + 回归五条

**PR-2（P1，可紧随）**

7. 检索框缩小 tag 列表（子串；前缀/后缀用 checkbox 或下拉切换）
8. NONE 逻辑 / 轻量「排除 tag」（第二组勾选或输入框，取实现成本低的）
9. caption 写回排序扩展（频率/长度，次于列表排序；时间紧可砍）

### 3.5 #227 验收对照

| Issue 验收项 | 落点 |
|--------------|------|
| 勾选 tag 后图库只显示含该 tag 的图；AND/OR 正确 | `filterItemsByTags` + 面板 |
| 一键选中筛选结果 → 批量删/加 | 「全选筛选结果」+ 现有 batch API |
| tag 列表四维排序 + 升降序 | `sortTagList` + 面板排序控件 |
| 快捷 tag 仍加词、筛图走独立勾选区 | 3.1 交互拆分 |
| 不破坏批量编辑、撤销/重做、单张 pill、布局 | 回归手测清单 |
| （P1）检索缩小列表 / NONE / 排除 | PR-2 |

### 3.6 风险

| 风险 | 缓解 |
|------|------|
| 词元长度口径与秋叶不一致 | 文档注明估算规则；预留后端精确接口为备选 |
| 大数据集下图库过滤性能 | 全量 tags 已在内存，computed 过滤 O(n·m)；千级图无压力，万级再加防抖/虚拟滚动（不预优化） |
| 页面拆分引发回归 | 拆分与功能同 PR 但分 commit；回归清单逐项过 |

---

## 4. 阶段 2：#210 beta-tagger-ui 预研与分期方案

> ⚠️ Issue 明确「等维护者下达实现指令后再写 `beta-tagger-ui/` 代码」。本节为**技术方案预研**，指令下达后直接按此执行。

### 4.1 应用形态决策（需维护者拍板）

| 决策点 | 建议方案 | 备选 |
|--------|----------|------|
| 进程形态 | 独立 FastAPI 进程，默认 `:28100`，占用即报错提示改 port | — |
| 前端形态 | **同仓独立 Vite 应用** `beta-tagger-ui/frontend/`，通过 npm workspace 共享 `frontend/src/dataset/`、`frontend/src/components/dataset/`、i18n 方案 | 把共享层发布为本地包；或复制（不推荐） |
| 后端形态 | `beta-tagger-ui/server/`，依赖 `mikazuki/dataset/`（阶段 0 抽出）+ `mikazuki/tagger/` interrogator 框架 | 完全独立包（会丢复用） |
| 启动入口 | `python -m beta_tagger_ui --port 28100`，提供 `.bat/.sh` | — |

### 4.2 后端工作清单（12 项，对应 Issue 分期）

| # | 项 | 期 | 复用/新增 |
|---|-----|----|-----------|
| B1 | 服务脚手架（app、端口、启动入口、占用报错） | 1 | 新增 |
| B2 | 递归扫描（默认开、可关）+ 扩展名白名单 | 1 | 改 `mikazuki/dataset/scanning.py`（阶段 0 已预留参数） |
| B3 | 编辑基线 API：scan/caption/batch/undo/redo | 1 | 搬 `dataset_editor.py` 薄层，契约可对齐 |
| B4 | 冲突策略：跳过 / 覆盖 / **末尾追加**（Tag `", "` 去重保序；NL `"\n\n"`） | 2 | 新增 write 策略模块 |
| B5 | 覆盖预估张数接口 + 打标写盘接入 undo 栈 | 2 | undo 复用阶段 0 |
| B6 | 打标范围解析：selected > filtered（前端传筛选后列表）> all（需确认标记） | 2 | 新增 |
| B7 | Tag 引擎接入：WD EVA02 v3（默认，0.35/0.6）、CL、**PixAI v0.9（新增 interrogator）** | 2 | 框架复用 + 1 个新 interrogator |
| B8 | 提示词库 CRUD（内置 1 条通用，仅 NL） | 3 | 新增（JSON 文件存储即可） |
| B9 | JoyCaption Beta One 本地推理 | 3 | 新增（torch，重量依赖，按需加载） |
| B10 | Qwen3-VL-2B-Instruct 本地推理 | 3 | 新增（transformers） |
| B11 | Gemini / OpenAI 云通道 + Key 管理 + 失败列表重试 | 4 | 新增 |
| B12 | 打标任务进度/取消/显式错误（缺模型/缺 Key/显存不足） | 2-4 | `tagger/progress.py` 模式搬入 |

### 4.3 前端工作清单

| # | 项 | 期 | 说明 |
|---|-----|----|------|
| F1 | 三栏壳（中编辑、左右功能）+ 色调对齐训练器 | 1 | 复用现网样式变量 |
| F2 | 编辑基线：图库/清理/批量/撤销重做 | 1 | **直接复用阶段 0/1 的 composable 与组件** |
| F3 | 中英双语骨架 | 1 | 沿用 vue-i18n 方案 |
| F4 | 打标面板（新建）：引擎选择、阈值、范围、冲突策略、进度 | 2 | 现网「打标」只是追加触发词，不作基线 |
| F5 | NL 模式区分：长 caption 不套 Tag 清理/逗号批量编辑 | 3 | **新领域概念**：caption 模式标记（tag/nl），编辑 UI 按模式禁用对应操作 |
| F6 | 失败列表 + 重试入口 | 4 | — |

### 4.4 与 #227 成果的衔接点

1. `TagFilterPanel.vue` + `useDatasetTagFilter` → beta-tagger-ui 的筛图直接复用（打标范围「当前筛选」依赖它）；
2. `mikazuki/dataset/` → 新服务扫描/caption/undo 的地基；
3. caption 模式（tag/nl）概念若在 #210 期 3 才引入，**注意不要让 #227 的排序/过滤逻辑假设 caption 一定是逗号 tag**——`tagFilter.ts` 只依赖 `tags: string[]`，天然免疫。

### 4.5 #210 验收对照（摘录映射）

| Issue 验收 | 落点 |
|------------|------|
| 单独启动即可打标+编辑，不依赖训练器 | B1 + 独立前端 |
| 跳过/覆盖/追加正确；覆盖可确认、可撤销 | B4 + B5 |
| 打标范围/默认递归 | B2 + B6 |
| 七条路径小样本跑通、失败显式报错 | B7/B9/B10/B11 + B12 |
| NL 不被 Tag 清理改写；中英切换 | F5 + F3 |
| 训练器旧打标页、编辑页保留 | 不动现有路由与页面 |

### 4.6 风险与开放问题

| 风险/问题 | 说明 | 建议 |
|-----------|------|------|
| JoyCaption/Qwen 依赖体积 | torch + transformers 进便携包体积爆炸 | 按需安装/独立环境，先出文档说明 |
| 云 API Key 存储 | 不能进 git、不能明文日志 | 系统 keyring 或本地加密配置，参考 machine-manager 做法 |
| monorepo 共享机制 | npm workspace 是否引入会动根 package.json | 期 1 开工前与维护者确认 |
| PixAI v0.9 模型格式 | 需确认 ONNX/权重与标签文件格式 | 期 2 首日 spike |
| 端口契约 | 28100 与整合包端口规划 | 对照 `docs/design/ports/` 文档登记 |

---

## 5. 里程碑总览

```
M0  阶段 0 共享层抽取                    （小 PR，先行合入 dev）
M1  #227 PR-1：P0 筛图+排序+全选闭环     （本分支 feat/issue-227）
M2  #227 PR-2：P1 检索/NONE/排除         （紧随）
─── 以上完成后等 #210 实现指令 ───
M3  #210 期 1：壳+扫描+编辑基线+双语+撤销
M4  #210 期 2：Tag 三路+冲突策略+范围
M5  #210 期 3：提示词+本地 NL 两路
M6  #210 期 4：云两路+失败重试
M7  #210 期 5：进整合包、训练器跳转、分仓（后续）
```

每个里程碑独立 PR、独立验收；M1/M2 交付即关闭 #227，M3–M6 交付关闭 #210。
