# Issue #368：本地修复与验收结果

## 范围与交付状态

在 `fix/368-download-network-policy` 实现，基线为 `origin/dev` 的 `b4df253`。最初交付范围为本地修改与测试；用户完成下载人工验收后，已授权提交、推送、创建面向 dev 的 PR，并在 Issue #368 发布结果。不包含合并或发布整合包。原 main 上的打包脚本修改保存在 stash，旧 `mikazuki/dataset-tag-editor/` 目录未改动。

## 已实现

| 入口 | 接入方式 | 验证 |
| --- | --- | --- |
| 插件目录、插件 ZIP、托管 assets | `HttpDownloadAdapter` 显式代理；保留业务层签名/大小/SHA-256/Range/缓存/取消 | 本地 HTTP、代理重定向、错误、续传与安装 API 回归 |
| Anima Fast / Musubi / AI Toolkit 源码 | `GitDownloadAdapter`，指定提交浅 fetch、断连重试、脏目录保护、恢复已 init 的缓存 | 本地真实 Git 仓库旧提交获取/浅历史/缓存保护；故障注入；GitHub 小流量探测 |
| uv / pip / Python 环境安装 | 显式进程环境，任务策略快照、代理清理、日志脱敏 | 三种引擎安装器现有回归 |
| 模型资源下载 | 独立 SDK worker 继承策略，不热修改主进程环境 | 真实 worker 空任务协议与环境隔离测试、模型资产回归 |
| 更新检查与 tokenizer HTTP | 共享 HTTP 传输 | 既有更新/缓存测试 |
| 便携启动器与 Git 更新器 | `scripts/network_run.py`，由子进程继承代理 | 带空格批处理路径与退出码实测 |
| PowerShell release 更新器 | common helper 读取同一解析器的环境 JSON | PowerShell 语法检查；打包脚本回归 |
| 服务端设置与 UI | 受保护 `/api/network/settings`，插件市场/引擎页共用；配置不写入 Git/发布包 | API 鉴权/持久化/非法配置测试；前端类型、Lint、测试、构建；桌面/移动预览 |

网络模式为 `auto/system/manual/direct`；镜像仍是独立下载源配置。`auto` 读取调用参数/保存设置、环境代理、Windows 静态系统代理；仅有 `NO_PROXY` 不再屏蔽系统代理。`direct` 清理代理环境并对 native 客户端使用 `NO_PROXY=*`。本地回环始终绕过代理；PAC 只诊断提示，不执行脚本。

代理端口不硬编码。本次机器自动识别为 11807，其他用户以自身系统配置为准。手动界面不保存用户名密码；认证代理可使用宿主环境变量。任务 metadata 和日志中的 URL 认证及查询信息脱敏。

HTTP 读取从 1 MiB 阻塞读取改为最多 64 KiB 的 `read1`，尽快上报已经到达的数据。短读也保留进 `.part`；重试 offset 是实际接收量，最终完整性校验不变。**取消后的跨任务续传语义没有扩大**，仍遵循已有临时文件清理规则，完整校验 ZIP 可以复用。

新下载任务读取新设置；已运行任务使用策略快照。第三方 SDK 的宿主启动环境只初始化一次，不在并行任务期间热改全局环境；宿主内长期 SDK 如需变更继承环境应重启。独立模型 worker 与引擎安装任务不需要重启宿主来取得新配置。

## 验收证据

- 后端最终汇总：**223 passed、1 skipped、2 subtests passed**。日志：`.runtime/issue368-final-backend.log`。
- 跳过项：`tests/test_plugin_marketplace_api.py:1086`，需要未随源码提供的 Agent 插件构建脚本和 ZIP 工件。没有将其计为通过。
- 前端 `npm run check`：**33 个测试文件、210 项测试通过**；类型检查、Lint、生产构建通过。日志：`.runtime/issue368-frontend.log`。已有 EngineStatusBar 属性默认值提示和 bundle 体积提示仍存在。
- 浏览器：本机 Edge headless 预览 1440px 桌面与 390px 移动端，配置读取/保存成功，无 JS pageerror，无横向溢出。接口使用受控 fixture；真实后端鉴权/保存由 API 测试覆盖。截图：`.runtime/issue368-desktop.png`、`.runtime/issue368-mobile.png`。
- 真实 HTTP：自动识别 Windows 11807 代理，GitHub Release Range 请求返回 **206、65,536 字节、2.36 秒**。
- 真实 Git：按本会话 GitHub Git 网络规则显式通过 11809，`ls-remote` 成功，约 **1.7 秒**；不将其称为 11807 Git 全量克隆测速。记录在 `.runtime/issue368-live.log`。
- 批处理代理桥接：带空格路径可执行，保留子脚本退出码 7。
- release 内置 Python 3.10：可导入新的策略、HTTP 和 Git 模块；运行环境识别为 auto。
- `git diff --check` 与 PowerShell helper 语法检查通过。

## 验收边界

- 人工验收：用户在修复分支的真实前后端中测试 Next Trainer Agent v0.3.9 下载，明确反馈“验收通过，下载速度合格”。服务使用专用 Python 环境、真实 release 插件频道，网络 API 确认自动读取系统代理。此次未在操作前核验缓存清空状态，因此不认定为从零整合包验收，也不将用户反馈扩大为独立核验完整安装流程。

- 没有在测试中的 release 目录修改文件、重启应用或中断现有安装。
- 没有全量重新安装数 GB 的 Anima/CUDA/FlashAttention 环境，也没有执行训练；已验证对应安装命令/环境链路及真实小流量网络，不声称完成整合包全量验收。
- 没有运行真实更新覆盖工作区/整合包的破坏性流程；更新器验证限于策略桥接、语法、既有脚本回归。
- 当前 dev 不含 main 独有的 `scripts/portable/portable_git.py`。将来 dev→main 整合时必须复核其网络入口；不在本次分支伪造或移植整个 main 更新器。
- 此方案不能保证源站、代理服务或第三方镜像始终可用，也不能自动控制第三方库中忽略代理环境的自建网络连接；错误会按已接入适配器报告，新增客户端必须单独接入。

## 维护约束

新增业务下载必须调用网络策略与传输适配器，或通过受控子进程环境运行第三方 SDK。保留业务特有的签名、大小、哈希和原子安装流程，不把网络层重试当作完整性保证。宿主 loopback RPC、模型推理服务调用与开发维护脚本不应盲目套用公共文件下载重试策略。

实现核对参考：[Python ProxyHandler](https://docs.python.org/3/library/urllib.request.html#urllib.request.ProxyHandler)、[Git 配置文档](https://git-scm.com/docs/git-config)、[uv 环境变量](https://docs.astral.sh/uv/configuration/environment/)。
