# Phase 2：报告、轮询与编辑器冲突保护增量

基线 eb93de4；阶段仍 in progress。本报告不代替完整浏览器业务、真实评测或从零重建验收。

## 已实现

- TaggerPage 历史任务列表、恢复提示、失败重试和报告：呈现逐项状态、实际 profile、缓存、prompt revision 和 before/after hash；不展示私有计划/路径或原始响应。
- 抽出 useTaggerJob、useLlmProfiles、CaptionPromptEditor、CaptionJobProgress。请求单飞、AbortController、代次隔离、离页取消，以及取消任务后旧轮询不能反写状态；报告只接受最新选择。
- natural 模式隐藏 Tag 清理和分级选项；窄屏进度按钮改为正常文档流，历史与按钮不重叠；本地/任务状态中文化，安装进度使用 MiB。
- Dataset Editor 批量请求携带扫描 hash，整批验证后才写入；兼容旧客户端不传 hash，但写前仍捕获冻结快照并校验。文件逐个采用 atomic/before hash。
- undo/redo 校验对应事务另一侧 hash，外部修改或删除返回 caption_conflict；失败不提前弹出历史。中途冲突时已成功和剩余部分分开保留历史，半批操作仍能撤销。
- 快照由单次原始字节读取计算 hash，恢复保留 Tag/natural/mixed 的空白及 CRLF。清理型操作仍拒绝 natural/mixed。

## 实际命令及结果

Python 3.11.15，运行时为 workspace/sandboxes/nl-caption-runtime-20261006/.venv：

```powershell
& <runtime-python> -m pytest tests/test_dataset_caption_provenance.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py -q
& <runtime-python> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
npm exec --yes --package=node@22.17.1 -- node 'I:\NdoeJS\node_modules\npm\bin\npm-cli.js' --prefix frontend run check
```

- 编辑器定向最终 35 passed / 4 warnings / 3.05s；相关后端最终 218 passed / 4 warnings / 19.05s。
- 前端最终 51 files / 321 tests passed / 20.67s；typecheck、lint、build 均通过；lint 两个已有 EngineStatusBar 警告；Vite 1866 modules / 8.15s。构建有已有 Rollup annotation/chunk 提示。
- 增加 11 个后端场景：undo/redo × 修改/删除、整批陈旧 hash、半批竞态、逐字节 Tag 恢复、整批 undo 预检、部分 undo 历史、创建后的外部替换、mixed 恢复。前端新增 8 场景覆盖报告、恢复、轮询和配置加载生命周期。

## 真实浏览器检查及边界

实际 Vue + FastAPI 开发服务：127.0.0.1:5176 / 28761。独立空配置根为 workspace/sandboxes/nl-caption-browser-20261007；测试进程显式允许这两个 host/origin。FastAPI lifespan=off，仅验证 Phase 2 页面，不证明正式启动或 Zero-Short。

- 桌面 1440×1000：document scrollWidth 1425；窄屏 390×844：375，无横向溢出。
- 空 profiles 时预览/批量禁用，可打开共享管理，隐私和可选本地提示可见，未触发模型下载。
- 共享对话框窄屏宽 374.39；增加未填写草稿、触发校验、Escape 关闭后后端仍 profiles=0。未注入真实凭据。
- 窄屏修正后按钮 position=static，范围 y2086.5–2179.5，历史始于 y2203.5，互不重叠。
- 使用正确测试 allowlist 后页面 console 0 errors / 0 warnings；此前自定义端口 bootstrap 403 和服务切换 ECONNREFUSED 记录为测试环境诊断，未修改生产安全配置。
- 修正后截图：sandbox 的 natural-desktop-fixed.png、natural-narrow-fixed.png。修正前截图不能用于证明最终布局。
- 本轮两个自建服务已停止；截图和空配置不入 Git。未执行真实提供方连接、预览写回、取消/重试完整浏览器链路，不能声称人工验收完成。

## 尚待完成

共享本地资源管理完整复用、translation cache 配置兑现、安全任务回滚/清理、完整浏览器业务矩阵；Phase 3 真实远程/ONNX/EDD、完整回归失败闭环；Phase 4 新依赖/资产/配置/cache 从零重建。宽范围 11 failed / 21 skipped 和训练 collection errors 未获豁免。
