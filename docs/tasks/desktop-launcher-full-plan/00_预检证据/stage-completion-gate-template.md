# 阶段完成门模板

> 复制到外部证据根 `M<阶段>/stage-completion.md`；本模板不是已通过记录。唯一阶段进度写回[总控](../00_总控目标索引.md)，Git操作统一[Git基线治理](git-baseline-governance.md)。

当前修订0.2：[CR-001](change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)列明的资源受限GPU子项由用户授权skip，不计pass；其他未豁免必测仍完整执行。复制本模板时保留逐case豁免及未验证能力，不能只写总结果pass。

## 1. 身份与结论

- Plan ID：`desktop-launcher-full-20261028`；计划版本/规格摘要：待填。
- 阶段稳定名/目标/执行授权来源：待填。
- run-id、host-id、代码commit、dirty diff摘要：待填。
- 交付包路径/SHA256、受限测试配置摘要/启用参数、配方/模型/数据摘要：待填。
- 开始/结束UTC时间：待填。
- 结论：`pending | pass | pass-with-boundary | fail | blocked`，默认pending。
- 本结论适用范围及明确未证明内容：待填。

## 2. 开工与测试核对

| 硬门 | 证据 | 结果 |
| --- | --- | --- |
| 对应阶段清单与上一阶段完成门 | 待填 | pending |
| D1–D6及资源授权范围 | 待填 | pending |
| Git基线、保存无关改动、禁止夹带 | 待填 | pending |
| 单元测试及真实失败定位能力 | 待填 | pending |
| 合同测试/版本兼容/错误码 | 待填 | pending |
| 集成与故障注入 | 待填 | pending |
| gray新旧路径/资料/回滚对照 | 待填 | pending |
| real原生UI、下载、API/子进程或GPU | 待填 | pending |
| Zero-Short阶段专属入口条件 | 待填 | pending |
| 无目标外资料变化、无外部进程误杀 | 待填 | pending |
| 网络/GPU/磁盘累计与高水位未超限 | 待填 | pending |
| 失败原始日志和修复后独立attempt | 待填 | pending |
| 清理预览、实际清理和保留材料 | 待填 | pending |
| 阶段提交/push和ls-remote身份校验 | 待填 | pending |

测试逐项链接到 `result.json` 和原始输出，写出命令、参数、机器/制品身份和实际结果。不适用项需原因和替代证据，不能空白。CR-001指定skip逐项列`case_id/waiver_id/user_source/resource_reason/未证明能力`，允许完成调整后的阶段并给pass-with-boundary。其他P0/P1未解决或未豁免必测未过不得pass。

## 3. 资源账本与风险

填写本阶段/全计划累计网络字节（含失败）、GPU秒数、同引擎失败重试计数、E新增字节/F峰值、两卷最小剩余空间。列出P0/P1/P2/P3、问题归属、修复证据、剩余限制与变更单；预算缺测为unknown，不写0。

## 4. M6追加硬门

必须链接 A1–A10 逐子项联合矩阵；干净Windows OS/VM的无Python/uv/训练器/缓存且缺WebView2基线；独立根四引擎从零安装/修复及未豁免GPU/权重证据，CR-001指定skip另列；同一最终交付包SHA；所有重建后的受影响用例复验；壳更新故障/精确状态恢复；迁移合成源/外部sentinel保留；关窗后的进程/端口及外部服务保留。

A4/A8须最终同一二进制实测；允许只读受限测试配置仅在新标记沙盒显式启用，配置摘要/默认生产根未变/默认模式拒绝测试信任的证据齐备。另SHA测试构建不抵扣；无可审核同二进制测试通路且无生产资源即blocked，D5内置清单+手动升级不构成豁免。

M6允许仅含CR-001明确批准的GPU skip后声明“完成（含GPU验收边界）”，不得宣称四引擎GPU全通过。其余必测unknown/not-run/skip、缺干净OS/未豁免GPU或合法资产/预算时仍blocked/fail；M2/M3旧证据不能抵扣M6重新从零。

## 5. 解锁与写回

记录“本阶段回答了什么问题、为何下一阶段现在可开始”、对应证据摘要，以及唯一下一步。完成外部证据后更新总控与manifest中的证据链接和状态，不另建竞争性总体进度。最终完成还要求最终报告、M6提交/push和远端分支头校验；本轮文档生成不执行这些动作。
