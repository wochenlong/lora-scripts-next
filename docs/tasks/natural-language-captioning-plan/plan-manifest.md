# Plan Manifest

2026-10-10参考增量索引：`../../design/kohya-natural-captioning-reference-review.md` 为参考取舍与设计修改，`../natural-language-captioning-reference-modification-task-book.md` 为 Standard 增量执行台账（目标、任务、开工清单、证据治理、复盘与 goal 合并）。父 canonical 保持唯一；新增证据 `../../evidence/natural-language-captioning/2026-10-10-reference-delta/`。开发、回归和手测更新已完成，全部新增门通过；用户人工验收 pending，未宣称新真实生成或新从零验收。

2026-10-09用户手测增量：默认自然语言打标改为英文，内置提示词和System prompt随输出语言切换；自定义草稿保留并提示恢复对应模板。en正文含中文即拒绝，旧错误cache重新生成。Editor修复scan空草稿遮蔽及重新进入刷新，原文展开/恢复磁盘文本；新增只读中文译文，复用共享LLM text路由/运行时/密钥和同SQLite独立表，中文正文零模型请求、remote-first、本地显式兜底，无Key外部API不联系，取消/旧响应隔离。自然语言Tag批量入口禁用，390px面板宽度修复。原goal完成历史保留，新增验收独立记录，不把旧报告当新功能通过。

2026-10-09最终闭门：用户已手动清空sandboxes，实测五个剩余Windows根全部不存在，无自建模型/应用进程，Git过期worktree注册已清理。功能源码与候选8986b9e的Git内容一致（仅65项LF/CRLF checkout行尾差异）；此前全部验收证据有效。GATE10/G-11通过，Phase0–5完成，保留四项Windows原生symlink未验与本轮远程未配置的批准/可选边界。详见phase-5-isolated-rebuild/2026-10-09-cleanup-closure.json。用户要求在goal完成后另建全新手动测试项目，此为后续独立交付，不能复用已删除沙盒。

以下2026-10-08及更早条目保留为历史，当前状态以上述闭门结论和canonical任务书为准。

