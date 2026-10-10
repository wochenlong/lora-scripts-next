# 提示词预设统一控制验收记录

日期：2026-10-10。分支：feat/NL-Captioning。交付为工作树增量，没有新增提交或推送。

## 需求与结果

用户要求移除重复的输出语言控制，提示词预设统一决定语言与输出格式。页面已经移除独立语言和详略下拉框，内置预设名称明确详细/简短；只读显示预设语言和纯文本 .txt 落盘格式。自定义提示词继承当前预设语言，保存/另存保留该属性。用户先选择目标语言预设再编辑即可创建对应语言模板。

切换模型不再自动更改预设语言。不支持预设语言的模型显示提示并禁用试标/批量。实际请求的 language、完整 user/system prompt、字符上限来自同一预设草稿；后端协议和严格 JSON/正文语言校验保持，失败重试使用原任务快照。

## 验证矩阵

| 项目 | 状态 | 证据 |
|---|---|---|
| 打标页面专项：语言/详略预设、草稿取消、自定义属性、试标/批量一致、不兼容模型 | pass | TaggerPage.caption.test.ts，26项 |
| Node22 前端完整 typecheck/lint/test/build | pass | frontend-check.log：53文件、349项；2条既有 lint warning、构建体积提示 |
| Python3.11 后端 Caption 测试组 | pass | backend-caption.log：133 passed，4条既有警告 |
| 手测项目自身 Node22 构建 | pass | 手测根 preset-controls-build.log |
| 浏览器真实界面：无独立语言/详略下拉、中英简短完整模板、撤销切换保留草稿、预设只读属性 | pass | 实际托管页面 Playwright 检查 |
| 390px 窄屏 | pass | viewport=390，document.scrollWidth=375，无横向溢出 |
| 浏览器试标请求继承英文简短预设；不兼容中文预设禁用生成 | pass | browser-checks.json，catalog/preview 在浏览器内 mock；未启动模型 |
| HTTP/端口/服务源码身份、受保护数据文件 SHA | pass | deployment.json |
| 新增控制方式下真实远程/本地生成与用户验收 | not-run | 交用户在现有手测项目执行，不以 mock 代替真实生成 |

## 手测交付与边界

入口：http://127.0.0.1:28766/dataset/tagger。沿用 nl-caption-manual-20261009，停止自有应用后保存旧源码和 dist 至 preset-controls-backup-20261010，再仅复制13个明确文件并从手测源码构建。53个用户数据、预设、任务与配置文件在更新/重启后 SHA 保持一致。实际 API Key 不打印、不复制；服务重启后需按既有运行时契约重新注入。

没有 Agent、训练、模型下载或新服务改动；无关 test_diffsynth_review.py 保留。开发树生成的 tracked dist 已恢复。

浏览器模拟第一次使用了错误的 preview URL，等待结果超时；该次真实后端对合成无效请求返回400，未运行模型、未写标注。修正为 /api/tagger/jobs/preview 后浏览器 mock 检查通过，路由拦截已撤销并重新加载真实页面。

重点人工测试：英文详细/简短预设实际生成；中文预设切换；以英文预设为基础修改并保存自定义模板后刷新复用；试标不写TXT且批量配置相同；不兼容模型提示；Editor原文与只读中文翻译、中文免模型请求。
