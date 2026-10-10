# U4 完成门（AC-U4）

日期：2026-10-11  
阶段：全量回归与真实链路审计

## 结果

`pass_with_platform_skips`。U4 是实现阶段的回归检查点；报告按执行时的源码提交保存（后续功能提交为 `7a650f29`，最终 `70ae1c0f` 仅修复隔离验证器参数兼容）。没有业务失败或未核销 P0/P1。Windows 当前进程没有创建 symlink 的权限，因此 6 个 symlink 安全用例显式记录为环境 skip，未静默忽略。最终候选的完整 fresh 证据以 U5 完成门为准。

## 证据

- 后端范围矩阵：`workspace/sandboxes/nl-caption-u5-project-20261011-r2/docs/evidence/natural-language-captioning/dev-unification-20261010/U4/backend-scope-20261011-r6`，68 个测试文件、805 个用例，799 passed、0 failed、6 个显式 symlink 权限 skip；该报告的 `source_commit` 保留为执行时的 `37dc62b4`。
- 前端完整 `npm run check`：67 files / 421 tests passed，typecheck、lint（0 errors，2 个既有 warning）和 Vite production build 通过；仓库要求 Node 22.17.1，本机实际执行版本为 Node 24.13.0。
- 真实远程：`remote-qwen36-natural-caption-translation-20261011.json`，6 张图英文 Caption、严格 JSON、远程 text/vision capability verification、翻译、缓存重放零请求、中文短路零请求、预览不写、任务归档和请求预算均通过；密钥仅后端运行时注入，报告与配置无明文。报告保留其执行时的 `source_commit`。
- 真实本地模型：`local-qwen35-natural-caption-translation-20261011.json`，Qwen3.5-2B + F16 mmproj + llama.cpp b11327，英文视觉 Caption、中文翻译、写回、冲突保护、取消、取消后健康和停止通过。报告保留其执行时的 `source_commit`。
- 真实 WD/CL Tag：`real-wd-cl-tag-20261011.json`，6 张图真实 `wd14-convnextv2-v2` ONNX，预览、字节一致性、归档和默认跳过通过。

## 范围与安全审计

- 远程 profile 只在后端运行时持有 API key，持久化使用掩码和运行时凭据缓存；仓库、报告、日志、命令参数未发现该 key。
- Caption 强制 vision capability；翻译只要求 text；远程 profile 优先，本地 fallback 必须显式开启。
- 自然语言正文保留原文编辑，翻译为只读派生内容；自然语言不进入 Tag 清理、排序、拖拽和批量 Tag 变更。
- 未修改 Agent、plugin、训练接口；旧 `/api/tag-translation/config` 仅保留兼容适配，不作为新的权威配置来源。

## 下一阶段

固定本候选后执行 U5 全新隔离重建。U5 必须重新下载 Qwen3.5-2B、mmproj、llama.cpp runtime、公开样本和 WD14/CL 资产，不得复用本阶段 sandbox 的模型或状态。
