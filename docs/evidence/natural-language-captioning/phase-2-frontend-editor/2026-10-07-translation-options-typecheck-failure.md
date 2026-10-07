# 前端翻译选项类型检查失败记录

Status：resolved。修复后完整 Node22 check 重跑通过（325 tests / 51 files；typecheck/lint/build pass）。Phase2 完成门未通过，无豁免。

- 基线：25e954b，增量 shared translation prompt/reasoning UI。
- 实际命令：Node22.17.1 `npm --prefix frontend run check`。
- 失败：vue-tsc TS2322，LlmSettingsDialog.vue textarea 的 value 从 Record<string, unknown> metadata 推导为未知对象类型，不能绑定文本值；exit1，后续lint/test/build未执行。
- 根因：模板没有把已由后端校验的 metadata 字段显式转换为字符串。组件Vitest不代替静态类型检查。
- 修复：textarea/select 使用String(field ?? default)，保留空字符串和default语义；后端限制translation_system_prompt为string≤20000，reasoning_effort为disabled/high/max，并拒绝object/array。
- 风险：未修改caption提示词；仅旧翻译选项共享编辑。不得将第一次失败check计为通过。
- 复验：Node22.17.1 check退出0；Vitest325 passed / 20.56s，build1868 modules / 8.24s。未新增Lint warning。
- Next action：实际浏览器重启恢复和历史选择验收。
