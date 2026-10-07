# 共享设置与编辑器来源保护增量

基线 9f23e8c；Phase 2 in progress，不是完整前端/人工验收完成。

## 本批行为

- TaggerPage 与标签翻译设置均接入 `LlmSettingsDialog`，移除两处独立 profile 编辑表单，共用 profiles/routes/capability 和保存接口。
- 配置草稿独立于已保存配置；取消清空输入，重新打开重新读取后端掩码；保存只提交此编辑器拥有的 profiles/routes，避免覆盖并发修改的提示词预设。
- 翻译路由允许 text-only，caption 路由仅列 vision；连接测试针对已保存的选中 profile，修改后须先保存；vision 测试需要单图路径。
- 翻译界面的原 remote/local 互斥标签改为显式本地兜底复选框，仍保留既有本地安装控制。共享 vision 模型的 text readiness 可被翻译页面识别，不强制重复安装另一模型。
- caption_formats 扩展实际训练 Tags，并兼容旧表升级；编辑器用路径+当前 hash 查询生成来源，短自然语言不会被当作 Tag。caption-first mixed 使用实际 Tag 投影，不拆分自然短句。
- 自然语言保存/撤销保留原始空白和 CRLF；编辑器写回采用 atomic/before hash，前端把扫描 hash 发送到保存接口，外部修改返回 caption_conflict。

## 实际验证

独立 Python 3.11.15 venv 执行：

```powershell
& <runtime-python> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
```

结果 207 passed / 4 warnings / 29.40s；新增来源测试验证短 natural、caption-first mixed、陈旧扫描 hash 和旧 SQLite 表升级。此前定向来源/编辑器/任务回归 40 passed，翻译兼容回归 47 passed。

Node 22.17.1 执行 `npm --prefix frontend run check`：typecheck pass，lint 0 errors / 2 个已有 EngineStatusBar warning，Vitest 49 files / 313 tests passed（21.49s），Vite build 1860 modules（8.01s）。新增设置组件 4 场景，覆盖能力路由、取消/重新打开、保存边界和精确连接测试。测试 stub 的 prop type warning 已修复后重新执行完整 check；不将早期带该新增 warning 的结果当最终检查。

`git diff --check` 已通过。构建后恢复 tracked dist 基线，最终重建从源码生成；不手改产物。新文件只有源码/测试/脱敏证据，真实配置/数据库/模型/图片不入 Git。

## 尚待完成

历史报告与重启恢复 UI、轮询代次/重叠防护、提示词/进度组件抽取、本地资源管理完整复用、cache 控制和安全回滚/清理，以及桌面/窄屏/键盘/空配置/错误/隐私的真实浏览器验收仍待闭环。编辑器批量/undo/redo 的完整外部冲突矩阵亦需补验。Phase 3/4 尚未完成，宽范围 11 failed / 21 skipped 未获得豁免。
