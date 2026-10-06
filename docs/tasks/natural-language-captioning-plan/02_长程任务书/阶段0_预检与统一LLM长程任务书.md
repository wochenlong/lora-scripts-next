# 阶段 0：预检与统一 LLM

## Purpose

集中配置、能力、资产和路由复杂度，为翻译与视觉打标提供稳定公共 seam。

## 执行步骤

1. 在 feat/NL-Captioning 工作树记录初始 git 状态、源 commit 和本阶段 evidence 目录。
2. 新增统一 LLM contracts、profile v5、mask 和 revision。
3. 迁移现有 translation config/store/service 到 facade，保留旧 facade。
4. 实现 capability routing：translation=text；caption/combined=vision。
5. 实现 remote-first：远程可用优先，失败后按策略启用本地 fallback。
6. 注册 SiliconFlow remote profile contract 和 Qwen3-VL-2B local asset manifest，不把 Key 写入文件。
7. 建立 fake text/vision endpoint 和 migration fixtures。
8. 跑翻译、tagger、config、store 相关回归测试。

## 完成标准

- 旧 API 兼容；
- capability 和 route unit/contract pass；
- migration 幂等；
- remote-first/local-fallback 行为可模拟；
- 无 secret/path 日志；
- Phase 1 开工清单通过。

## Failure handling

迁移失败保留 v4 文件，停止进入 Phase 1；旧翻译 regression 失败时回到 facade adapter；远程优先策略不明确时阻止 UI 接线。

## Evidence

tests output、migration fixture、fake server transcript、git diff --check、task book update。
