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

- ⑤ Schema 分区命名对齐旧版(adapter 无标题 intersect 展开)→ 见下方「§5 实施计划」
- ⑥ 数据集浏览按钮 / tag 位置 / 空分页贴底 → 见下方「§6 实施计划」
- ⑦ 任务页内嵌训练日志面板(折叠 + 红点)→ 见下方「§7 实施方案」

## §7 实施方案:任务页内嵌训练日志(云端适配)

### 现状清点

| 关注点 | 现状 | 位置 |
| --- | --- | --- |
| 任务详情结构 | header → 进度条 → meta → actions(含「新窗口打开日志」)→ 预览图 → Loss | `pages/TasksPage.vue:172-201` |
| 日志 API | SSE `GET /api/train/log/stream/{task_id}`(全量回放 + `{done}` 结束);`GET /api/train/log/tail/{task_id}?limit=`(≤2000 行,返回 `lines/total/done`);旧任务(非本会话)404 | `mikazuki/app/api.py:1148,1218` |
| 前端 API 层 | `tasksApi` 无日志方法 | `api/tasks.ts:50-55` |
| 「新窗口打开」 | `/train-log?task_id=…`(后端独立 HTML,保留不动) | `TasksPage.vue:187` |

### 改动(纯前端,后端零改动)

1. **`api/tasks.ts`**
   - `logTail(taskId, limit?)` 类型化 client(`TaskLogTail { lines, total, done }`)
   - `trainLogStreamUrl(taskId)` 返回 SSE 路径(组件用 `EventSource` 消费)
2. **新建 `components/TaskLogPanel.vue`**(props:`taskId`、`status`)
   - **默认折叠**。折叠态:每 ~4s 轮询 `logTail(240)` 做错误探测;命中正则 `/\berror\b|\btraceback\b|out of memory|\boom\b/i` 或 `status === "FAILED"` → 标题旁红点
   - **展开态**:`EventSource` 消费 SSE(回放全量缓冲,`{done}` 后关闭);`EventSource` 不可用/报错回退 tail 轮询;正文 `pre` 滚动区(~320px,monospace)
   - 工具行:跟随底部开关(默认开,新行自动滚底)、跳到最后一次报错(最后命中行 `scrollIntoView`)、复制(`navigator.clipboard` + 回退)、下载(Blob → `train-log-{taskId}.txt`)、行数显示
   - 切换任务/组件卸载:关流、清空、重置红点;tail/stream 404(跨会话旧任务)→ 显示「本会话无日志」态,不亮红点(除非 FAILED)
3. **`TasksPage.vue`**:Loss 区块下加 `<TaskLogPanel :task-id="selected.id" :status="selected.status" />`;「新窗口打开」链接保留
4. **CSS**(`features.css` 任务页段):面板复用 `task-placeholder` 卡片语言;红点复用 rail-alert 样式语义;工具行 ghost 小按钮
5. **i18n**(zh/en):`tasks.log.title|expand|collapse|errorBadge|follow|jumpToError|copy|copied|download|empty|unavailable`
6. **测试**:`TaskLogPanel.test.ts` — mock `tasksApi.logTail`,jsdom 无 `EventSource` 走 tail 回退;断言:默认折叠、FAILED 出红点、tail 命中 Error 出红点、展开渲染日志行

### 验证

`npm run typecheck` → `lint` → `vitest`(新组件测试)→ `build`;后端无改动,不需 pytest。

## §8 实施方案:缺失模型资产弹窗下载(musubi/krea2 先行)

### 背景

musubi 训练除本地模型文件外还有隐性 HF 依赖(tokenizer),网络不可达时直接炸在训练中途。设计定稿(用户确认):

- 每种训练类型内置**默认资产清单**(默认本地路径 + HF/ModelScope 下载源)
- 校验发现缺失**不直接报错**,弹窗询问是否下载,源二选一(ModelScope / HuggingFace),可 X 取消
- 主平台 `requirements.txt` 增加 `modelscope` 依赖(下载在主后端进程执行)

