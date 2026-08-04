# 设计计划 — 训练 Schema 表单单列化

> **来源**：产品反馈（关联 Issue #215)
> **范围**：训练页 Schema 表单字段排布；右栏 TOML 预览布局不变。

---

## 1. 需求

主训练页 Schema 表单当前一行两列，信息密度偏高。改为**一行一个参数（单列）**，降低扫视负担，长路径与字段说明更易读。右栏 TOML 预览（含向右抽屉收起）不变。

## 2. 现状调研

| 位置 | 内容 |
| --- | --- |
| `frontend/src/styles/features.css:52` | `.schema-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;padding:20px}` —— 两列的唯一出处 |
| `frontend/src/styles/features.css:53` | ≤720px 媒体查询已将 `.schema-fields` 降为 1fr（并含 filepicker 窄屏规则） |
| `frontend/src/components/DynamicSchemaForm.vue:35` | `.schema-fields` 唯一使用点；每个 section 一个 fields 网格 |
| `frontend/src/pages/TrainingPage.vue:245` | `DynamicSchemaForm` 唯一页面使用点，覆盖全部训练 Schema（含 Anima Fast) |
| `frontend/src/components/DynamicSchemaForm.test.ts` | 只测字段逻辑，不断言布局 |

结论：改动收敛为**一条 CSS 声明 + 一处媒体查询清理**，无组件/逻辑改动，无测试依赖两列布局。Tagger 页用自己的 `.tagger-grid`，不受影响。

## 3. 方案

### 3.1 必做

1. `features.css:52`:`.schema-fields` 的 `grid-template-columns:repeat(2,minmax(0,1fr))` 改为 `minmax(0,1fr)`（单列）。
2. `features.css:53`：媒体查询中 `.schema-fields{grid-template-columns:1fr}` 声明变为冗余，删除该条；保留同查询内 filepicker 窄屏规则。

### 3.2 单列后的宽度观感（建议项，目检后定）

单列后字段控件（`el-input-number`、`el-select` 现有规则为 `width:100%`）会拉到表单全宽：

- 文本/路径/filepicker/textarea：全宽是本次需求的收益点（长路径易读），保持 100%。
- 数字、下拉等短控件：全宽可能显得空旷。备选是给 `.schema-field .el-input-number` 加 `max-width`（约 240–320px)。**默认不加**，构建后桌面目检再定，避免无依据的样式分支。
- `.field-description{min-height:30px}` 原为两列行高对齐服务，单列下不再必需；默认保留（最小改动），目检若显空洞再评估。

### 3.3 明确不动

- 右栏 `.control-panel` / TOML 预览 / 抽屉收起（`preview-docked`）全部不变；单列只影响左侧 `.form-canvas` 内的 fields 网格。
- 组件、Schema、i18n、测试零改动。

## 4. 实施步骤

1. 修改 `features.css` 两处（3.1)。
2. 验证：`npm run check`；桌面 + ≤720px 手工目检各训练页表单（含 Anima Fast、条件分支字段、filepicker、textarea、自定义参数 table 角色）。
3. 按目检结果决定是否落地 3.2 的数字控件 `max-width`。
4. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 5. 验收标准

- 所有训练页 Schema 表单一行一个参数；长路径与说明文字完整易读。
- ≤720px 窄屏表现与现状一致（本就单列）。
- 右栏 TOML 预览布局与抽屉收起行为不变。
