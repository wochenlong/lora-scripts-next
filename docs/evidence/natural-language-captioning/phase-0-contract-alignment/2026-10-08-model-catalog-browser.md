# 2026-10-08 模型优先页面、能力契约与浏览器验证

基线 c599835；本轮为 Issue #409 的持续施工，不是最终验收。

## 实现

- 新 GET /api/tagger/models：后端权威模型目录，保持10个旧Tag模型ID；按WD、CL、Qwen-VL和Vision LLM系列归类；只通过本地文件/Hub缓存查询已下载状态，不进行下载；text-only Profile不进入Caption目录；返回支持字段、语言、runtime、output、ready和profile引用，不返回Key/endpoint。
- TaggerPage一级本地模型/API服务，API没有ready模型时不显示入口。根据模型output显示Tag或Caption；具体型号、作者、系列折叠、原名搜索、下载/就绪状态。模型切换保存各自草稿，Caption请求不携带WD字段。
- Caption参数含max_tokens、temperature及提示词，进入实际preview/batch调用、cache revision和持久任务快照；runtime/model_id/profile_id必须匹配并具vision能力。
- API拒绝Caption的Tag参数、追加/前置及混合布局；旧Tag request也拒绝Caption专属字段。默认跳过，copy为明确覆盖。
- manager.start及retry拒绝历史combined重新执行，删除任务worker中Tag+Caption串联和mixed生成分支；历史记录查看、回滚及Editor来源防护保留。
- retry先核对before hash再跳过，外部修改仍报告caption_conflict，不静默把冲突算成功。
- 浏览器fixture的新user_data root隔离，防止写入开发树用户预设。

## 验证

相关后端最终定向矩阵216 passed/4既有依赖warning/20.87秒，范围为tests/test_caption*.py、test_llm*.py、test_tagger*.py、test_local_vision*.py、test_vision_service.py、test_dataset_caption*.py。此结果不是全仓最终矩阵。

前端Node22完整check：336 tests/52 files，typecheck/lint/build通过；2项既有EngineStatusBar warning，构建8.37/9.84秒记录为迭代过程，最终构建9.84秒；VueUse注释和chunk提示保持已知状态。

实际浏览器：使用新的独立fake fixture，正式源码构建的dist与实际FastAPI API，lifespan=off；3张合成非敏感样本；没有真实LLM或Key。这是业务验收，不是Real/Zero-Short/Phase5。

- 修复真实KeepAlive初始化时序：mounted请求曾在activated中被失效并丢弃，模型目录为空；现在mounted微任务与activated共享同一generation，添加KeepAlive回归。测试新增时发现旧status mock未返回数据，同步完善真实响应fixture；最终336通过。
- 默认本地具体WD型号正确；API点击后选择fixture-vision，text-only不可选；自然语言页无append选项。
- 单图试标输出可见；此时文件系统caption计数0，证明试标无写盘。
- 批量真实API状态/持久history证明3/3写回，零失败；重复两次3/3跳过，provider request总数保持4（1次preview+3次batch），不重复收费。
- 首次浏览器脚本使用async waitForFunction导致Promise被当作truthy，读到了非终态计数；这些中间结果不用于验收。改为有界明确轮询并核对持久history，终态done/current3/success3及skip3已核实。
- 390px：document scrollWidth375，无横向溢出；formBottom与statusTop均1943px，证明任务区在底部；主操作宽327px；缺失Qwen显示安装入口且生成禁用。Qwen原始型号搜索及具体型号摘要正常。
- 浏览器console零error。浏览器已about:blank，本轮自己启动的fake server已停止；tracked dist恢复基线，不提交构建产物。

## 回归调整与未完成项

旧combined成功测试改为四种layout均在provider/写回前被拒绝；原append崩溃恢复测试改为明确copy覆盖后的crash恢复，继续验证无重复推理和原子写回。维护/rollback测试明确选择覆盖，而不依赖旧默认覆盖行为。Tag旧四种conflict action仍逐字节灰度通过。

仍需：user_data预设多文件事务/跨进程保存、显式导入UI、系统提示词编辑完善、user_data/tasks与既有任务体系联动、Tag单图试标、完整模型专属参数/保存失败保护、实际预设跨浏览器及刷新测试；最终全测试、真实模型、正式空配置lifespan和Phase5从零重建。

单一下一步：补齐user_data预设存储的多文件失败恢复和跨进程修订保护，再接入显式导入UI。Goal active；不将局部通过当完整交付。
