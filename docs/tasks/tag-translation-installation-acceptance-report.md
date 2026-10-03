# 标签翻译下载与安装系统验收报告

日期：2026-10-02（Asia/Shanghai）  
Goal：`01a0c916-e274-7412-9950-a0d41c633bdf`  
分支：`feat/tag-translation`  
验收目录：`project/.runtime/tag-translation-isolated-acceptance-20261002`

## 结论

T1～T6 的工程验收项已完成，代码和文档已推送到远端分支，当前不创建 PR，等待用户统一验收。词库、模型和运行时均在独立 `data/` 根目录现场安装，没有复用项目原有资产，也没有加入 Git。

## 结果

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 词库状态 | 通过 | `dictionary-check.json`、`dictionary-latest-noop.json` |
| 最新状态保护 | 通过 | 最新时 UI 更新按钮 disabled，API 无下载任务 |
| 取消/重试/旧库保护 | 通过 | `dictionary-retry-cancel.json`、`dictionary-progress.jsonl` |
| 本地一键安装 | 通过 | `local-setup-final-fixed.json`；Qwen GGUF 563,036,064 bytes，llama.cpp b11327 19,275,534 bytes |
| 自动启动/健康检查 | 通过 | `local-status-thinking-off.json` |
| 动态端口 | 通过 | `local-dynamic-port-final.json`，示例 7072 → 7892 |
| Qwen 翻译 | 通过 | `local-translation-response.json`，思考关闭后返回有效内容 |
| 五种翻译路径 | 通过 | `translation-path-matrix.json`、`auto-fallback-response.json` |
| 设置 UI | 通过 | `ui-manual-acceptance.json`，覆盖词库、远程卡片、本地启停、缓存清理和保存保护 |
| 全量进度/刷新恢复 | 通过 | 浏览器实测 2/2；刷新后释义仍显示，`sample.txt` 原文未修改 |
| 自动化回归 | 通过 | 后端专项 24 项；前端 41 个测试文件/253 项、typecheck、lint、build |

## 修复项

1. 已是最新词库的更新按钮和 API 双重禁止无意义更新。
2. 词库、Qwen 模型和 llama.cpp 下载增加镜像/备用路径、超时、取消、重试、原子安装和旧库保护。
3. llama.cpp 从不可用的旧资产改为 b11327 Windows CPU x64，并完整解压 DLL 依赖。
4. 本地运行时端口由操作系统动态分配；主应用内部代理使用 `internal://dataset-translation`，不暴露固定 28000/18081。
5. 修复重启后再次点击安装会长期停留 `installing` 的状态机缺陷。
6. Qwen 启动显式关闭 reasoning，避免只返回 reasoning 内容而没有译文。

## 非阻断边界

隔离浏览器控制台仍记录项目既有的 `/api/plugin-host/bootstrap` 403 和 `/api/tasks` 500；它们属于插件宿主和任务模块边界，不影响 Dataset Editor 与翻译链路，已单独记录，不能作为翻译安装通过证据。Qwen 0.8B 适合轻量兜底，复杂自造标签的质量仍低于 Danbooru 词库。
