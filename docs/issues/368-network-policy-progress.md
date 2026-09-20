# Issue #368 执行记录

## 最新授权与人工验收

- 用户在真实源码服务中完成插件下载人工验收，反馈下载速度合格。
- 用户随后明确授权 commit/push、向 Issue #368 发布修复结果、创建面向 dev 的 PR；下方未提交状态为早期阶段记录。
- 提交范围仅含本次代码、测试、前端构建产物与验收文档，不含运行时插件目录、缓存、日志或原用户 stash。
- 未完成新整合包从零安装、旧版升级覆盖及 main 独有更新器整合验收；提交说明必须保留这些边界。

## 目标与基线

- 在同一工作区从 origin/dev b4df253 创建 fix/368-download-network-policy，修复代理发现与下载链路不一致。
- 原 main 的 build_portable.ps1 修改保存在 stash（preserve local build_portable change before issue-368 dev sync），禁止丢弃；旧子模块 dataset-tag-editor 保持原状。
- 已授权：实现、测试。未执行推送、PR、合并或发布。
- 方法：源码排查 + 行为回归测试；跨模块标准修复，沿用 Issue #368 及评论中已批准方案。

## 实施与验证映射

| 项目 | 输出/验证 | 状态 |
| --- | --- | --- |
| 统一 NetworkPolicy，auto/system/manual/direct，镜像独立 | 代理优先级、NO_PROXY、注册表缺项、PAC、认证脱敏测试 | 已完成；见最终验收记录 |
| HTTP 显式代理，保留校验/续传/取消 | 本地 HTTP/代理、Range、缓存、签名既有回归 | 已完成本地验证；发布边界见最终验收记录 |
| Git 共享适配器，浅 fetch、临时错误重试、安全恢复 | 本地真实 Git 仓库及故障注入测试 | 已完成本地验证；发布边界见最终验收记录 |
| 引擎 uv/pip/模型/更新网络接入 | 入口清单与安装回归 | 已完成本地验证；发布边界见最终验收记录 |
| 配置与诊断 UI | API、安全边界、前端检查与构建 | 已完成本地验证；发布边界见最终验收记录 |
| 集成验证与发布边界 | Windows 实际小流量验证；main 独有 portable_git.py 发布整合检查 | 已完成本地验证；发布边界见最终验收记录 |

## 已知状态

- 第一轮只有 download_sources.py 等十个文件的局部修改，尚未完整实现方案。
- 11 项基础测试通过；安装器回归 63 项通过、1 项 mock 参数失败（已尝试调整，待复验）。
- 系统 Python 3.14 + Pydantic 2 不兼容现有项目，插件市场测试收集失败；改用兼容环境，不能将收集失败算通过。
- 第一轮 Git 失败后直接删除目标目录、不区分错误，HTTP NO_PROXY 处理不完整、代理字段可能泄露到 metadata：本轮优先修正，不保留这些不完整实现。
- 下一步：实现并验证共享网络策略与适配器，再迁移调用方。

## 2026-09-20 增量续接记录（以此节覆盖上方早期状态）

- 当前实现：新增 mikazuki/networking/{policy,http,git,events,api,process,model_worker}.py；旧 download_sources.py 的初版代理代码已移除，保留原镜像契约并转发新策略。
- policy 支持 auto/system/manual/direct、Windows 注册表单项缺失、NO_PROXY/CIDR/loopback/PAC 提示、URL 脱敏；HTTP 使用逐请求/重定向代理 handler；Git 用 init+浅 fetch+detach、临时故障重试，拒绝覆盖脏缓存，不递归删除目录。
- 安装器：Anima/Musubi/AI Toolkit 接入 Git 适配器，uv/pip 接入进程环境；marketplace catalog/assets/package、update_check、tokenizer HTTP 接入适配器。模型下载通过隔离 worker 运行 SDK。
- 配置：/api/network/settings 复用宿主令牌与同源保护，config/network.local.json 不入 Git/打包；引擎和插件市场均有 NetworkSettingsPanel，市场进度显示线路/尝试/速率。
- scripts/network_run.py 桥接 portable launcher/Git updater；PowerShell updater common 读取同一策略。批处理带空格路径与退出码已 smoke：返回 7 正确。
- dev upstream 识别失败的原因：原 remote.origin.fetch 只包含 main。已仅追加 dev refspec 并配置 dev 的 upstream；当前 fix 分支不变。
- 验证：兼容 venv .runtime/issue368-venv（Python 3.11/Pydantic 1）；首批 97 passed；网络+集成 70 passed；市场扩大回归最初 88 passed/1 failed/1 skipped，失败是 read1 保留完整短读导致旧 1MiB 对齐断言失效，已改为真实接收量，待最终汇总复验。
- frontend npm run check：33 files/210 tests passed，类型/Lint/build 成功，仅现有 EngineStatusBar 默认属性警告及 bundle 体积警告；生成 dist 保留以供源码宿主直接测试。
- .runtime/issue368-live.log：HTTP 自动系统代理11807，206/65536字节/2.36s；Git 手动11809 ls-remote HEAD成功/1.7s（GitHub Git诊断按技能强制11809）。未全量重装数GB引擎依赖，未运行训练。
- 原 stash 与未跟踪旧子模块保持；没有 commit/push/PR/发布/issue更新。
- 剩余：统一任务策略快照、异常诊断收口；最终后端汇总回归与前端桌面/移动预览；架构入口清单/发布边界与最终结果文档。main 独有 portable_git.py 必须在 dev→main 整合时复核，不能在此分支声称已修改不存在的文件。
- 下一步：完成最终异常边界检查并运行汇总回归。

## 最终本地验收（2026-09-20）

- 用户明确限定：只修复与验收，不向 dev 提交 PR；没有 commit/push/PR/合并。
- 已完成任务级策略快照、配置异常终态、HTTP 错误分类、SDK 启动环境反馈回路修复、原敏感来源 URL 的 metadata 脱敏。
- 后端最终 223 passed / 1 skipped / 2 subtests passed；唯一 skip 因缺少外部插件构建工件，明确保留。
- 前端完整检查 210 passed；桌面/移动 Edge 预览通过，接口 fixture 无页面错误/横向溢出。
- 全量模型/引擎重装与真实更新覆盖不在此次本地运行验证内，不能声称整合包发布验收通过。
- 完整结果与入口清单见 `368-network-policy-verification.md`。本轮本地修复交付；后续若用户启动发布验收，再进行工件构建、全量安装及 main 差异整合。