### 改动

1. **`mikazuki/musubi_backend/assets.py`(新)**
   - `AssetDef { key, label, default_path, hf_repo, hf_file, ms_repo, ms_file }`
   - `KREA2_ASSETS`:dit / vae / text_encoder(+可选 turbo_dit);repo id 由 `config/musubi_backend.toml [assets.krea2.*]` 覆盖(代码不硬编未证实的 repo)
   - `check_assets(values, project_root) -> missing`(按表单实际填的路径判断,相对路径基于 cwd)
   - 下载任务:HF 走 `hf_hub_download(local_dir=…)`;ModelScope 走 `modelscope` SDK;经 tm 任务 + train_log_hub 输出日志/进度(复用 `/api/train/log/stream`)
2. **`mikazuki/app/api.py`**
   - `POST /api/plugins/musubi/assets/check` {config} → `missing_assets[]`
   - `POST /api/plugins/musubi/assets/download` {items, source} → 后台任务 + log_stream
3. **`requirements.txt`**:+ `modelscope`
4. **前端**
   - `api/musubi.ts`:`assetsCheck` / `assetsDownload` + 类型
   - `TrainingPage.submit()` krea2 分支:preflight 前先 check → 有缺失 → 新组件 `AssetDownloadDialog`(el-dialog,缺失列表 + 源单选 + 进度;X/取消即中止提交)→ 下载完成重跑 check/preflight → 继续提交
   - i18n `training.assets.*` 双语
5. **测试**:`tests/test_musubi_assets.py`(check 命中/缺失、config 覆盖、下载任务 hf/modelscope 路径 mock)

### 不做(v1)

- 其它后端(sd15/sdxl/flux 底模)资产清单——机制通用,按 `ASSET_REGISTRY` 补条目即可

### 已补充(tokenizer 套路)

- krea2 清单 5 项已填死双源 repo(HF/ModelScope 同为 `Comfy-Org/Krea-2`,文件布局一致;tokenizer 为 `Qwen/Qwen3-VL-4B-Instruct`)
- `tokenizer` 为 `kind="hf_cache"` 特殊资产:musubi 的 `AutoTokenizer.from_pretrained` 只认 Hub id/缓存,CLI 未暴露本地目录参数,故下载落点铺进 HF hub 缓存布局(`refs/main` + `snapshots/main/`),ModelScope 下载经 `_materialize_hf_cache` 转换,断网可命中

### 验证

后端 `pytest tests/test_musubi_assets.py`;前端 `npm run typecheck && lint && vitest && build`。

## §6 实施计划:数据集打标 / 标签编辑

### 现状清点

| 关注点 | 现状 | 位置 |
| --- | --- | --- |
| 打标「图片文件夹」 | 纯文本 input,无浏览 | `pages/TaggerPage.vue:23`(`form.path`) |
| 编辑「数据集目录」 | 纯文本 input,无浏览 | `pages/DatasetEditorPage.vue:188` |
| 批量添加 tag | `append` 只支持追加到末尾;后端 `batch_edit` 固定 `next_tags.append` | `DatasetEditorPage.vue:126-139`、`mikazuki/dataset_editor.py:286-338` |
| 快捷 tag | `appendQuickTag` 写入 append 框(去重),位置由批量执行决定 | `DatasetEditorPage.vue:157-161` |
| 空工作台 | 未 scan 时 `.image-grid` 为空,pager 悬在中部 | `DatasetEditorPage.vue:195-199`、`features.css` `.dataset-gallery` |
| 浏览 API | 已有 `schemasApi.pickFile("folder")`(tkinter 后端弹窗,训练页同款) | `api/schemas.ts:36` |

### 改动

1. **浏览按钮(前端)**
   - `TaggerPage.vue` 与 `DatasetEditorPage.vue` 路径行加「浏览」按钮(复用 i18n `schemaForm.browse`):调 `schemasApi.pickFile("folder")`,`replaceAll("\\","/")` 写回;`picking` busy 态 + 失败 `ElMessage`(模式照抄 `SchemaField.vue:21-31`);仍可手填
   - CSS:路径行改 `grid-template-columns:minmax(0,1fr) auto`
