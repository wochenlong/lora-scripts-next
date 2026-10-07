# Plan Manifest

- Plan ID: DATASET-NL-TAGGING-20261006
- Version: v2.2-executing
- Scale mode: Full
- Readiness: executing（Phase 0/1 完成门通过；当前 Phase 2）
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

## 2026-10-07 执行同步

- 最新相关后端回归 226 passed；Node 22 前端完整 check：325 tests / 51 files passed，typecheck/lint/build 通过。共享设置/编辑器来源保护见 Phase 2 shared-settings-and-provenance 报告。Phase 0/1 核销分别见其 gate-review；本地真实批量明确复用 P1 资产。
- 宽范围回归仍有 11 failed、21 skipped；不得推进完整验证门。见 evidence 的 failure report。
- 凭据落实 goal 原有边界：后端进程内保存真实 Key，配置文件和响应只有掩码；后端重启需要重新注入。
- 连接测试直接测试所选 profile 并校验严格 JSON，不应用生产路由的 fallback。
- Phase 0/1 done；Phase 2 in progress；Phase 3/4 pending。唯一下一步：实际浏览器重启恢复与历史选择验收。

2026-10-07 共享资产/cache和浏览器业务增量：相关后端221+最后本地管理定向16通过，Node22 check324；真实Vue+API/fake模型完成预览不写、自然/组合批量、429部分失败重试、取消、报告、mixed原文save/undo/redo和外部冲突。translation共享text连接/窄屏/Tab/Escape部分通过。初始fixture继承auto偏好触发词库下载后已取消，r2将词库/MyMemory也替换，实际HTTP验证无下载。不是实际模型或Phase4，完整gate仍pending。见phase-2-frontend-editor/2026-10-07-shared-assets-cache-browser-flow.md。

翻译选项兼容增量已验证：迁移/共享及旧API双向保存、revision、managed restart保留metadata，浏览器profile新增/删除/取消/能力/语言过滤和翻译选项保存均通过；相关后端226、Node22 check325。首次typecheck失败已修复并复验，见Phase2 translation-options failure/resolved报告。实际模型/正式启动/Phase4仍不由fake fixture替代。
