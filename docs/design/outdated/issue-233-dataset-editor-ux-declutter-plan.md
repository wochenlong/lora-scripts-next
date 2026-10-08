# Issue #233 实施方案：标签编辑页减负——筛图/加词拆清、批量折叠、右栏合并

> **执行状态（2026-08-12）：已实施完成并推送，待手测验收。** 分支 `feat/issue-233`。
>
> 决策点按推荐方案落地：快捷 tag / 热门加词**整块删除**；caption 原文 textarea **默认折叠**（chip 为主编辑块）；中栏留白已收紧（minmax 150→140px、gap 12→8px、名条 padding 9px→6px 8px）。
>
> 提交记录：
> - `818c8f7` ux：左栏删 quick-tag-box、批量编辑 `<details>` 默认折叠（summary 带目标数）、右栏去完整路径换淡化短文件名（hover 看全路径）、chips 升主/原文折叠/单一保存、中栏收紧、dist 重建
>
> 验证：`typecheck` ✅ `lint` 0 error（3 个 warning 为无关文件既有）✅ `src/dataset` 测试 20/20 ✅ `build` 写回 dist ✅；全量测试 13 个失败为基线既有 jsdom 环境问题（与 #227 记录一致，非本次引入）；dist 已 `--renormalize`，`ls-files --eol` 确认全 `i/lf`
>
> 遗留：
> - [ ] 浏览器手测回归清单（§5），重点感受三个决策点的实际手感
> - [ ] 开 draft PR → 手测通过转 ready
> - [ ] 遗留 localStorage key `dataset-editor-quick-tags` 无害残留，未做迁移清理

