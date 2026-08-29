# Managed content channel — how updates reach an install (troubleshooting)

- Version: `2026-08-29-3`
- Scope: why knowledge/template/skill revisions do (or don't) show up in an installed plugin; what to check, in order.
- Evidence status: behaviour pinned by project tests `tests/test_plugin_marketplace_assets.py` (sovereignty/failure semantics) and shipped with plugin >= 0.3.4 (layer 1).
- Aliases / 检索关键词: 更新, 内容, 知识库, 没生效, 通道, assets, managed, 备份, OFFLINE, configured

## 内容怎么到达装机

1. 修订在 agent-assets 仓库改 `assets/knowledge|templates|skills`，bump `compat.json` 的 `assetsVersion`，发布 `assets-<assetsVersion>` tag（zip + 签名索引）。**不需要发插件新版本。**
2. 装机侧触发：市场页更新按钮，或对 Agent 说"更新内容库"（`assets_update` 工具，会先要你确认）。
3. 应用语义：只动托管命名空间；你本地改过的托管文件先备份到数据根 `managed/local-backups/<时间戳>/` 再更新；你自己新建的文件永远不被触碰。

## 没生效时按序检查

1. `assets.status`：`configured:false` = 未配置索引（检查 `NEXT_TRAINER_ASSETS_INDEX_URL`）；`OFFLINE` = 网络/代理问题，重试或指内网镜像 `NEXT_TRAINER_ASSETS_MIRROR`。
2. 版本号：status 里的 `assetsVersion` 是否已是目标版；不是则远端索引未发布或未指向该 tag。
3. 备份目录出现同名文件 = 你改过它，更新走了备份后覆盖；旧内容在备份里可找回。
4. 更新链任何失败都不会影响训练功能——它坏了只说明内容没到，不说明装坏了。
