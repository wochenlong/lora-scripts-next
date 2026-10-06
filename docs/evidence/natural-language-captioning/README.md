# 自然语言打标证据根目录

本目录只保存可审计的摘要、命令日志、环境版本、样本 hash、模型/profile/prompt revision、测试结果、失败报告和清理报告。

禁止写入：

- API Key、Authorization、完整请求头；
- 用户原图、完整远程原始响应和本地绝对路径；
- 模型二进制、llama.cpp runtime、node_modules、Python 虚拟环境和缓存；
- 未脱敏的数据集名称或其他私人信息。

阶段证据按以下目录归档：

- phase-0-llm/
- phase-1-vision-job/
- phase-2-frontend-editor/
- phase-3-evaluation-release/
- phase-4-isolated-rebuild/

Phase 4 证据必须证明其使用了全新 worktree、全新依赖、全新配置和全新测试输出，并包含最终清理报告。
