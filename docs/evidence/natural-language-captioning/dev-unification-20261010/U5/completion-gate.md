# U5 完成门（AC-U5）

日期：2026-10-11
阶段：从零隔离重建与真实验收
状态：`pass_with_platform_skips`

## 隔离边界

- 独立项目根：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r2`
- 独立输入根：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-inputs-20261011-r1`
- 源码候选：`70ae1c0f`；U5 业务验收报告在 `7a650f29` 生成，后续 `70ae1c0f` 仅修复隔离远程验证器的 `--runtime` 参数兼容，不改变业务实现
- 独立 Python：3.11.15 venv；独立前端依赖目录和 npm 缓存
- 仓库要求并实际使用 Node 22.17.1 完成 U5 前端检查；U4 早期检查曾使用 Node 24.13.0，已在 U4 台账中单独记录
- 输入重新下载并按 manifest 校验：公开样本、Qwen3.5-2B GGUF、F16 mmproj、llama.cpp b11327、WD14/CL ONNX 资产
- 配置、SQLite、任务队列、缓存、模型目录和 user-data 均为新建；未复制旧运行状态

## 自动回归

- 后端报告：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r2/u5-backend-scope-20261011-r3/report.json`；68 个测试文件、805 个用例，799 passed、0 failed；6 个 Windows symlink 权限 skip，均已记录为平台边界
- 前端报告：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r2/frontend/npm-check.log`；67 个测试文件、421 个测试通过；typecheck 通过；lint 0 errors、2 个既有 warning；production build 通过
- 独立真实 HTTP 回归：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r2/u5-http-acceptance-20261011-r2/http-real-report.json`，自然语言预览/写回、Editor 格式、hash 冲突、取消/重试/回滚、预设 revision 和清理检查全部通过

## 真实本地自然语言链路

报告：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r1/evidence/real-local/report.json`

- Qwen3.5-2B + `mmproj-F16.gguf` + llama.cpp b11327 启动成功
- 3 张公开样本英文 Caption 写回成功
- 本地中文翻译成功；翻译缓存重放零请求；中文正文短路零请求
- 预览不写盘、任务归档、停止/取消和缓存行为通过

## 真实远程自然语言链路

报告：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r1/evidence/real-remote-r2/report.json`

- 3 张样本英文 Caption 写回成功
- 远程 text/vision capability verification 通过
- 翻译、缓存重放、中文短路、预览不写盘和任务归档通过
- API Key 仅在后端运行时注入；报告、配置、日志和源码不含明文 Key

## 真实 WD/CL Tag 链路

报告：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u5-project-20261011-r3-tag/report.json`

- 使用重新下载的 `wd14-convnextv2-v2` ONNX，实际 provider 为 `CPUExecutionProvider`
- Chelsea/Coffee/Rocket 三张样本均完成真实 Tag 推理
- 预览不写盘、新旧 Tag 输出逐字节一致、任务归档和默认跳过通过
- 该链路不调用 LLM，保持旧 Tag 与自然语言 Caption 的边界

## 边界与结论

- U1 的候选质量/资源比较探针按用户决定记为 `waived_by_user`；本门只证明锁定的 Qwen3.5-2B 在功能链路中可启动并工作，不推导候选比较通过
- 6 个 symlink 用例因 Windows 权限明确 skip，不影响业务用例结论
- 真实远程报告不保存原始 provider envelope、图片路径或敏感凭据
- U5 完成后进入 U6：建立全新手测沙盒并启动应用；用户手工验收仍记录为 `pending_followup`
