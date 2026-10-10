# 证据治理入口

[预检](preflight-source-review.md)区分当前事实与未验证假设；[测试治理](testing-and-evidence-governance.md)定义证据与资源限额；[授权](risk-and-authorization-governance.md)约束范围；[变更控制](change-control-governance.md)防止降门。

规划门见[gate清单](gate-validation-checklist.md)，执行门在U0–U6任务书。失败、探针、完成、清理均使用本目录模板。机器核查结果记入`plan-validation.json`，它只验证文档，不作为模型/业务测试证据。

`dev-ui-and-local-qwen-analysis.md`与`merge-tree-summary.json`是上一轮只读分析的原样归档，分析中的“建议另建适配分支”等路径选择以本次用户锁定的最终`feat/NL-Captioning`为准。
