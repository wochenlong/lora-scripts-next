# 阶段 0：契约收敛与统一 LLM 长程任务书

## 目标

将现有实现和计划从旧 mode-first/combined 设计收敛到 Issue #409 的 model-first、capability-driven 契约。

## 任务

1. 记录 Issue #409、当前 commit、工作区和现有实现差异。
2. 从首版 UI/API/验收中移除 combined/mixed 创建和 Agent/plugin 范围。
3. 冻结 runtime、model、capability、output、user_data caption preset schema。
4. 审计统一 LLM、旧翻译 API、旧 `/api/interrogate` 和 API 动态入口。
5. 形成保留/迁移/删除/历史兼容表。

## 完成门

canonical design/task/goal/manifest/targets/checklists 一致；没有首版 combined/mixed 入口或 Agent 依赖；preset 与训练预设隔离方案可执行；差异表和 failure report 已归档。

## 验证与证据

文档一致性搜索、schema review、git diff review；证据写入 `phase-0-contract-alignment/`。
