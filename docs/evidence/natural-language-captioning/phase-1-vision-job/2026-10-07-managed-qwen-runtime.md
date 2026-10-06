# 受管 Qwen 服务开发验证

状态：pass-with-boundary；属于开发中的受管生命周期验证，不是 Phase 3 人工质量评测或 Phase 4 隔离重建。

## 环境与命令

Windows CPU-only，Python 3.11.15；Qwen3-VL-2B Q4_K_M 与 Q8 mmproj，固定 revision `52d6c8ffea26cc873ac5ad116f8631268d7eb503`。运行 `tools/verify_managed_caption_runtime.py`，参数为新 root、既有 P1 GGUF 目录、llama.cpp b11327 server 和三个公开样本：chelsea、coffee、rocket。机器绝对路径不写入本证据，具体开发目录见续接记录。

脚本构建全新配置目录，将既有 probe 模型文件建立硬链接；通过真实 `LocalVisionService.start_runtime()` 验证二文件 SHA、启动/健康检查、profile 登记，再通过 `UnifiedLLMService` 请求视觉 JSON。只汇报结构化指标，不输出 caption 原文、原始响应或秘密；最后停止管理的进程。此处未重新下载模型，不具有 Phase 4 的独立性。

## 实测结果

| 项目 | 实测 |
| --- | --- |
| 受管启动 | 4.835 秒，running=true |
| chelsea | 4.243 秒；451×300 JPEG，27833 bytes；zh-CN 严格 JSON；finish_reason=stop |
| coffee | 6.164 秒；600×400 JPEG，56809 bytes；zh-CN 严格 JSON；finish_reason=stop |
| rocket | 7.364 秒；640×427 JPEG，41994 bytes；zh-CN 严格 JSON；finish_reason=stop |
| llama-server RSS 峰值 | 3107680256 bytes，约 3.11 GB / 2.89 GiB；100ms 采样，不包括整个 GUI 内存 |
| in-flight 取消 | 0.195 秒，任务抛出 CancelledError；没有等待完整长输出 |
| 取消后请求 | 对同一指定本地 profile 做严格 JSON vision connection test，通过 |
| 停止 | stop_runtime 等待进程退出，status 不再 running |

三张输出均通过项目 caption schema 和中文字符规则，不据此推断语义质量。脚本使用受限 JPEG data URL；协议层不传本地路径。

## 尚未证明

尚未验证下载 API、完整 FastAPI/浏览器路径、caption job 的真实文件写回、远程优先及真实远程失败后的显式兜底、完整 EDD 评分、用户安装体验和清理磁盘资产。中间验证目录保留用于后续排查，只包含公开样本资产链接与无 Key 配置；正式隔离重建必须使用新的环境、配置、缓存和模型文件。
