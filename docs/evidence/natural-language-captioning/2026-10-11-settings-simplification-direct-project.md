# 设置收敛与当前项目直接启动验收

日期：2026-10-11。范围：用户手测后的设置收敛和直接运行当前分支；采用行为回归、相关后端契约和浏览器验收。历史 goal 已结束，本记录不引用旧沙盒验收证明新修改完成。

## 问题与最终行为

上一轮没有实现用户这轮设置要求，而是启动了旧沙盒。本次补齐源码并重新构建，运行 `E:/OpenSourceTeamWork/workspace/branches/feat-NL-Captioning` 的真实 FastAPI 应用及 lifespan，地址 `http://127.0.0.1:28000/dataset/tagger`。28767 的 U6 沙盒服务及其原模型进程已停止，未发现其他 sandbox 项目服务残留。

| 要求 | 实现与证据 |
| --- | --- |
| 精简打标页 | 删除本地兜底、Tag/Caption 递归勾选；两种请求缺省递归；参数初始化和恢复为 1024/0.7；预览路径在启动按钮下方 |
| 统一高级设置 | 翻译缓存、打标缓存和本地兜底缺省开启；折叠高级设置集中控制，保留已保存的关闭值 |
| LLM 模型管理 | 所有入口复用同一管理组件，模型卡默认折叠，仅摘要名及启用开关；本地状态、大小、内存说明和安装/启停入口并入受管模型卡 |
| 固定翻译提示词 | 前端移除修改项，实际 Tag 翻译统一使用内部 DEFAULT_SYSTEM_PROMPT；旧存储值保留兼容，但不能覆盖执行提示词 |
| 自动能力检测 | 不展示 text/vision 勾选框；内置几何图片和文本诊断检测实际能力，仅真实成功的能力可参与生产路由；文本成功、视觉失败仍可翻译；CAS 阻止配置变化后的旧验证写入 |
| 共享兜底有效 | 编辑页也移除重复开关。浏览器关闭高级兜底并保存后，真实翻译接口返回 409/llm_not_ready，没有使用已运行本地模型；之后已恢复为 true |

当前模型为用户指定的 Qwen3.5-2B Q4_K_M、同 revision F16 mmproj、llama.cpp b11327。仅复制并核验旧环境的模型与 runtime 资源，未迁移沙盒配置、Key 或数据库。当前真实模型服务端口 4283，模型、投影和 executable 均位于当前项目资产目录；文本和视觉诊断通过，health=ok。现有模型体积为 1.82 GiB；该模型未做峰值内存选型探针，显示“未测定”，不沿用旧 Qwen3-VL 的 3.1 GB。

## 验证

- Node 22.17.1 完整 `npm run check`：67 文件、428 项全部通过，typecheck/lint/build 通过。两个原有 EngineStatusBar lint warning 与 bundle 大小提示仍存在，无新增 error。
- 最终改动模型内存提示后再次生产 build 成功。生成资源由当前项目直接托管，浏览器读取新资源。
- 最终相关后端组合：19 个文件、199 passed、4 个既有弃用 warning，无失败或跳过。覆盖共享配置、能力自动探测及 CAS、翻译固定提示词、关闭兜底、API/JSON/密钥/本地模型、Caption/Tag 默认与任务。
- 浏览器实测：模型管理按钮名称正确；两类缓存和兜底缺省开启；模型卡与高级设置折叠；模型状态卡合并；自然语言参数实际为 1024/0.7；递归控件缺失；预览路径实际位于启动按钮下方；API 设置页复用同一管理组件。
- 390px 视口检查：折叠卡和启用控件可用，无页面横向溢出。桌面截图位于项目 `.runtime/llm-management-20261011.png`。
- 当前 HTTP `/api/version` 为 success/3.2.0-dev；主服务真实 listener PID 37860，本地模型 PID 44076。PID 是本次运行快照，重新启停后以 listener 为准。28767 无 listener。
- 项目 `.runtime/start-direct.ps1` 和 `.runtime/stop-direct.ps1` 已实际验证启动和优雅停止；辅助脚本、环境、日志及截图均保留在 ignored `.runtime`，后续无需沙盒。
- 用户原有 `tests/test_diffsynth_review.py` 改动保持原样。未更改 Agent、插件或训练实现，未自动提交或推送。frontend/dist 的变更是本次构建输出，不能把引用新资源的 index 与被忽略的新 js 分开提交。

## 启动副作用的恢复边界

此前误用 gui.py 引发全局 Python 3.14 的依赖安装，已停止该启动方式。根据原会话实际 pip 输出，rich、tensorboard、protobuf、uvicorn、websockets、h11、httpcore、httpx、python-multipart、numpy 共十项已逐个恢复到原版本，并验证 httpx/httpcore/numpy 正常导入；本轮新增且已证实原先不存在的 wheel、google-auth-oauthlib 已移除。

opencv-python 4.8.1.78 的原先状态缺少可靠输出，未猜测其原版或擅自卸载，不能声称整份全局环境完全还原。当前项目使用项目内 Python 3.11.15 与独立 .venv，pip check 无冲突，功能运行不依赖全局 Python 3.14。

## 手验交付

状态：自动验收通过，当前主项目已启动，用户手验待进行。重点检查打标页简洁布局、1024/0.7 默认值、模型卡折叠与启用、高级缓存/兜底保存、本地状态和启停，以及自然语言整句翻译。远程 Key 按当前项目配置在后端运行时注入，未从沙盒迁移凭据。

本轮是设置和管理交互验收，没有重复模型选型或整个项目从零重建活动。人工通过结论由用户后续提供。

## 2026-10-12 API 设置复选框显示修复