> 关联 Issue：[#233](https://github.com/wochenlong/lora-scripts-next/issues/233) ux(dataset-editor): 标签编辑页减负——筛图/加词拆清、批量折叠、右栏合并
>
> 前置：[#227](https://github.com/wochenlong/lora-scripts-next/issues/227) / PR [#232](https://github.com/wochenlong/lora-scripts-next/pull/232) 已合入 `dev`（勾选筛图 / AND·OR·NONE / 多维排序 / 全选筛选 / 排除 / 缩略图+lightbox）
>
> 工作分支：`feat/issue-233`（从 `dev` 最新 `6bebe6d` 切出）
>
> 性质：**纯前端 UX / 信息架构调整**，零后端改动、零过滤逻辑改动，独立小 PR → `dev`

---

## 1. 需求范围（以 Issue 拍板为准）

### 目标

| # | 项 | 说明 |
|---|----|------|
| G1 | 左栏以「按标签筛图」为唯一主交互 | 快捷 tag / 热门「点一下加词」去掉或降为次要入口 |
| G2 | 批量编辑默认折叠 | 一行标题可展开，标题上保留目标数量信息 |
| G3 | 右栏减负合并 | 去掉完整 `relative_path`（最多淡化短文件名）；Caption 与 Tags 收成同一编辑块（chip 为主、原文同卡折叠、单一保存） |
| G4 | 中栏（可选） | 略收紧缩略图留白；「全选筛选结果」保持易发现 |

### 非目标（Issue 明确）

- 不改 tag 过滤算法 / AND·OR·NONE / 排除语义（`useDatasetTagFilter`、`dataset/tagFilter.ts` 一行不动）
- 不重做打标页（#210 独立需求）
- 不把 Gradio DTE 设回默认入口
- 不改后端 API / 数据契约

### 验收（Issue 原文）

- 打开数据集后，一屏内能清楚完成：文本筛 → 勾选 tag 筛图 → 看图 → 全选筛选 → 批量
- 左栏不再同时强调「筛图勾选」和「热门加词」两套主交互
- 右栏无完整路径刷屏；caption/tags 不表现为两套独立大模块
- `npm run build` 写回 `frontend/dist`

---

## 2. 现状清点（改动落点）

主文件：`frontend/src/pages/DatasetEditorPage.vue`（252 行，单文件承载三栏全部 UI）

### 左栏 `.dataset-side`（模板 213–241 行）

| 现状 | 处理 |
|------|------|
| 路径 + 扫描按钮（215–216） | 不动 |
| 分类下拉（217） | 不动 |
| Caption / 文件名筛选（218） | 不动 |
| `TagFilterPanel`（219–238） | 不动（G1 的主角，保持） |
| `.batch-box` 批量编辑（239，默认全部展开，11 个控件平铺） | **G2：包一层折叠**（`<details>` 或受控 collapse），summary 一行显示「批量编辑 · 已选 n 张 / 筛选结果 n 张」 |
| `.quick-tag-box` 快捷 tag + 热门 tag（240，两套 chip 列表 + 自定义管理 + 两条说明小字） | **G1：整块删除**（推荐）或降级。见 §3 决策点 |

### 中栏 `.dataset-gallery`（242–247 行）

| 现状 | 处理 |
|------|------|
| 顶栏计数 + 翻页选择/撤销/重做/历史 | 不动；「全选筛选结果」按钮保留在 `TagFilterPanel` 内（已易发现，满足 G4） |
| `.image-grid`：`minmax(150px,1fr)`、`gap:12px`、卡片内 `padding:9px` 文件名条 | G4（可选）：缩略图 gap 收到 `8px`，卡片名条 padding 收到 `6px 8px`，`minmax` 可降到 140px |

### 右栏 `.caption-panel`（248 行，单 div 平铺）

| 现状 | 处理 |
|------|------|
| `<strong>{{ current.relative_path }}</strong>` 完整相对路径刷屏 | **G3：移除**，改为淡化的 `current.name` 短文件名（`title` 悬浮可看全路径，不占地） |
| `.caption-editor` textarea rows=10 大文本框 | **G3：收进同卡折叠**（`<details>`「查看/编辑原文」，默认收起或按 caption 长度决定），字数统计小字随折叠块走 |
| `.caption-chips` tag chips + 添加输入 | **G3：升为右栏主编辑块**，置于折叠原文之上 |
| 单一「保存」按钮 | 保持单一保存（已满足）；保存仍提交 `caption` 全文，chips 编辑与 textarea 编辑同一数据源，天然一致 |

### 需要同步清理的代码

- `DatasetEditorPage.vue` script：`QUICK_TAGS_KEY`、`quickTag`、`newCaptionTag`（保留，右栏添加仍用）、`quickTags`、`popularTags`、`appendQuickTag`、`addQuickTag`、`removeQuickTag`、`onMounted` 里 quickTags 的 localStorage 读取
- i18n：`src/i18n/messages/zh-CN.ts` / `en-US.ts` 的 `datasetEditor.quickTag.*` 5 个 key 删除；新增折叠 summary、原文折叠、短文件名等 key
- 样式：`src/styles/features.css` 的 `.quick-tag-box` 相关规则删除（55/56/59/63 行附近）；新增折叠 summary、右栏合并块样式；中栏间距微调
- 测试：无现存测试引用 quickTag / batch-box（已 grep 确认），无需改测试

---

## 3. 决策点

1. **快捷 tag / 热门加词：删除还是降级？**
   - Issue 允许「去掉，或收到很次要入口」。推荐**整块删除**：其「点一下加词」功能与右栏 chip 添加（单图）和批量 append 输入框（多图）完全重合，删除后无能力损失；保留只会继续与筛图勾选抢左栏注意力。
   - 若选择降级，备选方案：收到批量编辑折叠卡内部一行「常用：chip…」，点击填入 append 输入框。实现成本略高，仍留一套冗余交互。
   - 自定义快捷 tag 的 localStorage key `dataset-editor-quick-tags`：删除后遗留数据无害，不做迁移清理。

2. **批量折叠用 `<details>` 还是受控组件？**
   - 推荐原生 `<details>/<summary>`：零状态、零 JS、自带可访问性，与本文件已有的 `tag-filter-box`/历史弹窗里 `<details>` 用法一致（251 行历史详情已用 `<details>`）。
   - 默认折叠 = 不写 `open` 属性；summary 内联显示目标数（`已选 n 张 / 筛选结果 n 张`），保证折叠态信息不丢。

3. **右栏 caption 原文折叠的默认态？**
   - 推荐默认收起原文 textarea，chip 为主；短 caption（如 < 200 字符）也不展开，保持一屏信息密度稳定。若担心「直接改长文」场景变两步，可默认展开，Issue 未拍板，实施时取收起。

4. **中栏微调幅度？**
   - 可选最低成本项：只改 `features.css` 三个数值（gap、minmax、名条 padding），不动模板。

---

## 4. 实施步骤（建议提交粒度）

1. **commit 1｜G1 左栏拆清**：删 `.quick-tag-box` 模板 + 相关 script/i18n/CSS；左栏仅剩 路径→分类→文本筛→TagFilterPanel→批量折叠
2. **commit 2｜G2 批量折叠**：`.batch-box` 包 `<details>`，summary 一行带目标数；样式微调
3. **commit 3｜G3 右栏合并**：去完整路径换淡化文件名；chips 升主、textarea 入 `<details>`；CSS 调整
4. **commit 4｜G4 中栏收紧（可选）**：CSS 数值微调
5. **commit 5｜build**：`npm run build` 写回 `frontend/dist`（提交前 `git add --renormalize frontend/dist`，提交后 `git ls-files --eol frontend/dist` 确认全 `i/lf`）

每步后跑 `npm run typecheck && npm run lint`；全部完成后 `npm run check`。

## 5. 手测回归清单

- [ ] 扫描数据集 → 左栏一屏内可见：文本筛 → tag 筛图（频率降序）→ 批量折叠条
- [ ] 勾选 tag + AND/OR/NONE + 排除 行为与 #232 完全一致（纯回归）
- [ ] 「全选筛选结果 (n)」按钮位置与功能不变
- [ ] 批量折叠条 summary 实时反映 已选/筛选 数量；展开后全部批量控件可用，批量执行成功
- [ ] 右栏：无完整路径；chip 增删 → 保存 → 图库/筛图数据联动正确
- [ ] 右栏展开原文 textarea 编辑 → 保存 → chips 同步
- [ ] 灯箱、512 预览、翻页、撤销/重做/历史弹窗回归
- [ ] 中/英双语无缺失 key（控制台无 i18n 警告）
- [ ] `frontend/dist` 由构建生成、整合包 `:28000` 打开正常

## 6. 验证

- `npm run typecheck` / `npm run lint` / `npm run check`（含 build）
- 无后端改动，无需 `pytest`；无过滤逻辑改动，`tagFilter.test.ts` 应原样通过（跑一遍确认零回归）
- 推送：`git -c http.proxy=http://127.0.0.1:7890 push`（本机直连 GitHub 会被重置）
