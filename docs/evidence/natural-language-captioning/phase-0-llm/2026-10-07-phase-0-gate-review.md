# Phase 0 完成门复审

结论：Phase 0 done，统一 LLM 阶段相关契约/兼容门通过。GATE-09 完整实现与验证仍为 in progress，GATE-10 隔离重建为 pending；不将本阶段完成推导为完整交付完成。

## 逐项核销

| 完成条件 | 实际证据 | 结论 |
| --- | --- | --- |
| v4→v5、迁移幂等、掩码/修订 | llm contracts、unified store、runtime secrets；原子配置写入失败回滚；损坏配置返回可操作错误且不覆盖 | pass |
| 翻译 text、caption vision、语言限制 | capability/route tests、text-only 拒绝、语言配置校验与前端筛选 | pass |
| remote-first、显式 local fallback | 实际 HTTP fake vision provider；默认关闭的 text/vision fallback；legacy translation 显式开关 | pass |
| 精确连接测试 | 指定 local 不改走 remote；严格成功 JSON、截断/非法/重复字段拒绝；失败不转 fallback | pass |
| 凭据与传输隐私 | 进程内注入、配置/响应只有掩码、重启后无真实 Key、旧明文迁移、data URL 无本地路径、预览错误脱敏 | pass |
| 旧翻译与统一 facade 灰度 | 同一个真实 HTTP fake text provider 对比迁移前/后 facade 和统一服务，路由/凭据/翻译结果一致 | pass |
| 旧 API 兼容 | 旧 /api/interrogate 接受原 Tag 表单及 busy fail envelope；旧翻译 GET/PUT 掩码一致；remote 选择不停止其他功能共享的 runtime | pass |
| 共享受管本地可用性基础 | revision/SHA 双文件校验和管理单元测试；三公开样本真实受管启动、推理、取消、再请求和停止（复用 P1 资产） | pass-with-boundary |

最后一项属于开发验证，完整安装/HTTP/UI/真实写回/EDD/Phase 4 仍由后续阶段负责。翻译旧 `llm_mode=local` 在新 facade 表示显式启用本地兜底，远程仍优先；原 API 字段和 envelope 保留，但取消旧的“选择远程就停止共享模型”副作用，以落实已锁定的共享运行时决策。

## 最新实际回归

Python 3.11.15 venv 中执行：

```powershell
& <runtime-python> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
```

结果：168 passed，4 个已有依赖 warning，5.58s。此前相关 160/165、中间兼容 suite 62 和配置 suite 54 为修复过程的实际记录，最新结果覆盖这些改动。Node 22 前端 check 最新结果为 307 tests / 48 files passed，typecheck/lint/build 通过；原有 lint 2 warning。

宽范围 11 failed / 21 skipped 和训练 collection errors 未被此阶段豁免。它们仍保留为完整矩阵开放项，必须在最终完整验证和干净重建中闭环。

## 下一阶段

正式进入 Phase 1，保持当前 API 的 flat request 与 job status/report envelope；需要补持久快照/报告、恢复、组合预览、完整 fake 错误矩阵与真实写回。具体下一步：实现并验证任务报告持久化和服务重启后的恢复边界。
