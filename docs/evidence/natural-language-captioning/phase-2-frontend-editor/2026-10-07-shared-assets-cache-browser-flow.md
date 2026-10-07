# Phase 2：共享资产、缓存与实际浏览器业务增量

基线 c0c94ed；Phase 2 仍 in progress。真实模型、正式启动和 Phase 4 不由此报告替代。

## 实现

- ManagedVisionModel 是打标与共享 LLM 设置的同一个管理组件；翻译设置打开共享对话框即可操作同一 Qwen 资产，未打开或未点击安装时不会自动下载视觉模型。status 轮询单飞、离页 abort，关闭/卸载不会接收旧响应；runtime action 不覆盖未保存的远程草稿。
- 原有纯文本 LocalModelService 经 LocalTextModelService 注册到共享 profiles；启动/停止同步 readiness，实际运行状态动态校正。保留既有文本模型、runtime 和安装 API，不重复下载另一份模型。纯文本资产禁止伪报 vision；caption 能力筛选仍限制视觉。
- Qwen 视觉重启保留用户禁用标记；runtime 更新只保存 profiles，保留 cache/presets。LLM config 保存接口返回实际 readiness。
- 共享 UI 增加 translation/caption cache 开关；关闭 translation cache 同时绕过 API 前置缓存、流式结果/失败缓存和 worker 持久化，非流式仍返回实时结果。禁用缓存的 in-flight key 与启用缓存隔离。
- shared config 读取失败时禁用空草稿保存，避免把真实 profiles 意外清空。旧互斥说明修正为 remote-first/explicit fallback。
- 窄屏翻译对话框 grid 使用 minmax(0,1fr)，状态/操作按钮可换行，避免词库下载状态和按钮撑宽。
- 新增 tools/serve_caption_browser_fixture.py：fresh root、三张合成几何图片、实际 FastAPI API、fake 模型/Tag/词库/网络翻译，lifespan=off；无需真实 Key。只能证明业务集成，不能证明模型质量或隔离重建。

## 实际测试

```powershell
& <Python3.11.15-venv> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_local_text_registry.py tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
& <Python3.11.15-venv> -m pytest tests/test_local_vision_manager.py tests/test_local_text_registry.py tests/test_llm_translation_gray.py tests/test_tag_translation_api.py -q
npm exec --yes --package=node@22.17.1 -- node 'I:\NdoeJS\node_modules\npm\bin\npm-cli.js' --prefix frontend run check
```

- 相关完整 suite：221 passed / 4 warnings / 19.58s。随后视觉启停保存边界增量，最后定向16 passed / 1 warning / 1.62s。
- Node22 最终 check：51 files / 324 tests passed / 20.42s；typecheck/lint/build pass，lint 两个已有 EngineStatusBar warning；build1868 modules / 8.29s，已有 annotation/chunk 提示。
- 组件新增3场景：翻译共用视觉资产且不自动下载，runtime 刷新保留草稿，读取失败禁止保存。第一次对已完成请求断言 aborted 失败；改为在下一次未完成轮询中关闭并验证 abort，最终7个设置组件场景通过，不将失败版本当证据。
- HTTP fake 翻译测试验证关闭缓存连续两次真实 HTTP 请求、旧结果和失败记录不阻挡、旧缓存未被改写；公共 API 禁止前置读取；纯文本注册仅一次、停后not ready、拒绝vision。

## 实际浏览器验收

Vue Vite5177 + FastAPI28762 + fake provider18762；根 workspace/sandboxes/nl-caption-browser-flow-20261007，三合成图片，实际写回/journal/hash/配置接口，Tag 推理及 LLM 推理为fake。没有真实凭据/用户图片/模型下载。

- vision 列表只出现视觉接口，text-only不出现；共享设置的 caption route 同样过滤，translation route 包含两者。
- 保存/读取提示词预设；单图 strict JSON 视觉连接测试通过；natural preview 显示结果，磁盘仍0个caption。
- natural 批量 total3/succeeded3，实际3个写回，UI显示3/3；报告3行，显示profile/prompt revision/before-after hash，没有私有计划/目录/响应内容。
- 修改视觉profile名称、关闭caption cache后保存；后端实际读取更名且cache.caption=false，提示词预设未丢失。
- fake单次429被默认一次HTTP重试恢复，3/3成功；连续两次429触发同批 succeeded2/failed1；UI错误与重试按钮可用；点击retry只处理1项，parent_job_id关联失败批，succeeded1/failed0。
- 延迟10秒请求时点击中止，phase=cancelled/succeeded1/cancelled2，UI同步取消数量。测试操作间隔使第一项已完成，不能宣称0项写回。取消后combined preview及批量继续正常。
- combined preview确实包含Tag+自然段落；combined批量succeeded3，三个文件均有mixed分隔。
- Dataset Editor实际扫描显示mixed安全提示，禁用Tag清理；原文编辑保留自然段落前空白；undo恢复初始hash、redo恢复保存hash，逐字节匹配。
- 扫描后外部修改sample-1.txt，再页面保存收到409/caption_conflict和中文刷新提示，外部内容仍保持。console该409是预期错误；没有应用异常。不能说全程console 0 errors。
- 翻译页面共享设置读到上述更名profile和caption cache=false，text-only连接测试可用且严格JSON成功；Tab从测试按钮进入删除按钮，Escape只关闭内层，保留外层对话框，动画后数量由2降到1。
- 390×844窄屏：共享dialog宽374.39/scrollWidth374；外层翻译dialog修正前宽366.59/scrollWidth466，修正后scrollWidth367，document scrollWidth390。不将立即HMR前的读数当修正结果。
- 初始fixture翻译控件继承浏览器已有启用/auto偏好，触发词库下载；已显式取消该测试根下载并关闭翻译开关。随后fixture增加词库与网络翻译替身，fresh -r2根HTTP验证preview不写盘、combined3图写回、共享LLM实时翻译和无词库下载全部通过。初始测试不能称完全无外部网络。
- Windows取消fake HTTP请求出现ConnectionAbortedError测试线程输出，新增该分支捕获；正式client/job取消已成功。初次r2验证脚本误用/tagger/preview得到405，改为真实/tagger/jobs/preview后退出0。
- r1/r2两个自建后端及Vite均已停止；GGUF/SQLite/样本/测试状态文件不入Git；tracked dist构建后恢复基线。

## 完成门仍缺

完整profile新增/删除/能力切换与取消、更多键盘/窄屏页面操作、真正重启后的恢复和历史选择、编辑器半批失败的前端刷新；旧翻译提示词/推理选项UI兼容还需审计，安全job回滚/清理仍待实现。Stage3真实远程/本地中文评测、EDD/Zero-Short/完整失败闭环和Stage4从零重建仍未执行。宽范围11失败/21跳过无豁免。
