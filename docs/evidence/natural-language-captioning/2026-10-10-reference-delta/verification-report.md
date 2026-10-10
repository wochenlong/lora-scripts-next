# 参考设计增量实施与简单验收报告

日期：2026-10-10（Asia/Shanghai）。分支：`feat/NL-Captioning`。基线：`9927224`，本次为未提交工作树增量。

## 已完成

- 新参考复审明确只采纳选项组织和完整语言模板，不复制单独服务配置/词典翻译/默认中文。
- 前后端内置英文、简体/繁体中文和日文完整提示词，英文优先；正文必须使用目标语言，包含可见事实与禁止臆测约束。
- 描述详略选项应用简短（1–2句）/详细（3–5句）完整模板；自定义显示由提示词决定，切换须确认且取消保留草稿。
- 后端省略 prompt 时按 language 选择对应完整模板；显式空 prompt 仍拒绝。预设/自定义优先，缓存和任务冻结继续复用现有实际 prompt/system revision。
- 现有手测项目已更新、从其源码构建、正式启动；用户数据、预设、配置和任务内容保持。

## 测试结果

| 验证 | 状态 | 实际结果 |
|---|---|---|
| Python 3.11.15 完整 `test_caption*.py` 组 | pass | 133 passed，4 既有依赖弃用警告，0 skip |
| Node 22.17.1 前端 `npm run check` | pass | typecheck/lint/Vitest/build；348 tests / 53 files；lint 0 error、2 既有警告 |
| 手测项目自身 `npm run build` | pass | Node22 构建通过 |
| HTTP 正式启动 | pass | 28766 listener、`/api/tagger/models` 和 `/dataset/tagger` 返回成功 |
| 浏览器详略和语言 | pass | 简短英文→简短中文→英文仍简短；选择详细后完整英文 user/system |
| 用户旧默认预设 | pass | 未静默升级或覆盖；默认内容仍旧预设，选择内置模板可使用新版本 |
| 390px | pass | 无横向溢出 |
| Editor 中文原文 | pass | 已有自然语言原文可见；开启译文与原文相同，0 Caption 翻译请求；无 Tag chips；原文不变 |
| 数据保护 | pass | 53 个数据集/预设/任务/配置/SQLite文件升级前后及启动后 hash 全一致 |
| 新模板真实远程/本地生成与质量 | not-run | 本轮按用户“简单测试后亲自测试”交付，不使用历史真实结果代替新提示词质量 |
| 新一轮全项目从零重建 | not-applicable | 局部优化，沿用用户保留的现有手测环境；不宣称 fresh 重建 |
| 用户人工验收 | pending | 待用户亲自测试 |

## 故障与修复记录

初始错误使用宿主 Python3.14；旧 Starlette 的 TestClient 与宿主 HTTPX 不兼容，产生 HTTP case setup 失败。改回既有独立 Python3.11 后初始 130 项通过。中途新增默认模板处理曾造成 preset 字段重复移除的 KeyError，修正为安全移除后完整 133 项通过。旧前端测试断言模板短语也同步为新模板断言；最终全检查通过。没有修改依赖、跳过失败或改 Agent 接口。

浏览器首轮默认详略/完整模板检查为 false，原因是该真实环境已保存旧用户默认预设；行为符合保留用户预设的要求。显式选新内置详细模板后完整英文检查通过。未把首轮结果改写成默认迁移成功。

## 文件与交付身份

- 原始日志位于手测根目录 `reference-delta-backend-fixed.txt`、`reference-delta-frontend-final.txt`、`reference-delta-manual-build.txt`；此目录保存同名摘要日志。
- `deployment.json`：同步文件 SHA256、基线与工作树交付标识、数据保护结果、手测 dist index SHA256。
- `browser-checks.json`：浏览器实际检查摘要。
- 手测根：`E:\OpenSourceTeamWork\workspace\sandboxes\nl-caption-manual-20261009`。
- 回退备份：该目录 `reference-delta-backup-20261010/`，含覆盖前源码与旧 dist，不含明文凭据副本。
- 应用地址：`http://127.0.0.1:28766/dataset/tagger`；启动/停止仍使用现有脚本。
- 开发分支 tracked dist 已恢复原 HEAD，只交付源码；手测 dist 使用真实构建。未提交、未 push。既有 `test_diffsynth_review.py` 不改动。

## 完成门

REF-01、PROMPT-01、PROMPT-02、OPTION-01、TEST-01、SCOPE-01、HANDOFF-01 均 pass。开发与简单测试交付完成；用户人工验收保持 pending。