- Plan ID: `DATASET-NL-TAGGING-20261006`
- Version: `v3.0-issue-409-aligned`
- Scale mode: Full
- Contract: [Issue #409](https://github.com/wochenlong/lora-scripts-next/issues/409)
- Readiness: `complete-with-boundary`（全部硬门已关闭，批准的平台边界保留）
- Canonical progress: `../natural-language-captioning-task-book.md`
- Design source: `../../design/natural-language-captioning-tagging-design.md`
- Goal: `03_goal提示词/自然语言打标全程执行_goal提示词.md`
- Evidence root: `../../evidence/natural-language-captioning/`
- Current branch: `feat/NL-Captioning`

## Scope freeze

首版按 Issue #409 实现模型/运行方式优先的 Dataset Tagger：本地模型/API 服务为一级分类，Tag/Caption 按模型 capability 展示。WD/CL Tag 保持兼容；视觉模型支持自然语言 Caption；翻译与 Caption 共用统一 LLM 管理。

首版明确不实现、不展示、不验收 `combined`、`mixed`、Tag+Caption 串联、WD+Caption 双模型、本地+API 联合流水线。已有 mixed provenance 只用于历史/外部文件的安全兼容。API 未配置时不显示空入口。Agent、sidecar、provider、plugin marketplace 不属于本任务。

## Artifact manifest

| Artifact | Status | Purpose |
|---|---|---|
| `00_总控目标索引.md` | aligned | 总目标和边界已按Issue #409重写 |
| `00_预检证据/` | in use | 测试、授权、失败和变更治理 |
| `01_目标计划书/` | aligned | 按模型能力、预设、后端、前端和隔离重建拆分目标 |
| `02_长程任务书/` | aligned | Phase0–5执行任务和完成门，旧编号文件按正文阶段读取 |
| `03_goal提示词/` | rewritten | 可直接复制执行的 Issue #409 对齐 goal |
| `04_阶段开工清单/` | aligned | 每阶段硬门槛和失败处理，执行状态以canonical任务书为准 |
| `05_最小可行性验证/` | in use | 本地模型、user_data preset和capability风险；当前证据已补进索引 |
| `06_开工前最终复盘报告.md` | current-note-added | 保留v2历史，顶部新增#409当前事实 |
| `07_设计与任务书审计及开工准备报告.md` | current-note-added | #409重规划及最新实施/验证状态 |

## Gate status

| Gate | Status | Definition |
|---|---|---|
| GATE-00 | pass-with-boundary | 已有资料和 Issue #409 已读取；旧设计存在冲突 |
| GATE-01 | pass | #409契约、范围和out-of-scope已收敛 |
| GATE-02 | pass | 失败/重跑/隐私与清理记录已同步 |
| GATE-03 | pass | 模型能力、user_data preset、API dynamic entry目标计划已对齐 |
| GATE-04 | pass | Phase0–5长程任务书和开工清单已对齐 |
| GATE-05 | pass | Qwen/mmproj/runtime/ONNX全新公开下载与真实验收通过 |
| GATE-06 | pass | goal与canonical文档对齐，capability线上表示已说明 |
| GATE-07 | pass-with-boundary | 逐项审计完成，保留批准的平台边界与未配置远程 |
| GATE-08 | pass | 功能实施完成，OpenAPI首版范围声明已修正 |
| GATE-09 | pass-with-boundary | 前端342、后端512+Linux四原case及真实链路通过；环境口径获用户批准 |
| GATE-10 | pass-with-boundary | 第五根从零验收通过；用户删除剩余沙盒，2026-10-09实测清理完成 |

## Change control

以下变化必须同时更新 design、task book、goal、manifest、目标计划、阶段清单和证据索引，并记录原因：

- 首版 scope 增减；
- runtime/model/capability/output API contract；
- `user_data/presets` schema 或训练 preset 隔离；
- remote-first/local fallback 策略；
- Tag/natural 文件格式、冲突和原子写回；
- 测试阈值、真实资源、隔离重建步骤或完成门。

Agent/plugin/sidecar 相关内容不得通过“兼容性”名义重新加入本任务。

## Next action

原goal闭门提交并标记完成后，新建全新项目交由用户手动测试；此前历史Next action不再适用。

## 2026-10-08 实施增量

差异审计与首批预设实施见../../evidence/natural-language-captioning/phase-0-contract-alignment/2026-10-08-presets-and-delta.md。后端44/前端331通过，不是阶段/最终完成。当前Next action以canonical任务书末尾为准：模型能力目录和运行方式/模型系列选择器。

## 2026-10-08 模型目录增量

模型目录/页面/参数隔离与manager组合禁用完成；后端216、前端336及fake browser业务通过。详情见2026-10-08-model-catalog-browser.md。Next action由canonical task最新定义：预设事务/跨进程与legacy导入UI。GATE09/10未通过，旧in progress描述已由用户全面施工授权覆盖，当前executing。

## 2026-10-08 预设事务增量

预设多文件事务/进程恢复/OS跨进程锁和明确导入、系统提示词/草稿保护已实现；专项16、相关223与最后focused37、前端340/52通过，实际跨浏览器/后端重启fake验收通过。详见2026-10-08-preset-transactions-import.md。下一步TaskManager/user_data任务档案。Goal active，GATE09/10未通过。

## 2026-10-08 任务档案与Tag试标增量

既有TaskManager与user_data/tasks/dataset-tagger联动（35e5189），Tag/natural前端共用持久化链路；Tag单图HTTP预览、适用参数快照、状态恢复/真正取消/仅失败重试/安全删除和报告链接已实现。相关后端299、专项44、前端341/52/check/build与fake browser通过。证据2026-10-08-task-archives-bridge.md和2026-10-08-tag-preview-durable-ui.md。下一步真实ONNX与Qwen当前源码验收，随后正式lifespan/最终矩阵/Phase5。GATE09/10未通过。

## 2026-10-08 真实链路与验收修复增量

真实Tag/本地Qwen/正式Zero-Short及真实UI生成/取消/Editor通过；完整功能矩阵506通过/4Windows权限失败，补充Linux四原始case通过。Windows验收环境口径和新UI火箭人工评分正在等待用户答复。Tag下载取消和档案损坏类型隔离、支持语言/停止弹窗/取消模板选择等修复后专项50、前端342通过。最新证据phase-4-real-evaluation三份报告；下一步提交后完整功能矩阵复跑，Phase5未解锁，GATE09/10未通过。

## 2026-10-08 用户完成门批准

新UI火箭五维各4分，四项symlink跨平台组合验收获用户批准，保留Windows权限失败。Phase4 pass-with-boundary，Phase5 in progress；独立授权事件2026-10-08-user-gate-approval.json。下一步全新源码/依赖/URL资产重建，GATE10仍未通过，整体goal active。

## 最新完成门：2026-10-08

候选8986b9e功能/真实/从零已通过，最终证据索引2026-10-08-final-acceptance-audit.md。仅Windows剩余五个沙盒清理尚未核销；自动审批两次拒绝，已询问用户手动删除或明确保留例外。goal active，GATE10不能提前complete。


2026-10-09增量完成：候选81e85d7；前端347/53/type/lint/build，后端529通过/四项既有平台失败/0skip，真实本地English3/3与译文/cache/中文短路、浏览器16项通过。已更新现有手测项目并源构建/重启，4目录21文件SHA不变。新远程译文实测及新英文人工评分未运行，不伪称通过。详情2026-10-09-manual-feedback-change.md。


## 2026-10-10 预设统一控制（取代独立语言/详略选项）

用户授权：移除重复的“输出语言”，让提示词预设成为语言和输出格式总控。本次一并将详略入口收敛为预设中的“详细/简短”，避免多个入口描述同一份模板。

- 默认内置英文详细预设；选择预设一次应用完整 user/system prompt、语言与最大字符数。内置中英、繁体、日文各有详细/简短模板。
- 页面仅显示只读预设语言与纯文本 `.txt` 落盘格式；内部严格 JSON 响应协议仍由后端校验，不引入 JSON 文件或组合打标。
- 自定义模板继承当前预设的语言；先选择对应语言的基底再编辑、保存或另存。已有用户默认预设保持，未保存修改在切换时仍需确认。
- 切换模型不再静默换语言或模板。模型不支持预设语言时明确提示、禁用预览和批量提交；用户可选兼容预设或模型。
- 试标/批量从同一份预设草稿派生请求；重试继续使用既有冻结快照。后端 language 字段保留作为校验与 API 兼容契约，没有第二个用户语言控制来源。

验证门：无独立语言/详略下拉；中英预设完整切换；自定义保存保留 language/plain_text；试标与批量配置一致；不兼容模型不会改预设且生成禁用；取消切换保留草稿。执行前端完整 check、Caption 后端组，更新现有手测源码/构建并保护数据 SHA。新真实模型生成质量交由用户亲测。

执行记录：实现与简单验收完成；专项26项、前端349项/53文件/typecheck/lint/build、Caption后端133项、手测项目自身build、HTTP/浏览器/390px通过。手测应用已启动，53个用户数据与配置文件SHA保持。用户真实模型生成与人工验收 pending。证据目录 `docs/evidence/natural-language-captioning/2026-10-10-preset-controls/`。本次风险 P2，范围只涉及打标预设交互，API/Agent/训练不扩展；原公开完成门历史保留，不把旧证据当本次验收。
