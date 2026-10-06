# 测试与证据治理

## 必测族

- Unit: profile migration, capability routing, prompt, cache key, formatter, caption format, atomic writer.
- Contract: all new API schemas, old translation APIs, old interrogate compatibility, masked secrets.
- Integration: fake OpenAI-compatible text/vision server, remote-first fallback, local readiness, job cancellation.
- Gray: old Tag path versus mode=tag; old translation facade versus unified LLM service.
- Real: SiliconFlow three-image JSON and Qwen3-VL-2B three-image CPU probe; later low-limit real dataset.
- Zero-Short: empty model/key/dictionary state starts safely and gives actionable setup.
- EDD: fixed samples, deterministic schema checks, human semantic rubric and failure preservation.
- Isolated rebuild: clean worktree, clean dependencies, clean config/cache, backend/frontend build and startup, real remote-first/local-fallback smoke, full test matrix, privacy scan and cleanup.

## Evidence format

每次验证记录命令、日期、commit、环境、输入样本 hash、模型/profile revision、结果、失败类型和输出路径。日志不得含 Key、完整请求头或本地绝对路径。

## 清理

模型和 runtime 只保留在 sandbox 或用户资产目录；探针结束后删除 sandbox。报告保留摘要和 hash，不复制图片和 API 原始响应。

隔离重建证据必须额外记录源 commit、环境版本、安装/构建命令、空配置结果、真实样本 hash、profile/prompt revision、写回前后 hash、清理结果和人工验收人。隔离目录删除后，主结论必须仍可由摘要、hash 和命令日志复核。