用户截图及当前生产页复现：API 页面模型卡的“启用”框为约 49×40px，文字超出卡片。根因是嵌入的共用 LLM 管理组件继承了 `.settings-card input` 的文本框样式（100% 宽度、40px 最小高度）。同一规则影响本地/远程模型启用及高级设置的三个复选框。

采用 Lite bugfix、行为验收及只读审查；验收范围为设置页和共用管理弹窗的控件尺寸、文本包含关系、窄屏布局及启用/折叠交互。仅修改 `frontend/src/styles/settings.css`：文本框规则排除 checkbox/radio，共用 LLM 复选框明确 16×16px、无最小高度/内边距/外边距、固定 flex 尺寸；保留键盘 focus 样式。回退时只撤销这两处 CSS 变化，保留此前未提交改动。

- Node 22.17.1 的 `npm run build`（含类型检查）通过，生成当前项目生产资源；只有既有 bundle 大小提示。日志 `.runtime/api-settings-checkbox-build-20261012.log`。
- 实际浏览器回归通过：1655px 和 390px 的 API 页，本地及未保存远程模型卡、高级设置三项全部 16×16px，启用文字位于卡片内，页面无横向溢出；文本字段仍保留正常输入框高度。勾选模型启用不会改变卡片折叠状态。验证用接口/启用草稿已还原，没有保存测试配置。
- 共用 LLM 管理弹窗在桌面和 390px 下全部复选框 16×16px，无横向溢出。当前服务继续使用原运行进程，前端构建后刷新即载入新资源。
- 截图 `.runtime/api-settings-checkbox-fixed-desktop-20261012.png` 与 `.runtime/api-settings-checkbox-fixed-mobile-20261012.png`。纯样式修复使用实际浏览器测量和截图验收，没有新增不能检测 CSS 布局的 jsdom 测试，未重复后端或模型质量测试。

修复完成；用户可刷新 `http://127.0.0.1:28000/settings/api` 继续手测。

## 2026-10-12 标签编辑翻译设置与模型管理入口

用户手测发现 Tag 单图编辑侧栏没有明显的翻译设置按钮。当前版本仅把 Tag 翻译设置放在顶部齿轮菜单中，而自然语言侧栏已有按钮；翻译设置内部只有跳转 API 页的链接，无法留在编辑器内管理 LLM。

本轮采用 Lite 功能修复、行为回归与生产浏览器验收。验收要求：Tag 中文释义开关右侧显示“翻译设置”；自然语言保留同一入口；翻译设置提供“LLM模型管理”，使用现有共用配置组件；管理期间只显示当前层弹窗，关闭后返回翻译设置；保存后重新读取共用路由/能力/本地状态，取消不得保存配置或丢失 caption 草稿。保护此前未提交改动及用户数据，不改后端或训练/Agent 实现。

实现完成：`TagTranslationControls.vue` 在开关后发出 `openSettings`；`TagTranslationSettingsDialog.vue` 的管理按钮发出 `manageLlm`；`DatasetEditorPage.vue` 打开 `capability="text"` 的共用管理组件，暂时隐藏翻译设置，管理关闭后返回。Element Plus 关闭动画发出的 `update:modelValue=false` 已单独处理，避免返回目标被清掉。管理保存/测试/本地运行事件携带的共用配置直接更新编辑器，旧配置请求通过 generation 失效；离开 KeepAlive 页时关闭弹窗，生命周期版本阻止迟到刷新重新打开。

- 新 `DatasetEditorTranslationSettings.test.ts` 6 项行为回归通过：Tag 入口不触发翻译；取消管理不保存配置或 Caption、保留原文草稿；自然语言保存后使用新路由/兜底翻译当前草稿；本地运行操作刷新文本可用状态；离开时迟到状态不重开弹窗；旧配置回复不覆盖保存结果。既有编辑工作流与共用模型管理仍通过。
- Node 22.17.1 完整 `npm run check`：68 文件、443 项全部通过，类型检查、lint（无 error）与生产构建成功。日志 `.runtime/editor-translation-entry-check-20261012.log`。完整检查首次包含新增 fixture 的三条 lint warning；随后仅调整测试替身类型，新增文件 ESLint 零警告（`.runtime/editor-translation-entry-fixture-check-20261012.log`），类型检查和新 6 项测试再次通过，最终仅保留 `EngineStatusBar` 两条既有 warning。业务源码未再修改，生产资源仍与其相符。
- 实际 28000 生产页：用户当前 320px Tag 侧栏显示 66×32px 的翻译设置按钮，位于中文释义开关右侧。截图 `.runtime/editor-translation-entry-direct-20261012.png`；设置内入口截图 `.runtime/editor-translation-entry-settings-20261012.png`。
- 独立浏览器 context 使用 `.runtime` 几何样本检查 Tag 与自然语言：直接打开设置与模型管理、仅显示一层弹窗、管理取消返回设置、编辑器 route 与 Caption 草稿不变，未发送配置保存、原文保存或翻译请求。验证脚本 `.runtime/editor-translation-entry-browser-20261012.js`；用户当前数据集与浏览器编辑会话保留。
- 390px 下新增按钮保持在侧栏内且没有增加页面宽度。发现既有分页器/侧栏布局使整页宽度为约 408px；隐藏新增按钮并恢复原工具栏样式仍为 408px，因此不能声明整个编辑页已解决窄屏横向溢出。本轮只处理翻译设置及管理入口，该既有布局问题留作后续维护。
- 独立只读复审通过，`git diff --check` 通过。用户 `tests/test_diffsynth_review.py` 既有 12 增/3 删保留。没有后端/模型调用行为修改，未重复后端测试或模型质量评估。

当前项目已加载本轮生产构建，状态：入口功能及自动验收完成，用户可刷新 `http://127.0.0.1:28000/dataset/editor` 后手测侧栏设置及管理往返。
