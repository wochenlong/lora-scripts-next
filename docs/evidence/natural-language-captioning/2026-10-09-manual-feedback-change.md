# 手动验收反馈：英文优先与自然语言译文

用户2026-10-09反馈并直接授权：远程生成成功但Editor原文有时为空；本地英文选择仍返回中文；英文提示词实测可改善输出；自然语言需要中文译文，但继续禁用Tag操作，中文无需调用模型。

这是原goal完成后的修复与新增功能，原完成历史保留。当前状态：complete-with-existing-platform-boundary；已提交并同步手测项目。分支feat/NL-Captioning，既有tests/test_diffsynth_review.py修改保留。

| 验收项 | 实施/验证 |
|---|---|
| 原文正确显示 | 修复scan重新水合造成空草稿的顺序错误；重新进入Editor读取磁盘，保护真正未保存草稿；提供恢复磁盘原文入口 |
| 英文优先 | 新任务默认en；内置英文/中文模板及System prompt随语言切换，自定义草稿不静默覆盖 |
| 实际输出语言 | en返回中文正文即合同错误，禁止写回/缓存；既有JSON、截断/语言验证保留 |
| 自然语言译文 | 独立整句文本翻译、共用LLM text路由/密钥/运行时/SQLite，远程优先、本地显式兜底；不走Tag词库/拆分 |
| 中文短路 | 中英文混合保守判断，中文正文直接显示且不调用模型，后端再校验 |
| 前端安全 | 译文只读，不覆盖原文；切换图片/编辑/关闭时取消并隔离过期响应；Tag操作继续禁用 |
| 验证与交付 | 合同/HTTP与前端回归、真实本地英文三图与文本翻译、浏览器外部生成再加载/语言切换；更新保留沙盒，保留用户数据 |

开发方法：沿用integrated-development-workflow，BDD与确定性回归，真实LLM输出作EDD探测。新的有限修复不重新创建原goal或扩展到Agent/plugin。

唯一下一步：实施上述变更并完成针对性与相关完整回归。


真实补验首轮：迁移产生的无Key text远程占位配置被当成候选，实际fallback模型cache无法按远程revision命中；新译文路由在请求快照中排除此类外部接口，持久配置不变。新增合同验证后r2重启补验全部通过，保留首轮fail报告。不重用原goal人工4分评价新英文输出，r2只记录自动语言/功能检查。浏览器早期协议对隐藏的ElSwitch input和缺少llm:前缀型号定位错误，修正为实际可见控件/型号后完成；窄屏实测client375/body380的5px溢出真实修复，最终client/body均375。


## 最终结果与交付

候选81e85d7f88e230829fba94d4def2dec80d59d6b7。前端53文件347项、typecheck/lint/build通过，两个既有EngineStatusBar warning。候选后端53文件533项：529通过、四个原Windows WinError1314失败、0skip、17subtests；同四个case/安全路径组件均未修改，沿用此前用户批准的平台组合边界，未在本轮新跑Linux，不声称Windows原生通过。

真实Qwen3-VL-2B三图默认en均生成英文正文（3/3），真实中文整句翻译成功；缓存回放命中，原始TXT逐SHA不变，模型停止后中文短路仍成功。浏览器16项通过：原文显示/默认展开、Tag chips与批量Tag禁用、译文不改原文、中文0翻译请求、草稿恢复、外部生成后重新加载、English默认/英中模板及System prompt切换、最终390px client/body均375，无pageerror。

新模型输出只做自动语言/功能检验，没有冒用旧中文描述人工分数。本轮新增远程译文没有真实Key注入或付费请求，远程优先/fallback由合同与已有共享LLM回归覆盖，用户需重新输入Key继续远程手测。不宣称重新进行完整Phase5 fresh重建。

原手测源码已切到81e85d7并从源码重新构建，28766应用重启就绪。用户4个数据集、21个文件在升级前后逐SHA相同；预设/任务状态继续使用原state，不重新初始化。中文短路及新OpenAPI英文默认接口已在实际交付服务验证；独立BrowserContext读用户实际remote-english目录，原文、译文入口与禁用Tag批量均确认，未写用户文件。早期交付检查使用旧目录名caption-samples失败；按用户已改名的实际目录检查后通过，不改用户目录名。28767补验服务及视觉模型已停止，私有日志/截图留在手测根。原tests/test_diffsynth_review.py未提交或恢复；Agent/plugin生产零变更，没有push。

机器摘要：[测试、真实模型与交付](2026-10-09-natural-translation-results.json)、[浏览器](2026-10-09-natural-translation-browser.json)。用户下一步：Ctrl+F5刷新页面、重新输入后端运行时API Key，在自然语言原文面板开启中文译文；旧空草稿可通过恢复磁盘原文按钮明确丢弃。
