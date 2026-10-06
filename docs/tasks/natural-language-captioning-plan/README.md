# 自然语言打标施工计划

这是 DATASET-NL-TAGGING-20261006 的 Full Mode 施工计划体系。唯一进度源是上级任务书：

docs/tasks/natural-language-captioning-task-book.md

本目录包含总控目标、证据治理、目标计划、阶段任务书、goal 提示词、阶段开工清单、可行性探针计划和开工前复盘。实现必须逐阶段更新任务书和 manifest，不得只更新聊天摘要。

## 当前状态

- Execution readiness: drafting（等待用户最终 goal 提示词）
- Current branch: feat/NL-Captioning
- Current phase: 开工前审计完成，等待 goal
- Remote priority: locked
- Caption vision requirement: locked
- Local fallback: Qwen3-VL-2B candidate, locked after P1 probe
- Final delivery gate: Phase 4 — 隔离重建与从零真实验收
- Next action: 等待用户发送最终 goal 提示词；收到后从 Phase 0 开始，直至 Phase 4 通过
