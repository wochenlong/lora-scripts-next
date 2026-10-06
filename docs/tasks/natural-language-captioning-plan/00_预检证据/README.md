# 预检证据与治理

P1 已完成并记录在 docs/tasks/natural-language-captioning-feasibility-probe.md。后续每个阶段都必须把命令、输入、环境、结果和证据路径写入 canonical task book 或阶段报告。

硬性边界：

- 远程优先，本地兜底；
- translation 不需要 vision，caption/combined 必须 vision；
- API Key 不落盘；
- 真实远程调用只用脱敏样本；
- 证据不进入 Git；
- 取消和失败必须保留失败样本。
