# 自然语言打标全程执行 Goal

你现在开始执行 DATASET-NL-TAGGING-20261006 的完整交付任务。目标是把数据集模块的自然语言打标功能、统一 LLM 管理、后端任务链路、前端 TaggerPage、Dataset Editor 安全和所有验收工作完整实现，并在最后通过一次从零开始的隔离重建真实验收。不得以“代码已写完”或“测试通过一部分”作为完成结论。

## 开工位置与必读资料

当前开发分支固定为 feat/NL-Captioning。先记录当前 commit、git status、运行时版本和工作树路径，再读取以下资料：

1. docs/tasks/natural-language-captioning-task-book.md
2. docs/design/natural-language-captioning-tagging-design.md
3. docs/tasks/natural-language-captioning-plan/plan-manifest.md
4. docs/tasks/natural-language-captioning-plan/00_总控目标索引.md
5. docs/tasks/natural-language-captioning-plan/00_预检证据/
6. docs/tasks/natural-language-captioning-plan/01_目标计划书/
7. docs/tasks/natural-language-captioning-plan/02_长程任务书/当前阶段对应文件
8. docs/tasks/natural-language-captioning-plan/04_阶段开工清单/当前阶段对应文件
9. docs/tasks/natural-language-captioning-plan/05_最小可行性验证/minimal-feasibility-probe-plan.md
10. docs/tasks/natural-language-captioning-plan/07_设计与任务书审计及开工准备报告.md

不得重复消耗已完成的 TagUI 分析、SiliconFlow 三样本验证或 Qwen3-VL-2B P1 探针；可以复用其摘要、模型 revision、SHA、资源边界和失败边界。

## 不可变决策

- 翻译和打标共用同一套 LLM 管理、profile、asset、runtime、cache、connection test 和脱敏策略。
- 翻译 profile 不要求 vision；natural/combined caption profile 必须声明 vision capability。
- 远程 LLM API 永远优先；远程可用时不得主动改走本地。只有用户显式启用且远程失败时，才允许本地 LLM 兜底。
- V1 的训练 Tag 继续由 WD/CL 生成；LLM 只生成自然语言 caption，不得把自然语言句子偷偷拆成 Tag。
- Qwen3-VL-2B Q4_K_M + Q8 mmproj 是本地中文兜底候选；SmolVLM-256M 只能标记为英文/低资源候选，不能宣称中文质量。
- API Key 只能在后端运行时注入和保存为掩码；不得写入前端、Git、日志、测试报告、任务书、环境文件或截图。
- 远程请求只发送受限 JPEG data URL，不发送本地绝对路径、数据集名称或其他隐私字段。
- 自然语言和 mixed caption 不得经过 Tag 的逗号清理、排序、去重或下划线转换。
- 写回必须原子化并带 before hash；外部修改触发 caption_conflict，不能覆盖用户更新。

## 阶段顺序和执行规则

按 Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 顺序执行，不能跳过完成门：

### Phase 0：预检与统一 LLM

实现统一 profile contract、v4→v5 迁移、capability/language、revision、remote-first/local-fallback route、fake text/vision endpoint，并保持旧翻译 API、旧 /api/interrogate 和旧 TaggerPage 兼容。先运行 migration、contract、旧翻译和灰度回归。

### Phase 1：后端视觉任务

实现 image preprocessing、data URL、prompt preset/snapshot、strict JSON schema、vision adapter、cache、Tag/natural/combined formatter、atomic writer、progress、cancel、retry-failed、report、in-use lock 和 conflict guard。用 fake endpoint 覆盖成功、超时、429、非法 JSON、取消、部分失败和恢复，再运行低限额真实模型。

### Phase 2：前端与编辑器安全

实现共享 LLM settings、profile 能力过滤、远程优先排序、提示词编辑/取消回滚、单图预览、批量进度、取消、重试、错误和隐私提示；接入 TaggerPage；让 Dataset Editor 识别 tag/natural/mixed，禁止危险清理并保留原文。运行 Node 22 的 check、typecheck/lint/Vitest/build 和组件/手工验收。

### Phase 3：评测、发布与维护

