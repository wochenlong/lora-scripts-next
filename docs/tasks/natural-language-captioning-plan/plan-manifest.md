# Plan Manifest

- Plan ID: DATASET-NL-TAGGING-20261006
- Version: v2.0-preflight-audit
- Scale mode: Full
- Readiness: drafting（等待用户最终 goal 提示词）
- Canonical progress: ../natural-language-captioning-task-book.md
- Design source: ../../design/natural-language-captioning-tagging-design.md
- Evidence root: ../../evidence/natural-language-captioning/

## Artifact manifest

| Artifact | Status | Purpose |
| --- | --- | --- |
| 00_总控目标索引.md | done | 总目标、范围、阶段门 |
| 00_预检证据/ | done | 测试、授权、失败和变更治理 |
| 01_目标计划书/ | done | 可验收目标和测试矩阵 |
| 02_长程任务书/ | done | 分阶段执行步骤 |
| 03_goal提示词/ | done | 新会话可直接执行的 goal |
| 04_阶段开工清单/ | done | 每阶段硬门槛 |
| 05_最小可行性验证/ | done | P1 已执行证据和后续探针 |
| 06_开工前最终复盘报告.md | updated | 审计后开工边界 |
| 07_设计与任务书审计及开工准备报告.md | done | 第二轮审计、完整交付要求和待启动条件 |

## Gate status

- GATE-00 preflight: pass-with-boundary
- GATE-01 goal: pass
- GATE-02 evidence governance: pass
- GATE-03 target plans: pass
- GATE-04 task books: pass
- GATE-05 checklists: pass
- GATE-06 feasibility: pass-with-boundary
- GATE-07 goal prompt: pass
- GATE-08 final review: pass-with-boundary
- GATE-09 full implementation and complete verification: in progress
- GATE-10 isolated rebuild from zero and final acceptance: pending execution

## Change control

任何配置 schema、远程优先策略、vision capability、caption 文件格式、API contract、并发模型、测试阈值、隔离重建步骤或最终完成门变化，都必须更新 manifest、canonical task book、设计书和受影响的 gate。
