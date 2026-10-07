# 恢复报告与短自然语言来源保护失败记录

Status：resolved（源码、相关回归和实际浏览器复验通过）。Phase2整体完成门仍待最终核销。

1. 实际重启后历史报告没有显示中断原因：后端recovery item没有code，前端仅在item.code存在时显示error。修复新增caption_interrupted，并让前端兼容旧无code报告；实际旧报告三行原因可见。
2. 新增断言首次误放在“已结束的部分失败”用例，得到1 failed/21 passed；移到“pending任务重启”用例并验证persisted state code，最终22 passed/2 warnings/2.31s。此失败不是功能通过证据。
3. 外部修改已生成natural/mixed使hash失效，短词可能被当Tag：store对曾为non-tag但被外部修改的现存文件返回unknown/空tags，拒绝危险清理。不存在的caption不受此保守提示阻挡。
4. 实际API已返回unknown时，浏览器仍显示猫的Tag芯片：DatasetEditorPage重新启发式检测而忽略server caption_format。修复编辑格式和Tag投影遵循已有来源，mixed使用实际训练Tags，draft/filter/translation列表不拆短natural。真实UI复验：unknown和已保存natural“猫”均显示原文保护提示，无删除Tag按钮。

复验：编辑器/持久任务/Tag灰度54 passed；最后相关后端229 passed/4 warnings/22.53s，Node22 check328 tests/51 files/13.11s，typecheck/lint/build通过（2个已有Lint warning；build1868 modules/5.34s）。未豁免原始失败。完整回归、真实模型、EDD、正式启动和Phase4仍未完成。
