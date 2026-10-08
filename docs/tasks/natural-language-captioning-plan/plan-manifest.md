# Plan Manifest

- Plan ID: `DATASET-NL-TAGGING-20261006`
- Version: `v3.0-issue-409-aligned`
- Scale mode: Full
- Contract: [Issue #409](https://github.com/wochenlong/lora-scripts-next/issues/409)
- Readiness: `executing`（用户明确全面施工；差异表已归档，当前契约修复中）
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
| GATE-02 | pending | 证据治理与失败/清理策略同步 |
| GATE-03 | pass | 模型能力、user_data preset、API dynamic entry目标计划已对齐 |
| GATE-04 | pass | Phase0–5长程任务书和开工清单已对齐 |
| GATE-05 | pass-with-boundary | P1和当前本地真实/预设事务风险验证；最终fresh资产未验 |
| GATE-06 | pass | goal与canonical文档对齐，capability线上表示已说明 |
| GATE-07 | pending | Issue #409 对齐最终复盘 |
| GATE-08 | in progress | 用户已全面授权；实施和验证进行中 |
| GATE-09 | in progress | 功能/前端/真实本地通过，4项Windows权限失败及最终审计未核销 |
| GATE-10 | pending | 全新隔离重建和最终验收 |

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

完成当前矩阵与Phase2/3完成门审计；具体单一步骤以canonical任务书末尾为准。Phase5仍pending，不得提前宣告全验收。

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
