# 自然语言打标参考结论落地任务书

## 计划元数据

- Plan ID: `DATASET-NL-TAGGING-REFERENCE-DELTA-20261010`
- Version: `v1.1`
- Last updated: `2026-10-10 Asia/Shanghai`
- Canonical progress file: `docs/tasks/natural-language-captioning-task-book.md`
- Delta execution ledger: 本文（本次增量明细，父任务书保持唯一总进度）
- Parent plan: `docs/tasks/natural-language-captioning-task-book.md`
- Current branch: `feat/NL-Captioning`
- Current active phase: `Phase 3 - 双语默认模板落地与回归验证`
- Execution readiness: `开发与简单测试完成，交付用户人工验收`

## 目标

吸收 Kohya-LoRA-Tool 在语言选项和双语完整提示词上的有效经验，修正当前默认提示词在中文请求下仍可能使用英文指令的问题，保持现有自然语言翻译、编辑器安全、统一 LLM 管理和 Issue #409 边界，并交付可供用户手测的稳定版本。

## 范围与约束

- In scope：参考复审文档；后端完整中英文内置模板；前端内置模板和系统提示词；简短/详细描述选项；默认语言模板选择；回归测试；更新现有手测项目及说明。
- Out of scope：Agent 接口、独立服务、组合 Tag+Caption、重新下载模型、修改用户 API Key、重建已完成的全量验收。
- 约束：保留工作树中 `tests/test_diffsynth_review.py` 的既有未提交改动；不提交真实 Key；不把本地路径和原始响应写入公开报告；远程优先，本地必须显式兜底。

## 决策记录

### Verified facts

- 参考项目英文和中文是两套完整模板，但没有实际正文语言校验和 Caption 整句翻译。
- 当前分支已有共享 LLM 翻译、中文短路、英文正文校验、Editor 原文恢复和自然语言 Tag 操作禁用。
- 当前后端默认提示词只有英文模板加语言占位符，前端模板同样偏短。

### Locked decisions

- 英文默认；中文和英文模板独立维护。
- 只有没有用户自定义 prompt 时才自动选择内置模板。
- 语言与详略统一由提示词预设控制；已修改的自定义模板在切换预设时先确认，取消不丢失。

### Open questions

- 无。真实远程 API 和本地视觉服务由用户手测时按现有说明选择，不作为本次自动测试前置条件。

## 执行阶段

### Phase 1：参考复审与设计冻结

- Outputs：`docs/design/kohya-natural-captioning-reference-review.md`；本任务书。
- Completion criteria：明确采纳双语模板和选项设计，明确不采纳架构和翻译实现。
- Validation：检查文档与 Issue #409、父任务书和现有实现没有范围冲突。

### Phase 2：双语模板实现

- Outputs：`mikazuki/tagger/caption.py`、`mikazuki/tagger/caption_api.py`、`mikazuki/tagger/caption_job.py`、`frontend/src/dataset/captionPrompts.ts`。
- Completion criteria：未提供 prompt 时按语言选完整模板；用户 preset 和自定义草稿优先；en/zh-CN/zh-TW/ja 都有明确输出语言和可见事实约束。
- Validation：后端模板与 snapshot 单元测试；前端 typecheck、lint、组件测试和 build。

### Phase 3：回归测试与交付手测

- Outputs：测试日志、git diff 审计、更新后的手测重点。
- Completion criteria：新增测试通过，现有前后端专项测试通过；无真实 Key；工作树中只保留用户既有未提交改动和本任务改动。
- Validation：Python caption contract tests；前端 Caption 相关 Vitest/typecheck/lint/build；必要时运行后端完整 caption 测试组。

## 硬性完成门

- `REF-01`：参考审计明确其价值只限于选项组织和完整双语模板。
- `PROMPT-01`：英文默认模板全英文；中文默认模板全中文；提示词要求严格 JSON 和目标语言。
- `PROMPT-02`：无 prompt 时中文请求不再落到英文默认模板；已有 prompt 不被覆盖。
- `OPTION-01`：提示词预设统一选择语言与简短/详细完整模板；无独立输出语言/详略选项；已修改/自定义提示词先确认，取消不丢草稿。句数是模型指令，不是后处理强行删句。
- `TEST-01`：英文含中文正文拒绝；中文无汉字正文拒绝；模板选择有回归测试。
- `SCOPE-01`：没有 Agent、组合打标、独立服务或 API Key 改动。
- `HANDOFF-01`：给用户明确手测入口和重点测试功能。

## 进度台账

- Phase 1：done
- Phase 2：done
- Phase 3：done（开发与简单测试交付完成，用户人工验收 pending）
- Validation status：Python3.11 Caption组133 passed；Node22前端348项/53文件/typecheck/lint/build通过；手测项目自身build/HTTP/浏览器中文零翻译请求及390px通过；53文件数据hash全一致。证据 `docs/evidence/natural-language-captioning/2026-10-10-reference-delta/verification-report.md`。
- Residual risks：真实视觉模型输出质量和远程 API 运行仍需用户手测；自动测试不替代真实验收。

