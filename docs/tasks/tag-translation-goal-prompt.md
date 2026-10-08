# Tag Translation Goal Prompt

你正在继续执行 Next Trainer 的标签中文释义任务。

## 首先读取

1. `docs/tasks/tag-translation-task-book.md`：唯一任务状态和下一步动作；
2. `docs/design/tag-translation-design.md`：已审计设计边界；
3. `docs/tasks/tag-translation-migration-inventory.md`（如果存在）：迁移来源和适配清单；
4. 当前 worktree 状态：确认仍在 `feat/tag-translation`。

## 最终目标

在 Dataset Editor 中加入英文 Danbooru tag 的中文释义辅助展示：

- Danbooru SQLite 词库优先；
- 未命中时可选择免费网络翻译；
- 未命中时可选择本地 Qwen 0.8B 或远程 OpenAI 兼容 LLM；
- 原始英文 caption、打标结果、训练配置和导出始终不变；
- 尽量迁移 Aaalice MIT 代码，只写 FastAPI/Vue 适配层；
- 不直接复制 WeiLin GPL-2.0-only 实现。

## 执行纪律

- 每次工作前先检查任务书的 `Current active phase` 和 `Next action`。
- 优先复用已存在代码，只有迁移边界不兼容时才新写模块。
- 迁移文件保留来源、版权和许可证说明。
- 不把 SQLite 词库、API Key、模型文件、网络缓存和本地绝对路径提交到 Git。
- 任何翻译结果都只能进入独立 UI 状态，不能写回 caption。
- 每完成一个可验证阶段，就更新任务书的进度台账、事实、决策、风险和下一步。
- 不创建 PR；只在当前专用分支施工并留下可审计提交。

## 当前立即动作

执行 Phase 1：

1. 固定 Aaalice 快照并生成迁移清单；
2. 扫描其翻译模块的 Python 依赖和 API 契约；
3. 下载候选 ffdkj `tag.sqlite` 到临时用户数据目录或测试临时目录；
4. 查询固定标签样本并记录 schema、命中和失败结果；
5. 决定哪些文件直接迁移、哪些只改写适配；
6. 把结果写入 `docs/tasks/tag-translation-migration-inventory.md`；
7. 更新任务书，保持唯一的 `Next action`。

## 完成判断

不要因为文件已复制就宣布完成。只有迁移清单、词库探针、依赖扫描、许可证说明和可复现命令都留下证据后，Phase 1 才能标记 done。
