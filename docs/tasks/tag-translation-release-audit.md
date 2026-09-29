# 标签翻译发布审计

日期：2026-09-29
分支：`feat/tag-translation`
最终提交：`b21b5ed`（文档格式收口；功能提交为 `260958c`）

## 交付物

- [x] Danbooru SQLite 词库现场下载：用户数据目录 `assets/tag_translation/danbooru/`。
- [x] 词库下载使用临时文件、GitHub blob SHA、SQLite quick check 和原子替换。
- [x] 词库二进制和翻译缓存由 `.gitignore` 排除，未进入 Git。
- [x] Danbooru provider 优先查询 `name/category/cn_name/post_count`。
- [x] MyMemory provider 可选调用，真实请求返回 `blue eyes → 蓝眼睛`。
- [x] OpenAI 兼容 LLM provider 支持远程 HTTPS 和本地回环 endpoint。
- [x] LLM API Key 通过 masked config 保存，不进入前端 bundle 或日志。
- [x] Dataset Editor 显示英文 tag 和中文释义，翻译状态独立于 caption。
- [x] 保存前端 textarea 和原始 `.txt` 的内容保持 `blue_eyes, long_hair`。
- [x] `/api/dataset-editor/tag-translations` 兼容入口已提供。

## 许可证和来源

- [x] Aaalice 迁移模块保留 MIT 许可证文本：`docs/third_party/comfyui-autocomplete-aaalice-MIT.txt`。
- [x] Aaalice 迁移快照和文件 SHA 记录在 `docs/tasks/tag-translation-migration-inventory.md`。
- [x] ffdkj 词库来源和 schema 记录在迁移清单；词库按需下载，不随源码再分发。
- [x] WeiLin GPL-2.0-only 代码未复制，只保留行为参考。

## 验证证据

- 后端标签翻译和配置测试：8 项通过。
- Dataset Editor 相关后端测试：24 项通过。
- 前端 typecheck、lint、40 个测试文件/250 项测试和生产构建通过。
- 真实服务启动：`MIKAZUKI_DEV=1`、`127.0.0.1:28000`。
- 真实词库 API：返回 `blue_eyes=蓝瞳`、`long_hair=长发`。
- 真实 MyMemory API：返回 `blue eyes=蓝眼睛`。
- Edge CDP 页面验收：扫描临时数据集、打开 `sample.png`、点击“显示中文释义”，页面显示“蓝瞳/长发”。
- 原始 caption 和 `.txt` 均保持 `blue_eyes, long_hair`。

## 已知边界

- Qwen 0.8B 本地服务的真实模型质量尚未在本机启动；OpenAI 兼容配置、回环 endpoint、无 Key 逻辑和响应校验已覆盖。
- Node 24 生成的 `frontend/dist` hash 与仓库基线不同，构建产物未提交；发布构建应使用项目规定的 Node 版本和构建环境。
- ffdkj 词库内容可能出现专名或错误译名；词库结果只做辅助展示，不修改训练数据。

## 回滚

回滚代码使用分支提交的 Git revert；删除用户数据目录中的 `assets/tag_translation/` 可清除词库、配置和缓存，不影响已有 caption 和训练任务。
