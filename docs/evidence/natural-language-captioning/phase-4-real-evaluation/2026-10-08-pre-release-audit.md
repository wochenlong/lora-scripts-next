# 发布前范围、存储契约与重建输入审计

2026-10-08；业务基线f53582e，进度提交c5b0e5c。该报告不是最终交付签字。

已重新读取Issue #405：本功能的caption_prompt预设、settings默认引用、日期/UUID的任务档案、参数先落盘再启动、备份/修订、显式导入、删除保留图片/模型以及只归档新任务与其约定对应。端口仲裁、训练全局设置和Agent迁移不纳入本功能。凭据遵循用户更严格的运行时注入/磁盘掩码要求；当前没有API Key或远程Profile被注入本轮验收。

相对分支基线fc193789核对生产变更：Agent/plugin目录变更数0。app/__init__.py惰性导入是LLM数据集占用检查循环依赖修复，app/proxy.py移除弃用参数是启动兼容修复，app/api.py和tasks.py变更为既有任务页/队列联动，不能误认为新增Agent接口。

测试覆盖审计发现完整范围runner漏列test_local_text_registry.py，已加入EXTRA集合。该文件两项实际回归通过，覆盖纯文本模型只注册一次、拒绝伪造vision和视觉运行时保留翻译配置；后续完整运行必须包括它们，不能继续称旧51文件集合为最终完整集合。

phase5-frozen-inputs.json登记公开样本、许可证、SHA、Qwen/mmproj、runtime压缩包/可执行文件及ONNX/CSV的锁定来源。runtime压缩包SHA仅用于定义预期输入；Phase5须从公开URL重新下载并复核，不能链接或复制旧包。Python3.11.15、Node22.17.1以及所有新配置/缓存/输出规则已登记。尚未创建Phase5环境，execution_started=false。

输入清单复核修正了WD仓库名为实际注册表的SmilingWolf/wd-v1-4-convnextv2-tagger-v2。随后从公开Hub API确认Qwen与WD的固定revision真实存在，从GitHub release API确认b11327压缩包URL和发布SHA与冻结值一致。没有将尚未下载的Phase5资产记为已获取。

加入local_text_registry后的完整组合实际复验：52文件/515case，511通过/4相同Windows权限失败/0skip，17subtests通过；无新增失败。该集合替代先前遗漏两项的51文件集合，四项失败继续按原记录待用户决定环境口径。

剩余硬门：新UI火箭文本的人工评分、四个Windows权限测试的验收环境选择、包含local_text_registry的完整组合复验、Phase5本地从零真实验收、最终隐私和清理签字。前两项已发问，未答不视为批准；其余准备可继续。本轮不发布、不push，也不将旧combined/Agent证据作为完成门。