## 下一步动作

用户打开现有手测项目，按新增验收清单测试英文/中文生成、详略、原文与译文。

## 开工清单、治理与复盘（本次 Standard 增量合并记录）

- 已读 Issue #409 对齐设计、父任务书、manifest、参考源码和运行报告；分支核实为 `feat/NL-Captioning`，基线 `9927224`。
- 预检发现缺口：默认中文请求可能使用英文指令。修改边界明确，无需重新探测模型架构。
- 失败处理：测试失败保留日志，修复后重跑对应验证；环境失败换回项目支持环境，不能用 skip 核销。
- 证据：`docs/evidence/natural-language-captioning/2026-10-10-reference-delta/`。不保存 Key、供应商原始响应或用户配置全文。
- 执行环境：已有隔离 Python 3.11.15、Node 22.17.1；完整 Caption 组和前端 check；既有用户数据及工作树修改保持。
- 变更控制：新增选项只是完整内置 prompt 预设选择器，实际 template/system 进入既有任务快照、revision、缓存和重试；不新增重复 LLM 配置或请求参数。
- 交付方式：更新手测项目代码并从其源码构建；备份覆盖的旧源码和旧 dist，停止自有应用后更新；数据集、配置、预设、任务、缓存保持字节不变。服务重启会清除仅运行时存在的 Key，用户按既有契约重新注入。
- 资源限额：自动测试约 2 分钟、日志小于 2 MiB；浏览器不发远程生成请求；新备份不含模型副本。保留用户要求的手测项目，不自动删除它。
- 完成门复盘：REF/PROMPT/OPTION/TEST/SCOPE/HANDOFF 均需逐项核验；本次不重复原 Phase 5 隔离重建，用户要求的验证为简单测试后亲自验收。

## 本次执行 goal 提示词（归档，当前用户已授权执行）

在 `feat/NL-Captioning` 按本任务书和 `docs/design/kohya-natural-captioning-reference-review.md` 完成参考结论落地。按参考审计→模板与选项实现→自动回归→更新现有手测项目的顺序推进。优先英文；中英完整 user/system 模板，保留繁体/日文已有能力；简短/详细只切换预设，不修改模型管理或新增接口。用户自定义草稿/预设不静默覆盖。验证 HTTP 默认语言模板、preview 无写盘、批量写回、正文语言拒绝、中文翻译零请求及前端草稿保护。保留 Agent、训练、既有 `test_diffsynth_review.py` 和用户数据。使用项目支持环境完成 Caption 测试组和前端 check，留下真实结果。最后更新同一手测项目，确认 HTTP/浏览器可用，告诉用户重点测试英文/中文、详略、原文、译文、中文短路、预设、Tag 安全与既有文件保护；不把用户尚未完成的人工验收写成通过。


## 2026-10-10 预设统一控制（取代独立语言/详略选项）

用户授权：移除重复的“输出语言”，让提示词预设成为语言和输出格式总控。本次一并将详略入口收敛为预设中的“详细/简短”，避免多个入口描述同一份模板。

- 默认内置英文详细预设；选择预设一次应用完整 user/system prompt、语言与最大字符数。内置中英、繁体、日文各有详细/简短模板。
- 页面仅显示只读预设语言与纯文本 `.txt` 落盘格式；内部严格 JSON 响应协议仍由后端校验，不引入 JSON 文件或组合打标。
- 自定义模板继承当前预设的语言；先选择对应语言的基底再编辑、保存或另存。已有用户默认预设保持，未保存修改在切换时仍需确认。
- 切换模型不再静默换语言或模板。模型不支持预设语言时明确提示、禁用预览和批量提交；用户可选兼容预设或模型。
- 试标/批量从同一份预设草稿派生请求；重试继续使用既有冻结快照。后端 language 字段保留作为校验与 API 兼容契约，没有第二个用户语言控制来源。

验证门：无独立语言/详略下拉；中英预设完整切换；自定义保存保留 language/plain_text；试标与批量配置一致；不兼容模型不会改预设且生成禁用；取消切换保留草稿。执行前端完整 check、Caption 后端组，更新现有手测源码/构建并保护数据 SHA。新真实模型生成质量交由用户亲测。

执行记录：实现与简单验收完成；专项26项、前端349项/53文件/typecheck/lint/build、Caption后端133项、手测项目自身build、HTTP/浏览器/390px通过。手测应用已启动，53个用户数据与配置文件SHA保持。用户真实模型生成与人工验收 pending。证据目录 `docs/evidence/natural-language-captioning/2026-10-10-preset-controls/`。本次风险 P2，范围只涉及打标预设交互，API/Agent/训练不扩展；原公开完成门历史保留，不把旧证据当本次验收。
