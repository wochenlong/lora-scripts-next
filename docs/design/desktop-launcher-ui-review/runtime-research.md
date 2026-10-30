# 启停状态延迟：源码调研与设计建议

日期：2026-10-30。工作副本：`E:/OpenSourceTeamWork/workspace/branches/dev`，分支 `feat/desktop-launcher`，研究基线 `31849ae004ccd92dc190ae644dd1530a888454c2`。

本轮只读源码并设计，未修改启动器产品、未操作正在使用的沙盒、未触发服务启停或训练。下列耗时目标是待实现后验证的指标，不是本轮已测成绩。

## 1. 结论

用户观察与当前代码完全吻合。运行状态和安装完整性被装在同一个 `Report` 中；启动已经成功后仍做一次昂贵安装扫描，停止已经完成后前端也重新等待同一全量扫描。日志由独立事件即时显示，而按钮只能等完整命令返回后更新，因此两者长期不同步。

优化重点是让运行状态直接反映受管进程与健康事实，移除启停完成后的冗余扫描；启动前已有的源码、Python、环境、资料绑定和进程归属校验仍保留。调整刷新频率本身不能解决此问题。

## 2. 已证实的源码证据

| 现象/原因 | 当前调用链与精确位置 |
| --- | --- |
| UI 等整个启动命令返回才收到新状态 | `desktop-launcher/src/App.vue:286` 的 `perform()` 设置 `pending`，只有 action 完成才在 finally 清空；`:298` 的 `command()` 直接等待 `runCommand()` 后调用 `acceptReport()`；`:358` 发起 `start_trainer` |
| 成功日志早于状态返回 | `desktop-launcher/src-tauri/src/core.rs:1935` 的 `Engine::start()`，`:2049` 输出“真实训练器就绪”，`:2060` 保存健康绑定事务，`:2061` 继续 `self.inspect(root)`，而后才返回 `Report` |
| 启动前已有必要校验 | `core.rs:1936` 网络策略，`:1938` 固定清单启用授权，`:1939` mutable/租约，`:1940` 资料绑定环境检查，`:1944` verify_source，`:1945` check_environment，`:1946` runtime_view::prepare；`:2038` 真实健康接口与 Job 监听归属，`:2045` 版本一致性 |
| 启动后 inspect 重复验证当前版本 | `core.rs:1498` `inspect()`，`:1514` managed_python，`:1519` verify_source，`:1524` check_environment；`:1548` 遍历全部 release，`:1550` 再次 verify_source，`:1551` 再次 check_environment。当前版本在同一 inspect 内至少重复一次源码及环境校验 |
| 环境检查不是小查询 | `core.rs:504` `check_environment()`，`:507` 完整基础 Python 校验；`:518` `instances::assert_usable()`；`:545`–`:552` 新开独立 Python 导入大量关键包。`instances.rs:2261` `assert_usable()`，`:2268` Python 树摘要，`:2269` 环境全树扫描对比。`python_integrity.rs:317`/`:323` 校验完整解释器树；`source_integrity.rs:87`/`:154` 校验可信源码文件摘要与树结构 |
| 停止后主动发起全量 inspect 才更新 UI | `App.vue:366` stop，`:368` `await stopTrainer()`，`:369` 再 `await runCommand('inspect', root)`；旧 report 仍保留 running/healthy，pending 也未清空 |
| 按钮被旧 report 与全局 busy 一起限制 | `App.vue:74` busy 包含 pending，`:77` running 仅依赖 report.running，`:107` primaryDisabled 包含 busy/running，`:612` “停止”依赖 running、“在浏览器打开”依赖 healthy、“启动”仅在 !running 时存在，以上都受 busy 限制 |
| 日志和状态没有共同事件 | `bridge.ts:61` `listenToLogs()` 仅订阅 `launcher:log`；`main.rs:1188`–`:1189` 发该事件。`App.vue:197` `addLog()` 只加文本，不更新 report；`:577` 订阅日志；没有 runtime 事件或常规 runtime 轮询 |
| 单个大锁会使新增轻量查询继续排队 | `main.rs:31` Runtime 的 `engine: Arc<Mutex<Engine>>`；`:819` action 用 spawn_blocking，但`:820` 得到 Engine mutex 后一直持有到 start/inspect 返回；`:913` stop 同样抢这把锁。spawn_blocking 仅避免阻塞异步执行器，不缩短 UI 状态等待 |
| 异常退出只能等下一次操作被发现 | `core.rs:1489` reap 在 inspect/mutable/url 等入口才执行；当前没有常驻退出通知。`core.rs:136` Running 保存 child/root/port/Job/lease；`:145` Drop 杀并等待 child，字段随后按声明顺序释放 Job 和 lease |
| 打开网页当前已有即时再验证 | `core.rs:2072` `url()` 会 reap、确认监听端口属于 Job、实际 health；`main.rs:977` 的 `open_trainer()` 调用 url 后才交给 Windows 打开浏览器，可继续保留 |

