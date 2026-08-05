# PR #209 UI 反馈实现计划

> 依据:`pr209-ui-feedback-reference.md`(分支 ref/pr209-ui-feedback @ dad86a4f)第 1–4 节。
> 目标分支:`refactor/vue3-frontend`。产品意向稿,不强制像素级还原,按现有 Vue 3 组件体系实现。

## 现状清点

| 关注点 | 现状 | 位置 |
| --- | --- | --- |
| 训练工作台布局 | 双栏 grid:`.form-canvas` + `.control-panel`(sticky,含 TOML 预览与主控) | `frontend/src/pages/TrainingPage.vue:266-294`、`styles/layout.css:5` |
| 右栏折叠 | `previewCollapsed` → `.preview-docked`(56px rail),持久化 `ui-configs.training_preview_collapsed`;折叠按钮为文字「收起/展开」 | `TrainingPage.vue:289`、`layout.css:7-22` |
| Schema 控件 | 所有控件整列全宽堆叠;`.schema-field .el-input-number,.el-select{width:100%}` | `components/SchemaField.vue:44-59`、`features.css:52` |
| 开始/停止 | `.submit-row` 中开始 `width:100%` 主色,停止为浅红底+红描边次要样式 | `TrainingPage.vue:292`、`features.css:35,54` |
| 分区目录 | 不存在;section 卡片无 DOM 锚点 | `components/DynamicSchemaForm.vue:33-38` |

## 实施项

### ① Schema 控件秋叶式右对齐

- `SchemaField.vue`:模板重构为 `.field-text`(label+description)+ `.field-control`(控件)两段;非紧凑字段用 `display:contents` 保持原布局不变。
- 紧凑类(行布局、控件靠右定宽):boolean(switch)、number(步进 ~180px)、无 role 短 string(小框 ~200px)、options(select ~200px)。
- 全宽类维持现状:filepicker、textarea、array。
- `features.css`:新增 `.schema-field--compact` 规则(行布局、`justify-content:space-between`、控件定宽覆盖 `width:100%`);<900px 退回全宽竖排。

### ② 开始/停止同级

- `.submit-row` 两按钮 `flex:1` 等宽。
- 停止改实心危险色(红底白字),不动全局 `.danger-action`(任务页仍用),作用域限定 `.submit-row .stop-training`。
- rail 折叠态 `rail-stop` 同步实心化。

### ③ 分区目录(sticky sections index)

- 新建 `components/SectionToc.vue`:
  - props:`sections: { id, title }[]`;默认收起为 ~10px 细缝(带 `→` 指示)。
  - hover/click 细缝展开为 overlay 面板(absolute,不推布局);mouseleave 自动收回;点选分组滚动定位后收回;展开态头部 `←` 收起。
  - IntersectionObserver 做当前分组高亮;<900px 隐藏。
- `DynamicSchemaForm.vue`:section 加 `:id="`sec-${section.id}`"` 锚点。
- `TrainingPage.vue`:`tocSections` computed(过滤无可见字段的分组,复用 `isFieldActive`),`<SectionToc>` 置于 `.form-canvas` 内首位置,sticky 贴整列左侧(含 WorkbenchHeader/selector 上方区域)。

### ④ 折叠方向箭头

- 右栏 TOML:展开态收起按钮 → `→`;rail-handle 顶部加 `←`。
- 左栏目录:细缝 `→`,展开面板头部 `←`。
- 使用 Unicode 箭头(项目未引入图标库),保留 i18n aria/title 文案。

## 涉及文件

- `frontend/src/components/SchemaField.vue`(①)
- `frontend/src/components/SectionToc.vue`(新建,③④)
- `frontend/src/components/DynamicSchemaForm.vue`(③ 锚点)
- `frontend/src/pages/TrainingPage.vue`(②③④)
- `frontend/src/styles/features.css`、`layout.css`
- `frontend/src/i18n/messages/zh-CN.ts`、`en-US.ts`
- 测试:`DynamicSchemaForm.test.ts` 回归 + 新增 `SectionToc.test.ts`

## 范围外(参考稿第 5–7 节,另行处理)

- ⑤ Schema 分区命名对齐旧版(adapter 无标题 intersect 展开)
- ⑥ 数据集浏览按钮 / tag 位置 / 空分页贴底
- ⑦ 任务页内嵌训练日志面板(折叠 + 红点)

## 验证

`npm run typecheck` → `npm run lint` → `npm test` → `npm run build` + 桌面/移动端手工检查(最终 `npm run check`)。
