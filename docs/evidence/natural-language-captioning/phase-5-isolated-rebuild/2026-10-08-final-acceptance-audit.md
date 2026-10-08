# Issue #409 最终功能验收审计

日期：2026-10-08。候选源码：`8986b9e16ca90268480139eda5e086cbd197dea1`。分支：`feat/NL-Captioning`。

**功能、前后端、真实资源、人工评分和第五次全新隔离重建已通过相应验收；整体完成门仍等待Windows临时目录清理或用户明确批准保留例外。** 不把清理策略拒绝记为完成，不把Windows原生symlink环境失败记为通过。

## 当前证据

[最终证据包](final-8986b9e/acceptance-summary.json)保存原始Windows矩阵、Linux补验、范围/源码SHA、环境版本、新下载凭据、真实Tag/Caption/HTTP、Zero-Short、浏览器和人工评分绑定。所有资源与依赖重新获取，前四个根均不接受，未复用其模型/venv/Node/配置/数据库/输出。

| 完成条件 | 实际证据与结论 |
|---|---|
| 本地/API运行方式与模型能力优先 | 模型目录合同、前端342项、实际浏览器WD/Qwen切换；无配置API入口隐藏 |
| 模型系列、原名搜索、具体型号和下载状态 | 浏览器WD折叠/搜索展开/原模型名/已下载标志，参数草稿保留 |
| Tag与Caption参数隔离 | 后端能力拒绝与前端模型切换验证；OpenAPI仅natural/tag及单模式layout |
| 不创建combined/mixed | 前端类型/选择器无入口，API与manager拒绝；新增OpenAPI合同覆盖声明 |
| 统一LLM与翻译兼容 | 统一配置/能力/掩码/缓存/运行时与旧翻译API，完整功能矩阵覆盖迁移、text/vision和灰度 |
| remote-first、显式本地兜底 | 当前fake合同/集成覆盖远程优先与失败策略；历史真实远程证据独立保留。本轮远程未配置，未声称通过 |
| user_data提示词预设 | 类型隔离、revision、事务/跨进程/硬退出恢复/导入测试；真实浏览器另存为后独立BrowserContext读取同模板 |
| 未保存保护/恢复默认/键盘 | 实际Esc保留正文与所选模板、Tab进入名称、撤销和恢复内置模板 |
| 任务档案/既有任务页 | 归档及取消/删除/恢复合同、TaskManager回调；浏览器真实批量与刷新/deep-link报告，实际配置不随模板修改改变 |
| 真实ONNX与旧Tag兼容 | 三图新旧逐字节一致、HTTP预览一致，Tag数13/11/8，实际CPU provider |
| 真实本地视觉模型 | Qwen3-VL-2B Q4_K_M + Q8 mmproj，llama.cpp b11327，三图严格JSON/中文写回 |
| 资源与data URL | 启动4.806秒、批量25.082秒、RSS峰值3,069,657,088字节，四次受限JPEG data URL请求，服务停止 |
| 缓存、预览、默认跳过 | 缓存重放3命中/零新请求；preview不写盘；已有三图默认跳过/零新请求 |
| 取消/仅失败重试/冲突/原子写 | 真实HTTP22项通过：取消0写盘、坏图单项失败后只重试1项、parent绑定、推理中外部修改不覆盖、无遗留part/tmp |
| Dataset Editor安全 | 真实HTTPnatural不拆Tag、单字“猫”、undo/redo原字节、外部hash409；完整矩阵覆盖unknown和历史mixed保护 |
| rollback/clear | 真实创建写回回滚仅移除未变TXT，历史清理保留图片；所有权/备份/hash和幂等合同通过 |
| 完整前后端矩阵 | 前端52文件342通过，typecheck/lint/build通过（两个既有warning）；后端52文件516项，Windows512通过/4权限失败/0skip，Linux四原case通过 |
| 环境失败口径 | 四项跨平台组合验收由用户明确批准；保留Windows原生symlink未验记录，不扩大豁免 |
| Zero-Short | 正式lifespan、全新空配置/数据库/缓存/队列；五API200、Profile空/视觉与词库missing、API空入口不存在、生成禁用且安装入口可用 |
| UI桌面与390px | 实际截图/DOM，底部100%及3/3报告、无横向溢出；截图等待侧栏resize动画完成 |
| EDD人工评分 | CLI三条与原B文本SHA完全一致；UI猫/咖啡同B，火箭SHA1df733…对应最新用户五维各4分；不扩大到不同文本 |
| Agent/plugin范围 | 最终生产变更列表无Agent/plugin路径；仅使用既有共享TaskManager和应用启动基础，不增加Agent接口 |
| 隐私 | 证据仅摘要/hash/脱敏日志；staged扫描通过，未提交Key、模型/运行时、venv、node_modules、图片或DB |
| 清理 | 模型/应用进程已停止、五个临时源码worktree已移除、三个本轮Linux根已删除；Windows五个剩余临时根递归删除被自动审批拒绝，待处理 |