2. **添加位置(前后端)**
   - `mikazuki/dataset_editor.py`:`BatchEditRequest` 加 `append_position: Literal["front","back"] = "back"`;`batch_edit` 中 front 时追加 tags 去重后**前置**到 `next_tags`;「删除 tag」不动
   - `api/dataset.ts`:`BatchEditRequest` 加 `append_position?: "front" | "back"`
   - `DatasetEditorPage.vue`:batch-box 加位置 select(最前面/最后面,默认最后面),`batch()` 传参;快捷 tag 逻辑不变(写入 append 框,执行时按所选位置生效)
   - 单张 caption 的 chip 添加(`addCaptionTag`)不在反馈范围,保持末尾追加
3. **空工作台贴底(前端)**
   - `DatasetEditorPage.vue`:`!root` 时 `.image-grid` 区域渲染空状态说明(未加载数据集提示 + 引导),pager 始终渲染
   - `features.css`:`.dataset-gallery` 改 flex column,`.image-grid`/`empty-state` `flex:1`,`.dataset-pager` `margin-top:auto` 贴底
4. **i18n**:zh-CN / en-US 增 `datasetEditor.batch.position|positionFront|positionBack`、`datasetEditor.gallery.empty*`;浏览复用 `schemaForm.browse`
5. **测试**:`tests/test_dataset_editor_api.py` 加 prepend 用例(front/back/去重);`dataset/caption.test.ts` 不动

### 验证

前端 `npm run typecheck && npm run lint && npm run build`;后端 `pytest tests/test_dataset_editor_api.py`。

## §5 实施计划:Schema 分区命名对齐旧版

### 根因

`mikazuki/schema/shared.ts` 的 `SAVE_SETTINGS`(:94)、`LR_OPTIMIZER`(:113)、`ANIMA_FAST_LR_OPTIMIZER`(:186)、`PREVIEW_IMAGE`(:249)、`LOG_SETTINGS`(:273) 以及 `lora-master.ts:2`(:「训练用模型」)、`lora-master.ts:93`(「网络设置」)等内联结构,都是**外层无 `.description()` 的 `Schema.intersect`**,标题在内层第一个 object 上。`frontend/src/schema/adapter.ts` 的 `buildSections()` 只读顶层节点标题 → 整块落入「高级设置」且互相合并。

### 改动

1. **`frontend/src/schema/adapter.ts` — `buildSections()` 递归展开**
   - 有标题节点:维持现状(`collectFields` 整组成一个 section)
   - 无标题 intersect:下钻 `list` 子节点——有标题 object → 独立命名 section;无标题 object / 条件 union 碎片 → 并入上一 section;位于首位且无上一 section 时才落到「高级设置」兜底
   - `collectFields` / `conditionsFrom` / 序列化 / 校验逻辑不动,字段集合与条件不变
2. **`frontend/src/schema/adapter.test.ts` — 回归断言**
   - 真实 schema(lora-master / flux-lora / sd3-lora)sections 含「保存设置 / 学习率与优化器设置 / 网络设置 / 训练预览图设置 / 日志设置」
   - 条件字段(`lr_scheduler_num_cycles`、`prodigy_d0`、`wandb_api_key`)并入所属命名区
   - 合成用例:leading 无标题碎片 → 「高级设置」兜底
   - `dreambooth.ts:191` 显式「高级设置」保留

### 不需要改

后端 `mikazuki/schema/*.ts`(前端展开即可,避免 schema hash 缓存失效)、`DynamicSchemaForm` / `SectionToc`(自动受益)、i18n(`advancedSection` 留作兜底)。

### 验证

`npm run typecheck` → `npm run lint` → `npx vitest run src/schema/adapter.test.ts` → `npm run build`。

## 验证

`npm run typecheck` → `npm run lint` → `npm test` → `npm run build` + 桌面/移动端手工检查(最终 `npm run check`)。
