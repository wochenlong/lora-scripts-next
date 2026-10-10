# U2 完成门（AC-U2）

日期：2026-10-11  
阶段：共享 LLM、配置预设、安装/runtime 统一

## 结果

`pass`（以当前工作树为候选，提交前仍需通过最终 U4 回归）。统一配置、能力声明与服务端 verified capability 已落地；Caption 强制 `vision`，翻译只要求 `text`；远程优先、本地显式兜底；API key 仅后端运行时注入；预设与 user-data 共用事务 root、锁、CAS revision、迁移预览/确认和幂等 receipt；Qwen3.5-2B 资产及 llama.cpp runtime 的下载与 hash 证据见同目录 JSON。

## 验证

- Python 3.11 定向范围：153 passed，1 skipped（Windows symlink 权限限制；不伪报通过）。
- Python compileall：通过。
- 资产完整性：`locked-default-assets.json` 与 `asset-download-report.json` 的 model/mmproj/runtime SHA256 一致。

## 边界

U1 的候选对比/质量/资源探针按用户决定记为 `waived_by_user`，不能从本完成门推导视觉质量已通过。真实本地启动、视觉 Caption、翻译、取消、恢复和从零安装属于 U4/U5 硬门。
