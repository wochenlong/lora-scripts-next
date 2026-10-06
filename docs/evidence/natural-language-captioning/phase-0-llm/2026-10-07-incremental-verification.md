# 2026-10-07 增量实现与验证

本报告覆盖当前 feature 分支的增量修复，不代表最终完整交付或隔离重建通过。修改前 commit 为 397581cb82dd0f714a4e15997847db8e9c27c409；本次变更与本报告一并提交，最终 commit 以 Git 记录为准。

## 实现与覆盖

| 范围 | 本次实现 | 实际证据 | 未关闭边界 |
| --- | --- | --- | --- |
| 统一配置 | v4/v5 兼容、双入口共享锁、删除所有 profile、凭据变更 revision、保存旧字段 | llm contracts/unified store/runtime secrets tests | 完整 facade 灰度与共享 UI |
| 凭据 | 配置只存掩码，Key 仅在进程内，读取旧明文时原子迁移，写失败不更新 Key | runtime secrets 5 tests：双入口、重启、排序删除、迁移、失败回滚 | 重启后须重新注入；无秘密文件作为替代 |
| 路由与诊断 | 默认不启用本地兜底；远程优先；所选 profile 的连接测试禁止换目标并拒绝非法/截断 JSON | route/fake provider/connection tests | 真实受管 runtime 与远程失败后显式兜底验收 |
| 视觉任务 | 任务快照、SQLite revision 缓存、取消正在等待的请求、占用锁、before hash、忽略策略、严格 caption JSON | caption job/cache/http contract tests | 报告持久化、恢复、组合预览、完整错误矩阵 |
| 受管 Qwen | 两文件固定 revision/size/SHA，复用 llama.cpp 生命周期、安装/取消/启停 API | local vision manager 4 tests；本报告末尾新增三样本受管验证 | 完整 HTTP API、下载、浏览器、真实写回与隔离重建仍待验证 |
| 编辑器 | mixed 识别、原文空白保留、批量写前整体校验、阻止 Tag 清理自然语言 | backend editor/format tests、前端 caption tests | 完整浏览器与真实写回验收 |
| TaggerPage | 三模式、模型字段同步、本地资源/启停、显式 fallback、预览/状态/重试、错误解析 | Node 22 check、3 个页面组件场景 | 设置复用、预设/取消回滚、完整人工验收 |

## 实际命令与结果

执行环境：Windows，独立 Python 3.11.15 venv（requirements 安装完成）、Node 22.17.1，当前开发 worktree。本节使用 `<runtime-python>` 表示该 venv 的解释器，避免证据中写入机器绝对路径；具体位置见续接任务记录。

相关后端回归执行：

```powershell
& <runtime-python> -m pytest tests/test_llm_contracts.py tests/test_llm_client.py tests/test_llm_unified_store.py tests/test_llm_runtime_secrets.py tests/test_llm_connection_test.py tests/test_llm_fake_integration.py tests/test_caption_cache.py tests/test_caption_contract.py tests/test_caption_job.py tests/test_vision_service.py tests/test_caption_api.py tests/test_caption_http_contract.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py (Get-ChildItem tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) -q
```

凭据和连接测试修复后第一次：134 passed / 4 warnings，5.14s。随后加入默认关闭 fallback 的回归，再运行同一命令：136 passed / 4 warnings，5.35s。此前相关版本为 122 passed；不能把旧版本结果作为后续未测试改动的证据。

前端使用 Node 22 的 npm CLI 运行 `npm --prefix frontend run check`：typecheck 通过；lint 0 errors / 2 个已有 EngineStatusBar 默认属性 warning；Vitest 48 files / 304 tests passed；Vite build 1858 modules，9.14s，存在已有 Rollup 注释和 chunk 大小 warning。该结果早于仅后端的凭据/诊断修复，前端源码此后未改动。

`git diff --check` 已执行，通过；Git 提示 CRLF 转换不属于 whitespace 错误。旧提交曾误移除 tracked dist，已使用 `git restore --source=1cfa947 --staged --worktree -- frontend/dist` 恢复原有受跟踪构建基线，不手工修改生成文件；最终隔离验收必须重新从源码构建。

单次命令指定不存在的 `test_tag_translation_config_store.py` 导致 no tests ran，之后以实际文件匹配纠正并重新执行。凭据新增测试曾因 Windows 默认 GBK 读取 UTF-8 fixture 失败，已显式使用 UTF-8，后续相关回归通过。

## 完成门

Phase 0–2 均仍在执行；Phase 3/4 pending。宽范围后端回归失败见同目录 failure report；不得把当前 focused suite 和前端 build 作为完整矩阵通过，也不得据此宣布 Phase 4 完成。

## 后续兼容层灰度补验

发现旧翻译 `_active_llm_config` 把所有已安装的本地 profile 直接列为兜底。已修复为必须检查用户明确启用的 legacy `local.enabled`；即使用户启用本地，远程仍优先。

实际执行：上述 venv 的 `python -m pytest tests/test_llm_translation_gray.py tests/test_llm_runtime_secrets.py tests/test_llm_unified_store.py tests/test_llm_connection_test.py` 加所有 `test_tag_translation_*.py`，`-q`。结果 58 passed / 1 warning / 1.65s。新增灰度测试通过真实 HTTP fake text provider 比较 v4 facade、迁移后 facade、统一服务的路由/凭据/最终翻译结果；另验证显式开/关本地时的候选列表。

受管 Qwen 三样本真实启动/推理/取消/停止的开发验证已通过，证据在 Phase 1 的 `2026-10-07-managed-qwen-runtime.md`；复用 probe 资产，不替代 Phase 4。
