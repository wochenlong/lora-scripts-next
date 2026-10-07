# Plan Manifest

- Plan ID: DATASET-NL-TAGGING-20261006
- Version: v2.2-executing
- Scale mode: Full
- Readiness: executing（Phase 0/1/2 完成门通过；当前 Phase 3）
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

- 最新相关后端回归 241 passed；Node 22 前端完整 check：329 tests / 51 files passed，typecheck/lint/build 通过。共享设置/编辑器来源保护见 Phase 2 shared-settings-and-provenance 报告。Phase 0/1 核销分别见其 gate-review；本地真实批量明确复用 P1 资产。
- 宽范围回归仍有 11 failed、21 skipped；不得推进完整验证门。见 evidence 的 failure report。
- 凭据落实 goal 原有边界：后端进程内保存真实 Key，配置文件和响应只有掩码；后端重启需要重新注入。
- 连接测试直接测试所选 profile 并校验严格 JSON，不应用生产路由的 fallback。
- Phase 0/1/2 done；Phase 3 in progress；Phase 4 pending。唯一下一步：完成主测试矩阵复验并核销剩余失败、跳过和联网测试。

Phase2 gate-review已逐项核销；Phase3 frozen-eval-manifest/rubric/preflight/Phase4输入齐全，初始人工评分为空；当前六条均 20/20，见 human-evaluation-approval.json。全局GATE09/10仍未通过，无失败豁免。

Phase3回滚/清理已实现并测试，actual浏览器恢复2/冲突1、取消无变化、清理保留文件/来源通过。相关241后端/329前端。原11失败已恢复逐case：17项依赖/README/process复验通过，关闭其中7个；4个symlink仍因WinError1314等待用户权限环境，未豁免；完整矩阵/真实/EDD/正式启动/Phase4仍未完成。

## 2026-10-07 真实生产路径及人工评分同步

远程、本地和同时可用的 remote-first/显式 fallback 均通过当前生产路径验证；三样本严格 JSON、缓存零重复请求、预览不写盘通过。用户对最初 A/B 六条描述五维各给 4 分，每条 20/20，两组均满足冻结 rubric。精确文本哈希与评分范围见 phase-3-evaluation/human-evaluation-approval.json；路由后续不同文本不沿用评分。详见 2026-10-07-production-real-and-human-review.md。Phase3仍 in progress，Phase4 pending，完整矩阵及最终交付门未通过。

## 2026-10-07 Tag/combined、Zero-Short和矩阵增量

真实默认WD ONNX三图旧/新Tag逐字节相同（13/11/8 Tags、8.366s）；实际WD+Qwen combined三图3/3、24.208s，mixed来源和actualTags正确，缓存3命中零LLM请求、preview零写盘、模型已停止。正式FastAPI lifespan=on和新Node22 dist已通过空配置/无Key/无词库/无视觉模型启动；API健康与桌面/390px页面可用，安装/配置入口、默认禁用fallback/生成均核对。证据见phase-3-evaluation/2026-10-07-real-tag-combined-zero-short.md，不属于Phase4。

主tests收集1503项；分区运行1467 passed/11 failed/25 skipped/1 deselected/77 subtests/308.42s。排除的唯一联网ModelScope tokenizer测试实际下载整个模型仓库，已停止并保留pending，未豁免。11失败中的7项已修复：任务维护测试不再向sys.modules泄漏Tagger替身，LyCORIS fake工厂允许可选导入缺失；相关55 passed/7.50s。另4项Windows symlink权限未解决。修复后的分区复验实际1474 passed/4 failed/25 skipped/1 deselected/77 subtests，306.54秒；仅4个Windows symlink失败。被排除的ModelScope项在独立7项真实组中通过，完整组合运行仍待复验；25项skip逐案审计/授权尚未核销。

DiffSynth Windows fixture改为稀疏标志+末字节seek/write，保留逻辑长度与模型header，13 passed/2.80s。初次truncate产生的测试文件清理被自动审批拒绝（仅blocked by policy），保留未复用，最终清理待核销。自建正式UI和模型进程停止，浏览器about:blank。

使用/维护说明已补充docs/natural-language-captioning-usage.md。Phase3仍in progress，Phase4 pending，goal未完成。当前唯一下一步：完成主测试矩阵复验并核销剩余失败、跳过和联网测试。
