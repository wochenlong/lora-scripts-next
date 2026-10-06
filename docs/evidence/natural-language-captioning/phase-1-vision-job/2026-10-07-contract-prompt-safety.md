# 契约、提示词与源图安全增量验证

此批次基于 426396f，仍不代表完整交付。最新相关 Python 3.11 回归为 160 passed / 4 warnings / 5.97s；最新 Node 22 完整 check 为 48 files / 307 tests passed。未豁免宽范围失败，未执行 Phase 4。

## 修复行为

- 配置保存校验 routes/cache/prompt preset 的类型、字段、长度、唯一 ID、语言和模板变量；拒绝无主机或非法端口的 endpoint、非法 metadata/secret revision；返回 HTTP 400，不产生部分配置文件。
- 空配置可以读取，提示词预设经过保存/再读取后保持一致，不触发模型下载。
- JSON 解析拒绝重复键（包括嵌套重复）与 NaN/Infinity；预览也拒绝 finish_reason=length 的截断结果，不将其当成功。
- 预览失败返回可操作通用消息，不回显提供方响应文本和本地路径。
- 原图 hash 在推理前捕获并用于缓存；推理后/写回前若原图变动，则报告 caption_conflict，禁止写回陈旧描述。JPEG 白底透明图转换规则对应新的 preprocessing revision v2，隔离旧预处理缓存。
- TaggerPage 新增命名提示词预设保存、选择、删除和撤销未保存编辑；按 vision 和目标语言双重过滤 profile；预览进行中禁止重复提交及同时开启批量。

## 实际运行命令

使用同一独立 Python 3.11 venv，执行：

```powershell
& <runtime-python> -m pytest tests/test_llm_contracts.py tests/test_llm_client.py tests/test_llm_unified_store.py tests/test_llm_runtime_secrets.py tests/test_llm_connection_test.py tests/test_llm_translation_gray.py tests/test_llm_config_http_contract.py tests/test_llm_fake_integration.py tests/test_caption_cache.py tests/test_caption_contract.py tests/test_caption_job.py tests/test_vision_service.py tests/test_caption_api.py tests/test_caption_http_contract.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py (Get-ChildItem tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) -q
```

结果 160 passed，4 项现有依赖 deprecation warnings。此前针对配置契约 47 passed、JSON/写回 50 passed，均为增量中间结果，以最新 160 为当前相关 suite 结果。

Node 22.17.1 执行 `npm --prefix frontend run check`：typecheck pass，lint 0 errors / 2 个已有 EngineStatusBar warning，Vitest 48 files / 307 tests pass（14.18s），build 1858 modules（5.90s）。新增组件测试验证保存预设后撤销编辑、语言不匹配时禁用启动，以及 pending preview 时按钮禁用/只发一次请求。前端测试不是浏览器人工验收。

`git diff --check` pass；每次 build 后通过 Git restore 恢复 tracked dist 基线，正式隔离验收必须从源码重新构建。此前提交的 78 个变更文件进行凭据模式扫描，pass；首次扫描因 Git 中文路径 quoting 失败，已用 NUL 分隔路径重新执行，不将失败的扫描当作通过。

## 仍待实现与验证

提示词预设尚未建立 prompt_id 解析/持久 job snapshot/report 完整链路；设置 UI 的共享组件与取消回滚、组合预览、轮询重叠/迟到响应、真实下载及完整浏览器验收仍待完成。完整旧 Tag 灰度、EDD 人工评分、失败矩阵、Zero-Short 及从零隔离重建仍为未关闭门禁。
