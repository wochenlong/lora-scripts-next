# Issue #409 任务归档与既有任务页联动

2026-10-08；源码父提交 e17bdd6。本记录为真实源码/API/浏览器与受控 fake 模型验证，不是实际模型或从零重建验收。

CaptionJobStore 继续负责执行与恢复；CaptionTaskBridge 将状态投影到既有 TaskManager maintenance lane，不增加调度器。新任务先写 user_data/tasks/dataset-tagger/日期/时间_UUID/config.json 与 task.json，然后持久化 SQLite，成功后才启动推理。档案包含冻结提示词、系统提示词、生成参数、模型身份/修订及逐文件结果；只用白名单配置，不包含 Profile 凭证。公开任务列表不包含数据集路径或原始提示词。任务日志只记录阶段与计数。

任务页可停止真实异步推理、查看打标报告、只重试失败项；历史任务重试读取原任务配置，不使用后来任务的提示词。TaskManager 删除隐藏档案投影，不删除图片、标注、模型或冻结 config；重启不会复活被删除记录。Caption 历史删除同步隐藏投影。恢复不自动启动推理，未完成任务转失败，明确重试后才生成。路径约束拒绝符号链接/junction 和越界档案。

验证结果：

- 相关 Caption/LLM/Tagger/Editor/Task 后端回归：296 passed，4 个既有 warning；模型快照增量后的 API/failure/bridge：39 passed，2 warning。
- 新桥接专项：10 passed，含实际异步取消、初始归档失败/SQLite 失败零推理、旧任务取消不影响新任务、恢复参数、历史重试、损坏 task.json 备份恢复、删除后不复活。
- Node 22 完整 check：340 tests / 52 files；typecheck、lint、生产构建通过，2 个既有 EngineStatusBar lint warning。
- 实际浏览器使用新 fake fixture：首批三图成功；单图延迟推理从任务页停止，cancelled=1/succeeded=0，零 txt 写回；任务报告链接打开对应 UUID。
- 两次受控 429 耗尽请求重试后：两图成功1/失败1；从任务页仅重试失败项，新任务 total=1/succeeded=1、额外 provider 请求=1，原 max_tokens=223 保留，parent_job_id 正确。
- 服务重启：5 条历史状态及完成时间保持，provider requests=0。删除其中一条终态记录后再次重启，只恢复4条，删除记录不复活，原图片/txt 字节保持。测试请求曾误用 fixture 的 /control 和 /state（404），改用 /__fixture/state 后实测 requests=0；不把404当证据。

剩余：Tag 页面尚走旧 /interrogate，Tag 单图预览尚需统一接通；本批不能称所有模型任务完成。真实模型、正式 lifespan Zero-Short、最终矩阵和全新隔离重建仍待执行。Agent/plugin 接口未修改。