`inspect` 的“健康查询”本身也排在源码/环境检查后（`core.rs:1529`–`:1539`），所以不能把现有 inspect 作为 250ms/500ms 的运行状态轮询。

## 3. 尚未实测的部分

- 本轮没有做新的启动/停止时间采样，不将用户观察量化成固定秒数。
- `mark_healthy()` 本身也可能耗时：`data_import.rs:1618`–`:1650` 要核绑定并写可恢复事务；需实现阶段单独埋点区分健康返回、健康提交和尾部 inspect。不能未经测量断言全部时间都来自某一个函数。
- Job 关闭会回收后代，但 `stop()` 目前只无返回值地 `take()` Running。新“已停止”定义应核本次受管进程组已排空、租约已释放；不能仅依据根 child 已退出或日志文本断言全部后代结束。

## 4. 推荐接口与职责

### 4.1 两种状态各管各的事

**安装状态 `InstallationAssessment`**：源码、Python、环境、前端、版本列表、资料绑定、修复结果、校验时间/状态。由安装、修复、版本切换和显式检查更新；耗时检查有独立进度，保持既有实际校验强度。

**运行状态 `RuntimeSnapshot`**：只表示本次受管服务。字段建议为 `workspace_id/root`、`release_id`、`instance_id`、`binding_generation`、`run_id`（每次启动唯一）、`seq`（该工作区单调增长）、`phase`、`pid`、`port/url`、`version`、`exit_code`、`last_error`、`observed_at`。只读 pid/handle/Job、已验证启动上下文和必要的本机 health，不读取归档/全树、不运行关键包 imports。

新增 `launcher:runtime` 结构化事件和 `runtime_status(root)` 轻量快照。事件驱动显示；快照用于首次订阅、重连和丢事件兜底。日志不解析为状态源。

`RuntimeSnapshot` 必须有独立短锁/共享状态，不与长时完整性扫描共用 Engine 大锁。运行所有权仍由后端统一管理；可使用单独 lifecycle worker/actor 持有 child+Job+lease，再发布不可变快照。HTTP health 不在快照读取锁内执行，更不能每次渲染触发新的 health 请求。

### 4.2 启动流程

1. 点击后立即显示 `checking`（正在检查启动条件），保持导航/日志页可用，禁用冲突的安装变更和重复启动。
2. 依照当前合同完成固定清单授权、租约、源码/Python/环境/资料绑定等启动前校验；在同一启动内复用已有验证结果构造安装快照，不通过尾部 inspect 重读相同文件。
3. 创建受管子进程后进入 `starting`（正在启动，等待服务）；后端 watcher 继续观察本次 child/Job 和 health。要能接受“取消启动”，由 owner 取消当前 run 并排空本次 Job。
4. 本次 Job 归属 + `/api/version` success + 版本一致通过后，完成必要健康绑定事务；提交成功才发布 `ready` 并返回/结束启动命令。保留 health-success 与 transaction-committed 两个时间点，日志“就绪”与最终 ready 语义一致。
5. UI 收到匹配的 runtime ready 就显示并启用“打开训练器”和“停止服务”；不等待版本列表刷新、环境检查或完整报告。

不把启动前完整性检查取消或改成未经验证的旧缓存。本设计的确定性提速在“已成功后的冗余等待”；若后续要跨启动复用完整性证明，必须另行设计可信失效机制并明确评审，不能只比 mtime 或依赖文件监听无事件就当作可信。

### 4.3 停止流程

1. 点击后立即显示 `stopping`（正在停止），禁用本次启动/重复停止，日志页和其他只读导航可用。
2. owner 终止本次受管 Job，核子进程组排空、回收 handles/lease；不执行源码/环境完整性扫描。
3. 后端发布 `stopped`（或 `stop_failed`，保留可恢复上下文），停止命令返回 RuntimeSnapshot；UI 收到 stopped 立即恢复“启动训练器”。
4. 安装状态需要复核时，单独进入 `checking` 标记并在环境页展示；它不掩盖实际已经停止的事实。下一次启动仍由后端启动前校验兜底。

## 5. 状态机与按钮