建立脱敏冻结评测集和 EDD rubric，分别验证远程中文 profile 与 Qwen3-VL-2B 本地中文兜底，记录 baseline/current、失败样本、资源成本、缓存隔离、回滚、隐私扫描、Zero-Short 和发布说明。此阶段完成不等于最终交付。

### Phase 4：隔离重建与从零真实验收

从全新的 worktree 或干净源码包创建全新目录、全新 Python 环境、全新前端依赖目录，禁止复用旧 .venv、node_modules、模型缓存、配置、SQLite、测试输出和未提交文件。重新安装、构建、启动并健康检查前后端；以空配置完成 Zero-Short；在公开/脱敏样本上完成 Tag、natural、combined；验证远程优先、远程失败后显式本地兜底、预览不写盘、取消、失败重试、冲突保护、原子写回和 Dataset Editor mixed safety；运行完整测试矩阵；完成隐私扫描、清理和人工验收。任何一个环节失败都不能宣告完成，必须记录证据并回到对应阶段修复，然后重新建立隔离环境。

每个阶段开始前必须读取该阶段开工清单并逐项打勾；每个阶段结束必须更新 canonical task book、plan-manifest、设计书、阶段清单、证据目录和 progress ledger。每个阶段只保留一个具体的 Next action。遇到硬门禁失败，生成 failure report，不得用口头说明替代。

## 必测验证矩阵

必须实际运行并保存证据：

- Unit：配置迁移、mask/revision、模板、图片压缩、caption format、formatter、cache key、原子写回；
- Contract：所有新 API、旧翻译 API、旧 /api/interrogate、错误码、任务状态、掩码 Key；
- Integration：fake OpenAI-compatible text/vision server、remote-first fallback、本地 readiness、Tag + caption、缓存、取消、重试；
- Gray：旧 Tag 与 mode=tag 逐文件比较，旧翻译 facade 与统一服务比较；
- Frontend：Node 22 check、typecheck/lint/Vitest/build、关键组件和手测；
- Real：远程中文 profile、本地 Qwen3-VL-2B、3–5 张公开/脱敏样本、真实写回和冲突保护；
- EDD：冻结样本、schema/规则质量、人工评分、失败样本和 revision baseline；
- Zero-Short：空配置、无 Key、无词库、无视觉模型时可启动且有可操作提示；
- Isolated rebuild：新目录、新依赖、新配置、新测试输出，完整重复上述关键链路。

如果某类测试确实不适用，必须在证据中写出原因、替代检查和批准人，不能默认为通过。

## 阻塞和暂停规则

只有以下情况允许暂停并向用户报告：未授权的 P0/P1、不可逆数据操作、凭据或隐私边界、架构锁定冲突、真实资源不可获得且没有已批准替代路径。普通代码取舍、测试修复、文档同步和可逆实现细节自行处理。不得因为任务较长而提前结束，也不得把旧 worktree 的未提交实现直接当作新分支完成。

## 最终完成标准

只有同时满足以下条件才能将任务书、manifest 和最终复盘标记为 complete：

1. 后端功能、前端 UI、Dataset Editor 安全和共享 LLM 管理均已实现；
2. 完整验证矩阵全部有实际命令和证据，失败项已修复或有明确授权；
3. 远程优先和本地显式兜底在真实路径中均可复现；
4. 用户可编辑提示词、预览、批量执行、进度、取消、失败重试、冲突保护和安全写回均通过；
5. 旧 Tag、旧翻译 API 和既有翻译功能回归通过；
6. 人工验收覆盖桌面、窄屏、键盘、空配置、错误、隐私提示和回滚；
7. Phase 4 隔离重建从零真实验收通过，证据证明不依赖旧工作树和旧缓存；
8. Git、日志、报告和构建产物不包含 API Key、本地路径、用户图片、原始响应或模型二进制；
9. 未授权 P0/P1 为零，所有计划文档与代码/证据状态一致。

最终报告必须列出：实际变更文件、运行过的每条验证命令、通过/失败结果、真实资源和样本边界、隔离重建路径、清理结果、剩余风险和维护动作。未满足任一条时，明确标记为未完成并继续执行。
