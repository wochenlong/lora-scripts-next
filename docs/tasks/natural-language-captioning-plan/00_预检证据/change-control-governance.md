# 变更控制

变更记录必须包含：原决策、拟议变化、原因和证据、影响阶段、风险等级、受影响 API/数据/安全边界、替代验证、授权状态、下一步动作。

必须触发变更控制的情况：

- remote-first 改为 local-first；
- translation/caption profile schema 改变；
- vision capability 判定改变；
- caption 写回格式或历史 mixed 兼容解析改变；首版不得新增 mixed 输出；
- 增加模型下载或外发 provider；
- 放宽 API Key/路径/图片日志策略；
- 跳过计划测试或降低 EDD 阈值。