| Runtime phase | 主操作 | 次操作/提示 |
| --- | --- | --- |
| stopped | 启动训练器（安装状态正常时） | 环境待检查/需修复时去环境页；日志入口始终可用 |
| checking | 正在检查… | 查看日志；若该阶段已设计取消则显示取消检查 |
| starting | 正在启动… | 取消启动、查看日志 |
| ready | 打开训练器 | 停止服务、复制地址、查看日志 |
| degraded | 重新检查连接 | 保留停止服务；提示“进程仍在运行，服务暂不可达”，不能显示可再次启动 |
| stopping | 正在停止… | 查看日志；不复用 ready 的打开按钮 |
| start_failed / exited | 重试启动（仍需经过启动校验） | 最近失败摘要和“查看日志”定位该 run |
| stop_failed | 继续停止/查看详情 | 不伪装已停止，不释放新的并发启动许可 |

runtime 与完整性状态正交：服务已ready时后续后台环境诊断不能仅因“检查中”把网页按钮隐藏；但外部文件损坏属于明确异常，需要提示并按运行保护合同处理，不能回写“所有文件已验证”。

## 6. 竞态与资源归属

- 订阅再读取快照，并使用 `run_id+seq` 幂等归并。工作区/版本/实例不匹配或 seq 更旧的事件不接受。旧 run 的迟到健康回调不能覆盖新 run/stopping。
- 每个 frontend 请求有 request epoch；安装目录变化/组件卸载后忽略旧结果。当前 acceptReport 会回写 path，新方案须防止旧检查把用户重新切回旧目录。
- 同一工作区生命周期动作串行；快速连续点击通过后端 operation/run 身份幂等处理。不能仅依赖前端 disabled 防重复。
- `ready` 之前必须核本次 Job 的监听者与版本；进程ID复用/端口被抢占均不能成为 ready。保留 URL 打开时的拥有者/health 验证。
- 进程退出 watcher 立即发 `exited`，取消该 run 未完成的 health，回收 Job 后代并释放lease。健康偶发失败保留 running，标 degraded，不当作 stopped；恢复后可返回 ready。
- 日志事件携带 run_id/source/level/seq，避免多个工作区串日志；UI 状态不能由“启动成功”某行字符串猜测。
- 前台状态转换期可 500ms 取轻量快照兜底；稳定运行期 2s/窗口恢复时刷新；非活动后台减频或停轮询。所有快照来自已维护状态，不重复起完整检查。health watcher 串行、有界超时、不叠请求。
- 分离“生命周期进行中”“安装写操作进行中”“完整检查进行中”。这些决定哪些按钮冲突，不能继续用一个全局 busy 把日志/导航/已就绪的打开动作全部封锁。

## 7. 最短实施顺序（待用户批准设计后）

1. 加 RuntimeSnapshot/结构化事件，分离长时安装检查锁与 runtime 发布锁；启动前校验不变，启动后删除尾部 inspect，停止后返回快照；同一 inspect 内去掉当前版本重复验证（不跨调用缓存）。
2. App 以 runtime 管理启停/打开按钮，移除 stop 后全量 inspect 的等待；轻量快照兜底与 run/seq 去旧；保留状态与安装/修复页各自刷新。
3. 随视觉重构加入日志独立路由；各页去除底部长日志区，只留一行阶段/错误摘要+“查看日志”链接，链接带操作/run定位且保留过滤状态与滚动位置。

## 8. 可量化精简验收

以下为设计目标，实施后应由同一高精度时钟埋点与原生UI检查验证，不能仅用“感觉变快”。

| 检查 | 提议目标 |
| --- | --- |
| 点击启动/停止 → 局部过渡状态可见 | 目标≤100ms，允许上限250ms；不等待任何IPC结果才变文字 |
| 必要健康绑定提交成功 + 本次owned服务健康 → 网页按钮可用 | 目标≤250ms，允许上限1s；期间不执行新的全量inspect |
| 本次受管进程组排空 + lease释放 → 启动按钮可用 | 目标≤250ms，允许上限1s；不等待环境扫描 |
| 静默异常退出 → UI不再显示ready | 目标≤1s（事件）；丢事件时≤2s兜底；过渡过程不得误报stopped而进程仍在 |
| 导航到日志 / 切回首页 | 目标≤100ms，允许上限250ms；不得重新触发全量校验 |
| 运行快照请求 | 本地目标p95≤50ms；零源码/Python/venv全树hash、零imports探针；health异步观察，不占读锁 |

实施验收只需：同一最终新包原生正常启停3轮并记录上述延迟、一次受管子进程意外退出、一次端口归属/版本不符拒绝（可定向夹具）、乱序/旧run/目录切换/事件丢失的状态归并定向测试。原有必要源码/环境篡改拒绝用1–2项已有回归保持；不重下模型、不重跑GPU训练和四引擎训练矩阵。日志页验证跨页保留/过滤/暂停跟随/错误跳转，确保最终页面不再挂长日志面板。

本轮结论为“调研已完成，实施待设计审阅”；不是性能优化已落地或新延迟目标已通过。
