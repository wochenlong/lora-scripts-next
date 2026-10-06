# 风险与授权治理

| 风险 | 等级 | 控制 |
| --- | --- | --- |
| 远程外发图片 | P0 | 显式远程 profile、隐私提示、压缩 data URL、无路径 |
| API Key 泄露 | P0 | 后端掩码、日志扫描、不可入 Git |
| mixed caption 被清理 | P0 | caption_format 门禁和原文测试 |
| text-only profile 执行 vision | P1 | capability contract、API 409、前端过滤 |
| 本地模型内存过高 | P1 | asset metadata、启动前资源提示、取消 |
| LLM 输出幻觉 | P1 | 固定 prompt、JSON schema、EDD、人工抽检 |
| 旧 API 回归 | P1 | gray regression 和 compatibility facade |

涉及新的外发 provider、文件格式改变、并发模型、训练输入语义或删除/恢复用户 caption 时，必须先写 change record 并重新跑相关 gate。
