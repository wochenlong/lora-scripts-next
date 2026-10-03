# 标签翻译 V5 Review 加固验收报告

日期：2026-10-03（Asia/Shanghai）  
Goal：`01a0c916-e274-7412-9950-a0d41c633bdf`  
分支提交：`1da2d2143a169f1084099574bcf3c3b2dd8e77c6`

## 完成内容

- 新增未保存 tag 会进入筛选索引，并且勾选后可以命中当前草稿图片；草稿仍不会写入 caption 文件。
- 中文释义开关打开时，新增 tag 会触发 debounce 增量翻译，只请求缓存中没有的 tag，进度会从 `2/2` 更新为 `3/3`。
- 远程 LLM profile 改为可折叠卡片；当前启用 profile、模型摘要和折叠状态清晰可见，新增 profile 自动展开，启用仍保持单选。
- 设置弹窗取消或保存失败时恢复已提交配置，避免未保存的 profile/mode 草稿污染翻译请求。
- 本地服务停止时显示重新启动或切换远程接口的操作提示；选择 LLM provider 时，如果本地或远程不可用，会提示配置并打开翻译设置。
- 保留后端 409 保护、动态端口、provider revision 和缓存隔离机制。

## Review 实测

- 原始 bug：新增 `new_review_tag` 后筛选列表找不到，已复现并修复。
- 修复后：筛选列表出现 `new_review_tag`，勾选后 gallery 显示 `当前筛选结果（1）`。
- 中文释义开关开启后新增 tag，进度由 `2/2` 变为 `3/3`。
- 停止本地服务后设置页显示“本地服务当前未运行”，保存按钮保持禁用，并提供远程切换动作。
- 远程 profile 添加、折叠、展开、取消恢复均已在浏览器中验证。

## 自动化验证

- 后端翻译专项：25 项通过。
- 前端 typecheck：通过。
- 前端 lint：无新增错误；保留仓库既有 `EngineStatusBar.vue` 两条 warning。
- 前端测试：41 个测试文件、254 项通过。
- 前端生产构建：通过；仅有既有第三方注释和 chunk 大小提示。

## 最终隔离启动

隔离根目录：
`project/.runtime/tag-translation-v5-final-acceptance-20261003`

- 源码来自 `feat/tag-translation` 的提交 `1da2d21`。
- 使用全新 `data/`，只创建一张 `sample.png` 和英文 `sample.txt`。
- 词库、模型、runtime、翻译缓存均未复制，启动状态为 dictionary `missing`、local model `missing`、LLM `configured=false`。
- 未执行 `npm install`、`pip install`、模型下载或词库下载；前端和 Python 运行环境仅通过目录 junction 复用机器上已有依赖。
- 后端：`http://127.0.0.1:7925`。
- 前端：`http://127.0.0.1:5176`。
- 已在干净数据根目录打开 Dataset Editor 和“翻译设置”，确认词库重试、本地一键安装、远程 profile、折叠、远程未配置提示、本地未运行提示和保存禁用状态均可见。

## 非阻断提示

浏览器控制台仍可能出现项目既有的 `/api/plugin-host/bootstrap` 403 和 `/api/tasks` 500；它们不属于本次翻译功能加固范围，也不影响 Dataset Editor 翻译设置页面启动和交互。

## 验收后热修复

真实验收中发现，保存 LLM 设置会清空前端全部译文缓存但不自动重新翻译，导致开关仍开启而中文释义消失。现已修复为只清理外部 provider 结果、保留 Danbooru 释义，并在保存成功后自动重新查询当前数据集；同时进度会显示未命中数量。97 张数据集实测保存设置后释义保持可见，进度显示 `1032/1032（未命中 1 条）`。
