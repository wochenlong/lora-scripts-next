# 标签翻译 V4 验证记录

更新时间：2026-10-01（Asia/Shanghai）

本记录对应 docs/tasks/tag-translation-task-book.md 的 V4-A～V4-E 阶段，所有验证在
feat/tag-translation 专用 worktree 完成。词库和模型资产只写入
assets/tag_translation/ 用户数据目录，不进入 Git。

## 自动化检查

| 检查 | 结果 |
| --- | --- |
| python -m compileall -q mikazuki/tag_translation | 通过 |
| python -m pytest -q tests/test_tag_translation_api.py tests/test_tag_translation_dictionary.py tests/test_tag_translation_store.py tests/test_tag_translation_local_model.py | 12 项通过（含本轮错误码、local-only、本地运行时回归） |
| cd frontend; npm run check | 通过；41 个测试文件、253 项测试通过；构建通过 |
| git diff --check | 通过 |

前端 lint 仅保留仓库既有 EngineStatusBar.vue 的 2 条
vue/require-default-prop 警告；本轮没有新增 lint 错误。Vite 对第三方
@vueuse/core 的纯函数注释和 chunk 大小给出已有构建提示，未阻断产物生成。

## 真实服务探针

- 开发后端 http://127.0.0.1:28000 可启动，/api/tag-translation/status 返回
  词库、LLM、local-model 三组状态。
- 当前用户数据中的 Danbooru SQLite 词库：330,414 行，SHA 校验通过。
- blue_eyes、long_hair 的实际解析分别返回“蓝瞳”“长发”，来源为
  danbooru；未命中项可以继续走 MyMemory/LLM。
- /api/tag-translation/local-model/status 返回固定安装清单
  qwen3.5-0.8b-q4_0、GGUF 文件名、下载进度、llama-server 路径和 loopback
  endpoint。当前机器没有自动下载模型或启动运行时，避免未经用户操作占用磁盘和端口；
  设置页的安装、取消、启动、停止动作已经接入。

## 人工验收路径

1. 打开数据集编辑器，点击“中文释义（全数据集）”，确认进度显示为 N/N，
   切换图片后缓存仍在，caption 原文没有中文释义写入。
2. 打开“翻译设置”，在 Danbooru 词库区域执行检查、更新、取消、重试；下载状态
   每秒轮询，失败显示错误文本，旧 SQLite 文件保持可查询。
3. 在本地 Qwen 区域安装 GGUF，填写 llama-server(.exe) 路径并保存；启动后将
   “使用本地 LLM”打开，翻译请求使用 loopback OpenAI 兼容 endpoint。
4. 选择“自动回退”，以词库未命中的标签验证顺序为
   Danbooru → MyMemory → LLM；关闭外部 provider 后仍可编辑数据集。
5. 在任务页和设置页之间切换，再刷新浏览器，确认数据集路径、当前图片、草稿、
   过滤器和翻译展示偏好恢复。

## 已知边界

- Qwen GGUF 和 llama.cpp 运行时不随源码发布；首次使用由“翻译设置”按需下载，
  运行时需要用户提供对应平台的 llama-server 可执行文件。
- 当前主机未进行真实 Qwen 推理质量/吞吐验收；该验收依赖用户选择下载模型并
  提供运行时路径，完成后应把响应耗时和质量样本追加到本记录。
