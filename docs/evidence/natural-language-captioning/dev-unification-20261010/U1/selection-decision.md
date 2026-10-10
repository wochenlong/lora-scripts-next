# U1 默认模型指定与授权边界

2026-10-11用户明确：无需进一步测试，直接选定Qwen3.5-2B。默认锁定Unsloth社区Q4_K_M主GGUF与同revision F16 mmproj，runtime b11327；这是用户指定模型，不是执行者A/B实测获胜。完整身份见user-selection.json。

AC-U1调整为pass_user_selected_with_probe_waived，解锁U2；原6图×3/12翻译选型质量、RSS和p95比较未运行，也不声称通过。已冻结fixture可用于后续功能验收。两候选下载session57383已停止，未启动模型或推理；已下载的本任务资产/part保留。新默认资产只下载Qwen3.5-2B至nl-caption-selected-qwen35-assets-20261011。

U4/U5的安装、真实视觉打标与翻译、严格JSON/真实语言、共享进程/有界队列、取消不写盘与从零重建均保留；最终所有功能验收通过和新沙盒交付才关闭goal。旧探针脚本仅归档到workspace/tools/nl-caption-u1-20261011，不作为产品代码或成功证据。
