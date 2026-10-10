# Plan manifest

- Plan ID：`DATASET-NL-DEV-UNIFICATION-20261010`
- Version：`1.0`
- Last updated：2026-10-10 Asia/Shanghai
- Scale mode：Full；目标T1–T7合并为一份完整实施验收设计，七个阶段任务与开工清单独立。
- Mode：replan with continuity（保留历史的增量重规划）
- Canonical progress：[原主任务书](../natural-language-captioning-task-book.md)，唯一执行台账
- Current branch：`feat/NL-Captioning`
- Current active phase：U0 pending，全部AC-U0…6 unrun
- Execution readiness：`drafting`（文档定稿、施工按用户要求暂停；等待明确启动）
- Planning review：`pass-with-boundary`，新模型验证安排在U0之后U1，没有免测
- Design：[设计增量](../../design/nl-caption-dev-unification-design.md)
- Goal：[全程执行提示词](03_goal提示词/最新dev适配与Qwen统一_goal提示词.md)
- Evidence root：`docs/evidence/natural-language-captioning/dev-unification-20261010/`（未来执行写入，当前未创建执行结果）
- Next action：交付长程任务书与goal，保持施工暂停，等待明确启动。
- Close rule：全部AC门pass且最终沙盒就绪后关闭，user_manual_acceptance=pending_followup。

## Artifact manifest

以下相对路径为完整产物索引；进度不在此重复维护。

| Artifact | Role |
|---|---|
| `00_总控目标索引.md` | 规划/规则/文档核查 |
| `00_预检证据/README.md` | 规划/规则/文档核查 |
| `00_预检证据/change-control-governance.md` | 规划/规则/文档核查 |
| `00_预检证据/dev-ui-and-local-qwen-analysis.md` | 归档分析证据 |
| `00_预检证据/evidence-cleanup-report-template.md` | 规划/规则/文档核查 |
| `00_预检证据/failure-report-template.md` | 规划/规则/文档核查 |
| `00_预检证据/feasibility-probe-report-template.md` | 规划/规则/文档核查 |
| `00_预检证据/gate-validation-checklist.md` | 规划/规则/文档核查 |
| `00_预检证据/merge-tree-summary.json` | 归档分析证据 |
| `00_预检证据/plan-validation.json` | 规划/规则/文档核查 |
| `00_预检证据/preflight-source-review.md` | 规划/规则/文档核查 |
| `00_预检证据/risk-and-authorization-governance.md` | 规划/规则/文档核查 |
| `00_预检证据/stage-completion-gate-template.md` | 规划/规则/文档核查 |
| `00_预检证据/testing-and-evidence-governance.md` | 规划/规则/文档核查 |
| `01_目标计划书/00_目标计划书索引.md` | 规划/规则/文档核查 |
| `01_目标计划书/01_适配与模型统一实施验收计划.md` | 规划/规则/文档核查 |
| `02_长程任务书/U0_本地合并与开发基线冻结.md` | 规划/规则/文档核查 |
| `02_长程任务书/U1_双用途模型探测与默认选型.md` | 规划/规则/文档核查 |
| `02_长程任务书/U2_共享LLM与配置预设迁移统一.md` | 规划/规则/文档核查 |
| `02_长程任务书/U3_最新dev打标与编辑UI完整适配.md` | 规划/规则/文档核查 |
| `02_长程任务书/U4_全量回归与真实链路审计.md` | 规划/规则/文档核查 |
| `02_长程任务书/U5_从零隔离重建真实验收.md` | 规划/规则/文档核查 |
| `02_长程任务书/U6_最终新沙盒启动与goal关闭.md` | 规划/规则/文档核查 |
| `03_goal提示词/最新dev适配与Qwen统一_goal提示词.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U0_本地合并与开发基线冻结_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U1_双用途模型探测与默认选型_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U2_共享LLM与配置预设迁移统一_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U3_最新dev打标与编辑UI完整适配_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U4_全量回归与真实链路审计_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U5_从零隔离重建真实验收_执行前清单.md` | 规划/规则/文档核查 |
| `04_阶段开工清单/U6_最终新沙盒启动与goal关闭_执行前清单.md` | 规划/规则/文档核查 |
| `05_最小可行性验证/minimal-feasibility-probe-plan.md` | 规划/规则/文档核查 |
| `06_开工前最终复盘报告.md` | 规划/规则/文档核查 |
| `README.md` | 规划/规则/文档核查 |
| `plan-manifest.md` | 规划/规则/文档核查 |

## Gate index

[规划GATE-00…14清单](00_预检证据/gate-validation-checklist.md)与[最终复盘](06_开工前最终复盘报告.md)只证明计划完整；执行AC-U0…6必须各自当前代码证据。用户暂停施工的最新指令优先于本包任何未来执行措辞。
