# 标签翻译 V4 验证记录

更新时间：2026-10-02（Asia/Shanghai）

本记录对应 docs/tasks/tag-translation-task-book.md 的 V4-A～V4-E 阶段，所有验证在
feat/tag-translation 专用 worktree 完成。词库和模型资产只写入
assets/tag_translation/ 用户数据目录，不进入 Git。

## 自动化检查

| 检查 | 结果 |
| --- | --- |
| python -m compileall -q mikazuki/tag_translation | 通过 |
| python -m pytest -q tests/test_tag_translation_config.py tests/test_tag_translation_api.py tests/test_tag_translation_dictionary.py tests/test_tag_translation_local_model.py | 24 项通过（含本轮错误码、local-only、镜像入口、本地运行时、资产提取、动态端口和重启后安装状态回归） |
| cd frontend; npm run check | 通过；41 个测试文件、253 项测试通过；构建通过 |
| git diff --check | 通过 |

前端 lint 仅保留仓库既有 EngineStatusBar.vue 的 2 条
vue/require-default-prop 警告；本轮没有新增 lint 错误。Vite 对第三方
@vueuse/core 的纯函数注释和 chunk 大小给出已有构建提示，未阻断产物生成。

## 真实服务探针

- 开发后端 http://127.0.0.1:28000 可启动，/api/tag-translation/status 返回
  词库、LLM、local-model 三组状态。
- 隔离验收数据中的 Danbooru SQLite 词库：330,898 行，SHA `0f4e8e9918fbfd11d578543c3e8367cfcf7fdf90` 校验通过。
- blue_eyes、long_hair 的实际解析分别返回“蓝瞳”“长发”，来源为
  danbooru；未命中项可以继续走 MyMemory/LLM。
- 隔离环境实际完成 qwen3.5-0.8b-q4_0 GGUF（563,036,064 bytes）和 llama.cpp
  b11327 Windows CPU x64 runtime（19,275,534 bytes）安装；一键安装自动启动健康检查
  通过，动态端口示例 `7072 -> 7892`，停止/重启后端口发生变化且没有固定 28000/18081。
- 受管本地代理实际返回 Qwen 翻译结果；关闭 Qwen 思考后，`isolated_auto_qzx` 返回
  `独立自动`，响应为 stop 而不是空 reasoning 内容。

## 人工验收路径

1. 打开数据集编辑器，点击“中文释义（全数据集）”，确认进度显示为 N/N，
   切换图片后缓存仍在，caption 原文没有中文释义写入。
2. 打开“翻译设置”，在 Danbooru 词库区域执行检查、更新、取消、重试；下载状态
   每秒轮询，失败显示错误文本，旧 SQLite 文件保持可查询。
3. 在本地 Qwen 区域点击“一键安装运行环境”；安装完成并自动启动后，选择本地模型，
   翻译请求使用主应用内部的 loopback OpenAI 兼容 endpoint。
4. 选择“自动回退”，以词库未命中的标签验证顺序为
   Danbooru → MyMemory → LLM；关闭外部 provider 后仍可编辑数据集。
5. 在任务页和设置页之间切换，再刷新浏览器，确认数据集路径、当前图片、草稿、
   过滤器和翻译展示偏好恢复。

## 隔离目录真实验收

隔离根目录：
`project/.runtime/tag-translation-isolated-acceptance-20261002/`。

- `source/`：从 `feat/tag-translation` 全新 clone 后安装前端依赖和 Python 3.13
  轻量运行环境；Vite 使用 `VITE_API_TARGET=http://127.0.0.1:7915`，验证了代理不再
  假设固定后端端口。
- `data/`：全新用户数据根目录，现场下载词库、模型和 runtime；`sample/` 只含一张
  图片和 `blue_eyes, isolated_runtime_tag` 原文 caption。
- 浏览器验收覆盖：检查更新、“已是最新”时更新按钮禁用、远程接口添加/启用/删除、
  本地服务停止/启动、未 running 时保存禁用、网络翻译、LLM、本地模型、自动回退、
  清理网络/LLM 缓存、中文释义开关、N/N 进度、刷新恢复翻译和原文保护。
- 真实结果：Danbooru 命中 `blue_eyes -> 蓝瞳`；LLM 命中
  `isolated_runtime_tag -> 独立运行时标签`；自动回退两项均显示释义；刷新页面后
  仍显示 `2/2` 和两条中文释义；`sample.txt` 仍为英文原文。
- 证据快照：`dictionary-check.json`、`dictionary-latest-noop.json`、
  `dictionary-retry-cancel.json`、`local-status-thinking-off.json`、
  `local-dynamic-port-final.json`、`local-setup-final-fixed.json`、
  `translation-path-matrix.json`、`auto-fallback-response.json`。

## 已知边界

- Qwen GGUF 和 llama.cpp 运行时不随源码发布；首次使用由“翻译设置”按需下载，
  安装结果只写入用户数据目录。
- Qwen 0.8B 的翻译质量仍属于轻量兜底能力，复杂或自造标签可能只得到近似释义；
  Danbooru 词库仍是首选来源。
- 隔离浏览器控制台有项目既有的 `/api/plugin-host/bootstrap` 403 和 `/api/tasks`
  500；不影响 Dataset Editor/翻译 API，但应由插件宿主和任务模块另行处理，不能当作
  翻译安装测试通过证据。

## 本轮缺陷回归

- 词库更新探针先通过 GitHub API 原始内容入口下载，避免跟随到不可达的
  raw.githubusercontent.com；测试中能看到进度进入 downloading，旧库仍保持可查询，
  取消后状态为 cancelled。
- 本地代理在模型运行时未启动时返回 503，配置保存接口返回 409，前端不会再出现
  “未配置就能启用本地 LLM”的状态。
- 本地 endpoint 固定为主应用数据集翻译路由，llama-server 只监听用户数据目录配置的
  loopback 内部端口。
- 本地模型页签在缺少模型时仍可进入并点击一键安装；只有运行状态为 running 时才允许保存
  为当前 LLM 路由。
- 本地模型配置不再展示 endpoint 或可执行文件路径；主应用端口从 GUI 启动环境读取，
  llama-server 内部端口由操作系统动态分配，端口冲突会在健康检查阶段失败并可重试。
- 词库镜像回归探针验证 ghfast.top、ghproxy.net、gh-proxy.com 均可返回完整文件响应，
  作为 GitHub API/raw 失败时的备用下载入口。
- 修复了进程重启后重复点击一键安装会长期停留在 `installing` 的状态机缺陷：已存在
  runtime 文件现在会先归一为 `ready`，随后启动健康检查；回归测试已加入
  `test_setup_reconciles_existing_runtime_after_process_restart`。
- llama.cpp 启动命令显式传入 `--reasoning off`、`--reasoning-budget 0` 和
  `--chat-template-kwargs {"enable_thinking":false}`，避免 Qwen3.5 生成 reasoning
  占满 token 而没有翻译内容。