浏览器协议第一次在报告AJAX尚未完成时检查条目数；明确等待报告加载后，当前真实任务三条written及3/3计数均已确认。该观察时序问题不替代功能验证，也未修改生产源码或复用旧根。

## 可复现命令

下面以`<fresh_root>`表示一个不存在的新目录；源码采用候选commit的干净worktree。环境、安装与构建日志及源/模型SHA见证据包。GitHub网络Git命令使用既定11809代理。

```text
git worktree add --detach <fresh_root>/source 8986b9e
uv python install 3.11.15 --no-cache --no-bin
uv venv --python <fresh_python> <fresh_root>/.venv --no-cache
python tools/download_caption_rebuild_inputs.py --manifest docs/evidence/natural-language-captioning/phase-4-real-evaluation/phase5-frozen-inputs.json --root <fresh_root>/inputs
uv pip install --python <fresh_root>/.venv/Scripts/python.exe --no-cache --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r requirements.txt torch==2.7.0+cpu pytest==9.1.1
Node22/npm: ci; run typecheck; run lint; test -- --maxWorkers=2; run build
python tools/run_caption_scope_tests.py --root <fresh_root>/backend-tests
python tools/verify_caption_real_tag.py --root <fresh_root>/real-tag --samples <fresh_root>/inputs/samples --manifest <manifest> --tag-models <fresh_root>/inputs/tag-models --commit 8986b9e --rebuild-inputs <fresh_root>/inputs
python tools/verify_caption_production.py --root <fresh_root>/real-natural --samples <fresh_root>/inputs/samples --manifest <manifest> --commit 8986b9e --local --assets <fresh_root>/inputs/vision --runtime <fresh_root>/inputs/runtime/llama-server.exe --rebuild-inputs <fresh_root>/inputs
python tools/serve_caption_acceptance.py --root <fresh_root>/zero-state --frontend-dist frontend/dist --port 28765
python tools/serve_caption_acceptance.py --root <fresh_root>/http-state --frontend-dist frontend/dist --port 28766 --rebuild-inputs <fresh_root>/inputs
python tools/verify_caption_rebuild_http.py --root <fresh_root> --port 28766
```

Python安装目录、npm cache、HF cache、user_data/translation/queue/输出均设为本轮新根。所有功能命令均使用新venv，前端使用Node22.17.1。四个Linux原case用独立新Python3.11.15/venv/候选源码；仅OpenCV以同4.8.1.78的headless包装满足Linux无libGL环境，不改原测试或替换symlink为junction。

## 剩余门

自动审批两次拒绝Windows递归清理，原始理由均为`blocked by policy`，未提供更具体原因。已经改用允许的Git逐个移除本轮临时源码树，未改用其他语言/工具绕过Windows删除拒绝。剩余五个沙盒仅含本轮公开样本、模型、依赖、缓存、配置和本地测试输出，没有真实远程Key。

需要用户手动删除五个剩余Windows根，或明确批准保留为清理例外。此前“4分all，全部通过”绑定人工评分与四项测试环境，不自动扩大为尚未发生的清理拒绝批准。其余完成条件不需要再次确认。整体goal保持active；收到处理结果后更新清理报告及最终门，才可以complete。
