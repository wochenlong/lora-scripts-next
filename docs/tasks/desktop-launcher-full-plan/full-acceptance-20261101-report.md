# 桌面启动器全量验收报告（执行中稿）

本轮由代理自动执行沙盒验收，覆盖启动器的按钮、条件入口、设置、版本与环境管理、日志、托盘和原生窗口功能，保存截图及机器可核对的报告。**验收尚未全部通过。**以下计数保留 validate04 原冻结时点，后文记录后来实际完成的 `interim02` 证据包与新原生终态；该中间包不构成最终业务签收。用户无需补做手动验收；后续结果继续以真实终态刷新本稿。

本稿的汇总时点为 **2026-11-01 11:05:16（北京时间，UTC+8）**，对应 `acceptance-delivery-validate-final06-04.json` 的生成时间 `2026-11-01T03:05:16.236302+00:00`。该快照之后的执行、补证和文档更新不自动计入以下数字，最终稿必须重新冻结输入并重新生成汇总。

## 范围与实际包身份

固定盘点为 227 行：App 页面与公共控件 117 行、环境与恢复等功能 88 行、原生窗口与系统交互 22 行。四个训练引擎的 13 类动作另展开为 52 个单元；这是固定清单中引擎模板的展开视图，**不与 227 相加**。盘点依据见[按钮与功能清单](full-acceptance-20261101-inventory.md)，执行边界见[任务书](full-acceptance-20261101-task-book.md)。

| 项目 | 实际记录 |
| --- | --- |
| 开发分支 | `feat/desktop-launcher` |
| 当前候选 | `FINAL06`，开发候选，尚非公开发行签收 |
| 启动器产品提交 | `4e1b4cc78939e8b906252b27dcc20692ad347a08` |
| 候选 EXE SHA256 | `11804c053d8667b1c9b91512d72055481aeb27d58be2ac32d181ede42413cbca` |
| 固定训练器 dev 源码提交 | `4e68df240c63ab7cf2156ea7fafabf18df4671e8` |
| 正式候选目录 | `F:/NextTrainerLauncherSandbox/full-acceptance-20261101/package-final-06` |
| 本轮沙盒总根 | `F:/NextTrainerLauncherSandbox/full-acceptance-20261101` |
| 原始证据总根 | `E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101` |

[候选身份文件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/final06-package-identity.json)记录实际 EXE、交付清单与分发文件摘要。FINAL06 部署时核对了 portable 九个文件的实际内容身份；构建与部署核对不等同于全部原生功能验收。

本轮**没有开启真实训练**。安装、检查、修复、重建、导入、运行网页服务与允许的导入探针可以实测，GPU 训练结果不属于本轮通过条件。依赖安装、目录存在、计划可见、任务请求已发送，以及日志中出现成功文字，均不能单独作为功能成功的依据。

本轮使用主机 Windows 上的独立功能沙盒与自有数据根，主机已有 WebView2。新安装根和空缓存场景不等于全新 Windows 虚拟机；本稿不据此宣称无 WebView2 系统的首次部署或跨机器兼容性已验证。

## validate04 时点的结果

| 验收状态 | 固定 227 行 | 四引擎 52 单元 |
| --- | ---: | ---: |
| 通过 `pass` | 180 | 0 |
| 部分通过 `partial` | 20 | 0 |
| 失败 `fail` | 5 | 4 |
| 受阻 `blocked` | 11 | 22 |
| 未测 `not-run` | 8 | 11 |
| 待复核 `pending-review` | 3 | 15 |
| 合计 | 227 | 52 |

以上是对 **FINAL06 候选可签收范围**的汇总，已叠加实际包身份、必要分支、证据完整性与源码影响审查。历史包上真实成功的安装或检查仍保留原始事实；其涉及已修改的引擎 worker（后台校验进程）、恢复流程或配方时，不自动升级为 FINAL06 通过。因此，52 单元中尚无完整候选签收，不表示四个引擎从未执行过安装或维护。

该次验证纳入 282 条精确证据记录（proof，即绑定原报告位置、实际包身份与截图的记录），其中 276 条为通过观察；记录数量不是完整功能或按钮覆盖数量。候选身份核验为真，引用核验 `warnings=[]`、`errors=[]`，输入文件运行前后 SHA 一致，验证耗时约 5.54 秒，`acceptance_complete=false`。详见[快照 JSON](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-04.json)及[执行与输入身份记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-04-run.json)。

## 按钮至少一次操作与完整业务验收分别统计

另行只读审计了 App 的 117 行，结果见[逐行交互覆盖](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/app-interaction-coverage.json)。该审计保留每行对应的原报告 Pointer、实际 EXE 和截图，不使用证据记录总数量充当按钮数量，也不改变严格业务裁定。

| App 行的交互事实 | 行数 | 含义 |
| --- | ---: | --- |
| 已有真实 UI 触发 | 112 | 包含触发后业务成功、正确拒绝和业务失败；后两者不能据此签成功 |
| 真实启动或偏好回退行为 | 2 | 此两行属于启动/状态行为，不是额外独立按钮 |
| 明确预期的 disabled 保护已核 | 2 | 不支持版本安装及当前／上一健康版本删除保护；此类保护不要求派发 enabled 点击 |
| 未找到真实交互记录 | 1 | `APP-ENV-005`，见下文 |
| 合计 | 117 | 116 行有 UI 或 disabled 事实；本表已含后续真实日志恢复入口，不覆盖开头 validate04 历史计数 |

真正尚未找到交互证据的是主程序失败摘要中的“查看高级选项”`APP-ENV-005`，需要形成真实检查失败摘要后点击，核展开、滚动与错误保留；普通高级展开按钮不能替代它。日志页“查看恢复”`APP-LOG-022` 后来已在真实持久故障和正式完整检查后点击，进入环境管理并展开高级；其同案恢复失败与整体宿主失败单列如下，导航成功不代表恢复成功。

后来的 `versions-dual-final06-03` 已通过正式 main 安装、健康 main 切换、dev 警告窗取消／确认与真实版本回退，关闭了这四条成功链的缺口；原 main 安装失败及旧 dev disabled-only 前置仍保留历史身份。`APP-VER-008` 的 dev 专属结构损坏／占用拒绝尚未实测，不能由成功切换或损坏 main 拒绝推导通过。

当前8个 App 部分通过项的剩余功能逐项保留，不能用“同名按钮点过一次”代替；源码检查只判断可达性，不授予 UI 通过。

| 部分通过项 | 仍未取得的实测及可达性 |
| --- | --- |
| `APP-HOME-011` | 轻量 `not_run` 冷启是真实可达、已准备独立补测；旧89启动依赖合法完整旧版环境，本轮资源未具备，仍 blocked |
| `APP-HOME-015` | `stop_failed` 重试只在真实受管 Job 终止或回收失败时出现；未制造操作系统失败或注入假状态，保 not-run |
| `APP-HOME-020`／`APP-LOG-023` | 保存临界区取消、重复／任务已结束回执依赖短时竞争。真实 UI 在 cancel_requested 后 disabled、任务终态移除按钮；未强行调用隐藏处理函数或伪造 IPC，尚无该窄窗采样 |
| `APP-VER-008` | 已知结构坏、运行服务或其他变更进行中会禁用切换；真正独立 lease 的后端拒绝需要另构前置。成功切换不替代这些保护观察 |
| `APP-ENV-001`／`APP-ENV-003` | 半装、绑定目录丢失、单包、基础Python、多包损坏，以及简化主确认／本页停止后修复均为真实业务入口；ENV 专案继续逐分支实测 |
| `APP-BASE-001` | 完整报告与轻量概况先后返回由 epoch 机制防覆盖，是内部异步竞争；实际导航已测，尚未确定采样全部响应先后组合，未注入延迟假响应 |

全启动器的“每按钮一遍”分母单列生产源码不可达项。`GUI-LIFE-07` 依赖 `history.status=rollback_pending`，当前后端只产生 `ready/pending`；[源码交叉审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/inventory-cross-review.json) 的 `/findings/0`（`XR-01`）记录该条件在当前产品不可达，且禁止注入假 IPC 使其显示。因此按 **226 个可达项加 1 个当前不适用／不可达项**呈现。该项是源码审查排除，不是一次 UI disabled 验证；不得混成可测试但漏测，也不得先行声称其余 226 项都已覆盖。严格完整功能与四引擎 52 单元仍按实际状态保留。

## 已修复的问题及验证边界

| 问题与用户可见影响 | 已完成的修复和实测 | FINAL06 的签收边界 |
| --- | --- | --- |
| 异步确认窗、引擎确认窗的初始焦点或取消后归焦不可靠 | 修正 App 与引擎确认窗焦点时序；FINAL03 及定向重测保存真实交互证据 | 前端与相关控件真实构建输入未变，按具体 proof 影响审查继承；旧截图保留旧包身份 |
| 损坏偏好文件导致冷启动 panic | 修复冷启动容错、错误显示和重新读取；FINAL03 四条原生场景通过 | 不以旧 focus01 正常偏好操作代替损坏偏好分支；采用对应正式复测证据 |
| 源码修复预览扫描大环境时触发文件、总容量或节点数量限制 | 预览不再冒称已采保护摘要；正式执行仍完整保护非目标内容；超过 5GiB 的受保护内容及 50,001 文件资源回归、FINAL04 真实源码修复通过 | 采用 FINAL04 实际执行与未变相关模块的精确审查，不从早期预览推导执行成功 |
| 已装引擎 receipt 与编译锁对 Python 派生字节码的处理不一致，阻断主程序维护 | 对齐原始 Python 文件合同，保持原件内容核验；FINAL04 单包和源码修复真实复验通过 | 不将该历史结果扩大为 FINAL06 四引擎所有维护动作通过 |
| 资料组合恢复忽略输入事务编号，可能恢复非目标事务 | 校验输入与实际事务编号；FINAL05 验证非法、未知、正确及重复恢复，保存前后字节证据 | 03/04 旧错误编号分支不继承为通过；采用 05 的精确新案 |
| 引擎恢复在完整复验前发布旧绑定，超时后可能丢失 pending 状态 | FINAL06 改为先完整验证候选旧状态，最后发布绑定；取消、超时和未知状态保留恢复入口。后来 DiffSynth 单窗维护取得真实中断重建→恢复 passed 终态 | 此新事实只覆盖该实际 DiffSynth 引擎分支，不能扩大为四引擎恢复全通过。相关主程序 MAIN06 旧案在前置检查阶段被中断，仍不能称其恢复执行成功或失败 |
| AI Toolkit 配方同时安装两个 OpenCV provider，原件不同导致完整性拒绝 | 对固定官方水印源码作正式发行期依赖补丁，构建 `0.2.0+nexttrainer.1`；两个独立构建所得 wheel 字节相同；141 包、273 条活跃依赖及原件冲突离线审查完成。后来 FINAL06 正式首次安装任务 succeeded，写入 generation1=validated1 的 ready 状态 | 后台安装成功与 UI 整案失败分列：原确认分支因 AI 按钮 locator 不在而失败，原图显示版本管理，页面变化来源 unknown；不据后台 ready 签完整 UI、`pip check` 或健康探针通过 |
| 引擎完整观测重复读取同一文件，增加检查与安装耗时 | FINAL06 同轮完整树内容摘要供 wheel、RECORD 和全树核对复用；保留完整 SHA、路径、CRC 及派生文件合同，未调宽原超时条件 | 差分与源码回归已完成；不宣称未在同环境测得的加速倍数，最终安装/维护仍需真实终态 |

本轮已保留 App 的严格 117 行裁定，以及逐具体 proof 的旧包→FINAL06 适用性审查。dual03／SET06及后续日志专用入口纳入后，App 严格结果为 **108 通过、8 部分通过、1 未测**，共155条精确 proof；其中原133条旧包适用审查及8条不继承记录内容保持不变，新增14条为 FINAL06 直接实测。未继承项包括缺实际构建清单的早期包证据、涉及新 worker 的只读引擎证据、原始安装失败与未匹配的早期原生分支。该增量不把旧 EXE 或截图改名为 FINAL06 实测，也不覆盖 validate04／interim02 的冻结计数。

对应原件：[App 严格裁定](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/app-full-adjudication.json)、[App 影响审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/final06-delivery-impact-review-app.json)、[环境影响审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/final06-delivery-impact-review-environment.json)、[原生功能影响审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/final06-delivery-impact-review-native.json)。这些工作文件可以继续增量更新；validate04 自身的输入 SHA 保存在其独立运行记录中。

## 后续 FINAL06 原生终态：后台成功与界面失败分列

下面两案晚于开头 validate04 及已导出的 `interim02` 冻结时点，尚未合并进前述旧计数。它们均由正式 UI 提交真实安装或重建，实际包 SHA 为同一 FINAL06；**后台任务已成功不抵消原 UI 分支与整案失败**。未开启训练，未调宽原超时、完整性合同或产品保护，也没有修改原报告。

| 原案与原件 | 正式后台事实 | 原 UI 与回收事实 |
| --- | --- | --- |
| [DiffSynth 重建终态](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/diff06-terminal-adjudication.json)；[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-diffsynth-rebuild-01/environment-report.json) `/checks/0` | 任务 `download-1793502113-226340-0` 为 succeeded，新实例 `tb5679596546441b` 为 ready、generation2=validated2、dirty=false、pending=null；receipt SHA 为 `ab7bd4ab9a77b777ab22fdff5f8fa0d39a46e9a1221bf4245e079f22b0c62ea8` | 安装后的自动完整只读检查仍“正在检查…”，超出原 900 秒 UI 等待限值；原 ENG-09 failed、原 host passed=false 保留。[原失败图](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-diffsynth-rebuild-01/screenshots/004-ENG-09-FAILED.png)显示该检查状态。node exit1、启动器 exit0、自有 Job 已排空为0、CDP 与服务回收 |
| [AI Toolkit 首次安装终态](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/ai06-terminal-adjudication.json)；[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-ai-toolkit-install-maintain-01/environment-report.json) `/checks/0`–`/checks/3` | 正式首次安装解析并安装141包，任务 `download-1793504765-228968-0` 为 succeeded；新实例 `t26c3fd14699a493` 为 ready、generation1=validated1、dirty=false、pending=null；receipt SHA 为 `b9674acd9de48788dfa658c29dae2f8cbb6a12836e732206934f838864f629f2` | `/checks/0` 安装预览、`/checks/1` 文件／依赖详情和 `/checks/2` 取消／Escape／Tab焦点循环三分支 passed；`/checks/3` 安装确认原 failed。[原失败图](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-ai-toolkit-install-maintain-01/screenshots/006-ENG-01-FAILED.png)显示**版本管理页**，AI 行 locator 连续30秒未找到；页面变化来源 unknown，不能解释成900秒查询超时或内容校验失败。host 精确终态为 `2026-11-01T04:11:47.421728+00:00`；node exit1、启动器 exit0、自有 Job 已排空为0、CDP 与服务回收 |

两张失败原图已作实际像素复核，观察范围见[本次视觉边界记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/app-native-terminal-visual-review-01.json)：AI 图可见“版本管理”和2个已安装版本，不能冒称 AI 安装成功页面；DiffSynth 图显示“正在检查…”及禁用按钮，不能冒称检查通过。执行中截图也不能替代完成截图。AI 前三分支只支持该专用引擎 UI 的对应事实，不能偷换成 `App.vue` 全局版本／主程序确认窗的成功证据；52单元由环境功能裁定继续更新。

AI 后续只读检查、精准修复、运行探针、占用／恢复等维护因原确认分支失败而未执行。DiffSynth 后续维护使用另一独立原案，后来已取得下面记录的成功终态。随后双版本、设置集成及剩余专用入口亦按主控单 GUI 顺序推进，只有真实终态才能更新严格结果；准备配置和调度顺序不计通过。

DiffSynth 单窗维护新案的[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-diffsynth-maintain-01/environment-report.json)在 `2026-11-01T05:25:58.452Z` 终态为 passed，9个精确分支均 passed：`/checks/0` 无 pending 的受控异常、`/checks/1` 真实目标 lease 占用与无关引擎只读／计划、`/checks/2` 健康主按钮、`/checks/3` 收起再展开、`/checks/4` 高级区、`/checks/5` 文件只读检查、`/checks/6` 真实源码精准修复、`/checks/7` 真实导入探针且无训练、`/checks/8` 真实中断重建再恢复。共有16张该案原截图。[host 原件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/native-engine-final06-diffsynth-maintain-01/host-status.json)于 `2026-11-01T05:25:59.664688+00:00` 终态 passed，node exit0、启动器 exit0、自有 Job 已排空为0、CDP3824回收；本案未启动网页服务，`service_ports=[]`。

该案的实际 EXE 为 FINAL06，未开启训练；占用分支中无关 Kohya 只进入正式安装计划，没有执行其安装，也没有以此证明其他引擎维护通过。新案成功不改写此前 DiffSynth 安装后 UI 查询超时、AI 跳页未知及其原 host 失败；后续汇总必须同时保留这些失败，并按精确功能范围纳入新通过证据。开头 validate04 与已导出的 interim02 仍是旧快照，尚未包含这9个新终态。

[独立终态旁证](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/diff06-maintenance-terminal-adjudication.json)另保留4个实际任务的完整快照：源码 repair 和 import probe succeeded、真实新实例 rebuild cancelled、recover succeeded。最后 pending 新实例 `t14fab6052b6d439` 为 generation4，正式恢复回 `tb5679596546441b` 的 generation3=validated3、pending=null、dirty=false；旧收据摘要匹配。该恢复通过不替代尚未在同案执行的依赖包缺损修复。

## 后续 FINAL06 双健康版本与设置父组件集成终态

`versions-dual-final06-03` 已于 `2026-11-01T05:40:16.682Z` 完成，**10/10 分支 passed**；[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/versions-dual-final06-03/native-report.json) SHA为 `4b31c1036a7405395bf5bae417702746edbe52f1c31aa345a7da4f9ca03b7204`。这不是将两个版本标记成健康的夹具：原中断 dev 按产品规则清理后正式重新下载安装，legacy main 使用固定原始 find-links 正式安装，两者分别完整检查、真实 HTML/API200 并正常停止。最终 current 为 `dev-4e68df240c63ab7cf2156ea7fafabf18df4671e8`，previous-known-good 为 `main-0785419e7dc1a3058bd8710a9aa933fec0aabdee`，两个真实版本均 installed/known_good；原资料摘要保持。

| 原报告位置 | 实际 UI 与后台证据 |
| --- | --- |
| `/checks/0`—`/checks/5` | 原磁盘 Running 保留且产品历史转 Interrupted；正式删除未激活 dev，再安装 dev 和 main，分别完整检查与 ready、HTML/API200、停止 |
| `/checks/6` | `App.vue` 全局 dev 警告窗三次打开：自动 Cancel 初焦，真实 Tab／Shift+Tab 完整环绕索引均为 `[1,0]`，Escape 归焦；第二次真实点击取消归焦；第三次普通 primary 确认切换 |
| `/checks/7` | 当前 dev 和上一真实健康 main 删除按钮同时 disabled，上一健康保护原因可核 |
| `/checks/8`—`/checks/9` | 正式回退健康 main、完整检查，再经真实确认恢复 dev；绑定、双健康记录及原资料保持 |

[dual03 host 原件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/versions-dual-final06-03/host-status.json)于 `2026-11-01T05:40:17.543196+00:00` 终态 passed；node0、启动器0，自有 Job 排空为0，CDP5857及真实服务2826/8390全部回收。[ROOT 独立核对](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/dual03-terminal-root-check.json)保留最终双健康与端口检查。dev 警告窗没有长路径 pre，不能据此宣称长溢出路径的真实键盘滚动已测；其 dev 结构损坏／占用拒绝仍未测。原 dual01 下载缓存竞争、dual02 同期退出及旧 main 安装失败原件保持不变。

`settings-integration-final06-dual01` 随后于 `2026-11-01T05:41:38.625Z` 完成，**3/3 分支 passed**；[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/settings-integration-final06-dual01/native-report.json) SHA为 `dd8fdb1e30737fbf5238650f46978f5a1120f575e20f64c9f046ac5227d3d8df`。`/checks/0` 在真实服务 API200 前后，核资料复制、组合切换、资料恢复，以及 Trust/Shell 变更控件全部 disabled，未强点；`/checks/1` 真正点击 Trust“检查更新”，父级 `not_run→complete`，完整检查明细可见，原 profiles 和版本绑定保持；`/checks/2` 真正复制105字节微型资料到新的未激活资料集 `settings-integration-236996`，receipt committed、activated=false，并自动触发父级 `complete→not_run`，没有显式 refresh 或 inspect。

两种父组件刷新合同按源码和实际终态分别签收：ImportPanel 由 `operate` 提交正式资料任务，任务终态后父组件读取轻量概况；父组件没有为其绑定 `changed`。TrustPanel 的 `changed` 才触发完整 `inspect`。微型复制的计划废弃通过更改资料集名称触发生产 watcher，ImportPanel 没有取消按钮，不编造点击取消。收据事务为 `data-import-settings-integration-236996-1312d7761ffe2bfb`，任务 `download-1793511697-236996-0` repair succeeded；源资料、原 profiles、registry、profile-bindings、当前／上一版本保持。历史 DATA-05 仅展开清单、DATA-10 未独立记录父刷新，与本次新终态保留各自范围。

[SET06 host 原件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/settings-integration-final06-dual01/host-status.json)于 `2026-11-01T05:41:39.267686+00:00` 终态 passed；node0、启动器0、自有 Job 排空为0，CDP8796及真实服务9978全部回收。[ROOT 独立核对](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/settings06-terminal-root-check.json)保留三分支与端口状态。[另一代理只读窄审](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/app-dual03-set06-independent-review-01.json)重新核13条 direct proof、精确 Pointer、全部图像摘要和回收记录，并实际查看dev初窗／确认、导入前后4张图片，结论为指定范围通过。以上两案没有开启训练，不代表全部117行已通过；它们及前述 DiffSynth 新案尚未进入旧 interim02 冻结包。

[ROOT 两图像素复核](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/root-dual03-set06-visual-review-01.json)另实际查看dev键盘循环截图与导入完成后截图：前者显示取消按钮焦点轮廓，整段按键序列依原 JSON；后者显示用户资料页、新未激活资料集名称及“完整性未检查”，receipt 的复制归属依原 JSON。像素复核不增加任何业务 pass。

## 后续 FINAL06 基础Python专用恢复终态

[基础组件恢复新案](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-final06-base-existing-01/environment-report.json)的 `/checks/0` 于 `2026-11-01T05:57:22.464Z` passed，原报告 SHA 为 `58c0c839b500ef91b113187d16e803314c4c291ff139d0ca7e6d704cd9277f11`。这是针对既有真实 `publishing` 事务 `base-python-30f5c68bcedae069786f7b5c`，实际点击“继续未完成组件恢复”及“继续恢复与逐环境校验”；[独立按钮事件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-final06-base-existing-01/environment-button-events.json)记录两次 DOM 点击与对应前后截图。任务 `download-1793512467-228420-0` succeeded，intent 成为 committed，原 `_bz2` 文件 SHA `23fd67eadaf93e1786bca36ac03a26277b32957e43b15d148ff043d019846083` 由产品恢复，两引用实例分别 generation4=validated4、generation3=validated3，均 dirty=false、pending=null；原事务保持，没有由 harness 改写产品状态。

[该案 host](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-final06-base-existing-01/host-status.json) SHA 为 `8eb7ea63ad33b13a7c0903df76e948332683d1e244d261609853e6199f1ac94b`，于 `2026-11-01T05:57:23.735126+00:00` passed：node0、启动器0、自有 Job 排空为0、CDP7588关闭；本案未启动网页服务或真实训练。该新终态只覆盖 `GUI-BASE-04` 专用恢复，不能替代 `APP-ENV-001` 简化主按钮基础Python分类，也不能替代 `APP-LOG-022` 日志页“查看恢复”的点击；原基础组件故障案的导航失败与该日志入口未测继续保留。第07轮汇总早于此案，尚未包含这一新恢复 proof。

另两项同包故障恢复后来取得终态，按具体入口分别记录。

| 原件与精确位置 | 实际恢复与回收 |
| --- | --- |
| [依赖包提交故障与恢复](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-fault-final06-package-01/environment-report.json)，`/checks/0` 与 `/checks/2`；原 SHA `d47da13ae106ff54848f0925749ae1936c18a4d0bb2c040c80e4e44b9884d4b9` | 正式 absl-py 2.5.1 修复遇受控登记原子替换失败，原 failed 任务和 committing intent 保留；随后真实专用恢复按钮及确认触发任务 `download-1793512989-234940-1` succeeded，generation5 恢复。故障检验与恢复各自 passed，不把原预期失败任务改成功。[host](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-fault-final06-package-01/host-status.json) 于 `2026-11-01T06:04:08.486216+00:00` passed，node0/native0/Job0、CDP6278关闭，无服务启动 |
| [登记提交故障与恢复](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-fault-final06-registration-01/environment-report.json)，`/checks/0` 与 `/checks/2`；原 SHA `7098f01c814912e5fdc6a5bde52dbb44b40f9dd02a6dec9d62979493795668c0` | 登记正式提交遇受控拒绝访问后保留原 committing 事务；真实“继续未完成登记恢复”及“继续核验与补齐登记”完成任务 `download-1793513543-231372-1` succeeded，intent committed、current 未变、GUI 绑定由产品恢复。[host](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery-fault-final06-registration-01/host-status.json) 于 `2026-11-01T06:13:51.313042+00:00` passed，node0/native0/Job0、CDP1820关闭，无服务启动 |

两案 `/checks/1` 的日志“查看恢复”均因未显示专用入口保持 not-run，没有用普通环境页导航替代。它们只证明 `GUI-PKG-07` 和 `GUI-REG-05` 专用故障恢复合同，不自动签 `APP-ENV-001`／`APP-ENV-003` 简化按钮的分类与统一确认，也不签 `APP-LOG-022`。这些晚于第07轮冻结，最终汇总需等全部输入稳定后重算。

## 后续日志恢复入口通过与主程序实例恢复缺陷

[实例重建提交故障案](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-rebuild-fault-01/environment-report.json)为4/4分支 passed，其中 `/checks/3` 的真实 registry 只读锁导致正式任务 `download-1793513717-236684-0` failed、错误码 `gui_lifecycle_failed`；旧 registry 摘要保持，留下真实 `committing` 事务 `gui-rebuild-1793513736-236684-0`。这是预期故障检验通过，不能解释为新实例已经成功发布或恢复。原报告 SHA为 `8eb8fa093b1c89b3c3d8798915432536237c29cae5debca8c7a2ddbf3111c826`；[host](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-rebuild-fault-01/host-status.json)于 `2026-11-01T06:23:06.426059+00:00` passed，node0/native0/Job0、CDP5179关闭。

[恢复首次案](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-01/environment-report.json)在不相关的普通重新安装预览步骤等待对话框30秒后失败。该步骤被现有 pending 保护正确拒绝，没有实际点击恢复；这是外部套件前置路径问题，不能归为产品恢复失败。原报告 SHA为 `7de196b5bc6eaff56c261b54633b14ddc70192f5cb4e084d6c309993aef219d0`；原 host 于 `2026-11-01T06:24:17.559491+00:00` 失败，node1/native0/Job0、CDP3428关闭。该案原件保持，外部新案跳过这一步，直接读取真实实例记录并执行正式检查、日志入口及恢复。

[恢复第二案](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/environment-report.json)的 `/checks/1` 于 `2026-11-01T06:25:58.632Z` passed：真实持久故障经主程序完整检查建立 interrupted 报告，日志页出现专用 warning，实际点击“查看恢复”后进入环境管理且高级区可见。`/button_events/0` 记录真实点击返回；[警告原图](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/screenshots/003-LOG022-real-pending-after-complete-inspect.png)与[导航后原图](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/screenshots/005-APP-LOG-022-real-lifecycle-failure-after-formal-inspect-recovery-entry.png)保留可见状态。APP已实际查看导航后图片，其环境页及“收起高级选项”可见；图片本身不证明恢复完成。该精确分支作为 `APP-LOG-022` 通过采纳，原 BASE／PACKAGE／REG 三案未显示入口的 `/checks/1` not-run 各保留独立历史身份。

同案 `/checks/2` 恢复实际失败，当前有 **P1 产品缺陷**。真实内存任务 `download-1793514359-235144-0` 在 preparing 阶段以 `operation_start_failed` 结束，消息为“GUI重建事务gui-rebuild-1793513736-236684-0待恢复”；正式日志在14:25:59已显示线程结束。故障发生在任务持久化之前，因此没有新磁盘 task。外部 harness 只等待新磁盘文件，原行停在 `running`，不是后台仍在执行。[只读内存与正式日志](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/readonly-log-and-memory-0640.json)的 `/memory_snapshots/0/snapshot` 保存确切早失败终态，原报告无 `finished_at` 的未完成状态保持不变。

[另一代理独立源码核对](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/gui-rebuild-recovery-self-block-independent-review-01.json)确认根因：实例变更入口按“其他版本”调用重建就绪检查，而该检查扫描整个根目录的事务，没有筛选所属版本，因此把本次目标自身的 pending 误当其他版本冲突，在持久化和真正恢复之前拒绝。当前源码、FINAL06实际构建输入和产品提交对象摘要一致。原事务和 registry 保留；当前证据不支持数据丢失结论，也未以重复重试、伪造状态或修改操作系统绕过此保护。恢复功能仍失败，缺陷尚未修复。

恢复第二案原 raw SHA为 `665bb36dd4a96f4bd7881d4a343e63047ed6049c5e4963772b8ac97316b47f22`；[原 host](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/host-status.json) SHA为 `6e35f4ffd20bdc20e5261f108e6e9b334dce55b1f4884cf8d45783759f86edef`，于 `2026-11-01T06:47:10.185831+00:00` 失败，node1/native1、Job已排空，原 CDP 检查为 false。[独立回收复核](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/advanced-light-final06-recovery-02/terminal-readonly-check.json)于 `2026-11-01T06:56:47.295674+00:00` 重新核精确PID/代次已消失、自有唯一 Job 不存在，旧方法记录 `ports_closed[9689]=true`、`reclaimed=true`；该端口布尔值不等同于明确的 TCP 连接拒绝，单独不足以通过新合同的资源资格判断；`clean_for_independent_next_case=false` 只因原真实 pending 事务仍保留。后来的实际回收不改写原 host 失败或瞬时 CDPfalse，日志导航分支的通过也不将整案升级为通过。

独立审查发现，旧方法的端口布尔值不足以区分明确拒连与超时。随后另一代理在 `2026-11-01T07:19:52.059070+00:00` 完成[权威操作系统监听快照](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/recovery02-cleanup-os-listener-snapshot-01.json)，原 SHA 为 `e5e757423b3e3d766541f8a9a21a89d24713d54996ad79c6a1625587f010efa4`。该原件绑定同一 host、config、raw report SHA，再核同一 PID/创建代次不存在和精确 UUID Job 不存在；`/port_observations/0` 明确本案 CDP9689 的 `Get-NetTCPConnection` 全表查询成功、unknown=false、listeners=[]，服务端口清单为空。socket 的原值10035表示 Windows 超时/暂不可用，原件明确 explicit refusal=false，因此不称 TCP 连接拒绝；资源回收依据是成功的操作系统监听枚举与精确资源缺席。

[外部清理合同增量](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-cleanup-contract-delta-01.md)将 UI 子步骤行为与资源是否仍存活分开。仅当 proof 显式绑定原始 terminal 与额外 OS 快照 SHA/精确 Pointer，同时逐端口覆盖与身份、时间、PID/Job 缺席全部成立，才解除该子步骤的清理资格阻塞；原 native1/node1、整套失败与 GUI-LIFE-05 的业务失败仍原样保留。生成器与独立验包器共用纯谓词，并新增 forced/abnormal 警告。[19项合同自检](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/cleanup-contract-selfcheck-02/result.json)已实际通过，其中1项为真实原件组合，18项为内存构造的负例，覆盖错SHA、缺PID创建代次、Job存在、端口仍开、OS端口遗漏、查询未知或失败、监听仍存在。负例仅测证据合同，不是业务验收；原件摘要未变化。[NATIVE 最终独立只读审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/cleanup-reclamation-native-independent-review-01.json)已按最终代码和快照实际重放19项自检，另做9项谓词负例及4项 builder 绑定负例，结论为 `pass-with-resource-only-boundary`；同源离线验包器模板字节也已核对。该审查只批准资源资格合同，不授 GUI-LIFE-05、整套 host 或全量验收通过。

## 必须保留的失败与中断

| 原案 | 功能观察与裁定 | 原始回收结果及后续补证 |
| --- | --- | --- |
| `settings-integration-final05-01` | 旧根有 preparing 事务，启动入口不可用，harness 等待按钮超时；未提交真实启动请求，设置运行中保护与父刷新未进入 | 原 raw/host 均失败；启动器 exit0，Job、CDP 与端口回收。无该案截图，保留原 JSON，不补造 |
| `settings-integration-final05-02` | 先完成主程序完整只读检查；启动等待 360,000ms 仍“正在检查启动条件”，取消再等 180,000ms 未观测 stopped；无端口/API 成功 | 原 host 失败且自然 Job 三秒排空未通过；标题栏退出 exit0。随后关闭本案自有 Job，独立 cleanup-v2 核原 PID/代次、唯一 Job 不存在、CDP 与服务端口回收；不改写原自然排空失败 |
| `versions-dual-final06-01` | harness 在下载期间发布同名缓存，产品以“缓存目标在下载时已出现，拒绝覆盖”终止；裁为 harness 竞争与预期安全拒绝 | 原 raw/host 失败保留；exit0、Job/CDP/端口回收。未取得双健康版本，不把拒绝当安装成功 |
| `versions-dual-final06-02` | 首 dev 安装完整验证期间发生 pageclosed；未得到安装成功终态，未执行第二健康版本安装与成功切换/回退 | 原 host 失败，启动器在宿主关闭前已 exit0，Job/CDP/端口回收；仅保存下载、执行与验证进行中截图，不称失败终态页面截图 |

特别说明：`settings-integration-final05-02/native-report.json` 的 `service_started=true` 是原 harness 在提交启动请求后立即写入的**意图标记**，不是服务运行成功。原始文件保持不变，独立[解释裁定](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/settings-integration-final05-02-adjudication.json)明确 `ready_observed=false`、`port_observed=false`、`api_success_observed=false`。不能用此字段给设置运行中保护签收。

以上四案及其 config、host、截图、独立解释、cleanup-v2 和事件 JSON 已纳入 App 的历史失败索引，独立于通过 proof。导出器对白名单中的这些引用逐件保留，并核对其精确失败状态 Pointer；没有对应通过 proof 也不能遗漏历史失败。

## 三窗口同期退出与后续调度

北京时间 2026-11-01 10:55:59–10:56:04（UTC 02:55:59–02:56:04）附近，`versions-dual-final06-02`、`engine-final06-kohya-interrupted-recovery-01` 和 `recovery-fault-final05-base-04` 三个测试窗口同期退出。**退出原因仍为 unknown（未知）。**

三案分别使用独立 UUID 的自有 Job；源码审查未发现共享 Job 复用。窗口恢复、退出和托盘调用的静态范围审查也不能确定谁触发了这次历史退出。随后两条 WER 1001 事件指向 `setup.exe 156.0.4314.58` 的 `EdgeInstallerError|msedge 0x21f`，尚无与启动器退出的因果证据。系统安装器日志读取被拒绝，未为此提权或修改系统配置。

原案、进行中任务和退出记录均保留；未结束用户进程。详见[同期退出独立裁定](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/concurrent-window-exit-0256-adjudication.json)与[原始 Windows 事件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/concurrent-window-exit-0256-events.json)。后续采用**一次一个自有 GUI 宿主**的串行调度：先等待 DiffSynth FINAL06 原案终态，再执行 AI Toolkit，并按实际资源继续双版本、设置集成与轻根剩余链。调度顺序不构成这些功能已通过的依据。

## 证据与尚未完成的交付

真实按钮使用正式 WebView、原生窗口/菜单或系统对话框触发；IPC 观察和受控故障准备单独注明。截图用于呈现可见状态；隐藏行为另核任务终态、HTTP/API、文件摘要、receipt、绑定/资料前后差异，以及实际进程和监听端口。只读检查、安装预览、禁用拒绝和正式执行分别裁定，不能互相替代。

主控另对两张指定 FINAL06 图片进行了实际像素检查：DiffSynth 重建确认窗，以及中文原生托盘菜单，记录于[视觉抽查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/visual-qa-final06-01.json)。检查范围仅这两张图片：确认窗颜色、圆角、按钮、背景模糊和文字显示一致；菜单为“显示主窗口／退出启动器”。未见空白或第三方窗口。前者是确认执行前时点，后者是菜单展开时点；该抽查不代替随后业务终态、菜单点击与资源回收，也不表示所有截图均经过像素审查。

最终离线证据包计划包含固定 227 行、52 单元、逐分支裁定、精确 Pointer、实际包 SHA、截图、失败原件、回收明细、公开投影说明及独立验包器。原偏好/剪贴板备份、安装树、下载缓存、WebView 数据和 EXE 不进入证据包。需要脱敏的 JSON 另作公开投影，保留原摘要、投影摘要与删除 Pointer，不修改原件或把失败改成成功。

目前已完成导出器语法、小自检、五轮只读输入验证，以及 `interim02` 的真实导出、独立验包、浏览器预览和移动后再次验包。**交付通路已实际跑通，最终业务验收及最终冻结包仍待剩余用例。**相关工具为[证据导出器](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/build_acceptance_delivery.py)、[独立验包器](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/verify_bundle.py)和[导出合同](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-generator-contract.md)。语法、自检、引用验证和验包通过均不代表完整产品验收通过。

首次真实导出试跑 `interim01` 在创建输出目录之前失败：固定盘点 `/sources/2` 引用的初始原生基础设施规划 SHA 与后来补充过的当前同路径文件不同。实际核对该次输出目录及 `EXPORT_INCOMPLETE` 标记均不存在，保留原终端异常与[独立失败诊断](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-interim01-export-failure-diagnostic.json)，不伪造不完整包。此案也证明此前 validate04 没有覆盖 write 阶段的全部引用，不能把其零引用错误理解为真实导出已成功。

导出器已将这些引用移到验证阶段，并对这一**历史规划参考**保留[精确漂移说明](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/inventory-reference-drift-review.json)：原规划 SHA 为 `a55892c9b9a785d81ad42065adc6d5a52276ae95a6c9aea06d6fe26512fe27a4`，当前为 `f39a173151e986d073b955395f3130ece3a148735a997653db74b550ce8fd898`，未找到经摘要核实的旧字节副本。原 inventory 不修改，当前规划只作当前参考，不冒称旧原件；该说明不授予任何业务通过资格。真实 proof、config 和 host 的摘要冲突仍拒绝。第五轮[验证记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-05.json)已实际覆盖所有导出队列：输入 SHA 稳定、`errors=[]`，保留一条明确的规划参考漂移 warning。该较晚快照为 227 行中 180 通过、20 部分通过、4 失败、15 受阻、5 未测、3 待复核；52 单元及 282 条精确证据记录数量与前述 validate04 相同。它没有覆盖本稿开头注明的 validate04 原快照，也仍不代表真实导出或全量产品验收完成。

随后 `interim02` 使用该时点输入完成真实导出和外部独立验包。通过只读临时本地网页服务打开[离线证据首页](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-relocated-final06-interim02/index.html)，实际观察 227 个条目、52 个引擎单元；搜索 `APP-NAV-001` 返回 1 项，展开后证据图片成功加载，实际 EXE、回收记录及截图边界均能查看。浏览器工具不支持直接打开 `file` 协议，因此预览借用了专用 `127.0.0.1:18763`；该服务随后正常退出，端口已回收。[预览截图](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/interim02-evidence-browser.png)是证据报告页面，不能冒称产品 UI 实测截图。

在核对归属和目标路径后，仅将自有证据包目录改名为 `delivery-relocated-final06-interim02`，未删除或重新复制文件；文件清单 SHA 前后均为 `12296b5581462ba46745f188188d7e6e5f96bba69993e150c826646c7e1c2b55`。移动后再次使用包内独立验包器，实际通过。详见[移动与浏览器记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/interim02-relocation-and-browser-review.json)。另有[独立语义复核](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/environment-interim02-independent-review.json)：279 行含四引擎展开的裁定未被默升为通过，282 条精确证据的原状态及实际包 SHA 一致，92 项显式历史记录和失败截图边界完整保留，`errors=[]`、`acceptance_complete=false`。本包尚未纳入更晚的 DiffSynth 等原生终态；不可把此旧快照当成最终完整验收。

浏览器预览仅发现首页历史规划缺口详情默认展开占用过多空间，以及 favicon 请求 404。下一次生成器已改为默认折叠详情、保留醒目的缺口数和旧／现 SHA，并内嵌空 favicon；这些只影响未来新包，已冻结的 `interim02` 字节保持不变。新版模板 Python 与内嵌 JavaScript 语法均已实际通过；精确反向移除这三处模板变化所得 SHA 与 `interim02` 所用生成器一致，说明本次未改变裁定或投影逻辑。详见[纯呈现改动核验](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-presentation-check-01.json)。

在双版本及设置集成新证据纳入后，再执行了两轮只读验证。[第06轮原记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-06.json)保留一条真实错误：新增历史 main 安装失败记录的状态 Pointer 指向整对象，生成器无法把 dict 当状态；随后仅将该历史记录改为精确 `/checks/5/status`，原失败报告和截图没有修改。[第07轮验证](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-07.json)于 `2026-11-01T05:51:55.889332+00:00` 得到 `errors=[]`，保留同一历史规划引用漂移 warning，候选身份为真，306条精确 proof 中299条有效观察；[运行记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-07-run.json)证实约1.99秒、输入前后 SHA 稳定、未导出目录、未执行大复制。

第07轮新快照的227行是187通过、26部分通过、3失败、5受阻、5未测、1待复核；52引擎单元是3通过、8部分通过、5失败、3受阻、20未测、13待复核。该快照仅对应当次三份影响审查和严格裁定，未宣称后来 ENV 或引擎原案已经纳入，`acceptance_complete=false`。它不覆盖 validate04／05 或 interim02 的历史数字，也不等同于新的真实导出／离线验包。

后续继续 ENV 剩余专用入口和引擎维护实测，将新终态与已取得的双版本、设置集成及 DiffSynth／AI Toolkit 原件一起更新严格裁定及当前候选适用性，再冻结汇总、导出新目录并执行独立离线验包。只有全部必要项真实通过才能将 `acceptance_complete` 改为真；资源不足、前置受阻、不可达或未知原因的项目继续分别记录。

## 第08轮独立回收资格的中途验证

在 NATIVE 独立审查后，主控授权执行一次[第08轮只读验证](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-08.json)，汇总生成于 `2026-11-01T07:27:05.562253+00:00`，运行始末详见[对应运行记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/acceptance-delivery-validate-final06-08-run.json)。实际耗时2.2392秒，exit0、输入前后SHA稳定、errors=[]；310条精确proof中304条有效观察。原规划参考漂移 warning 保留，另有 `app:7614fd41b3c2cbc3` 的 forced/abnormal 资源回收限定警告。LOG022只签真实日志导航子步骤，原 native1/node1/hostfalse/CDPfalse和恢复业务失败不变。

该新快照的固定227行为191通过、26部分通过、3失败、2受阻、4未测、1待复核；52引擎单元为3通过、8部分通过、5失败、3受阻、20未测、13待复核。`acceptance_complete=false`，`final_input_freeze=false`。仍在执行、没有完整host终态的ENV用例未隐式计入。它是新的显式输入验证时点，不覆盖 validate04／05／07 或旧 interim02 的历史数字，未创建新导出目录、未执行大复制，也未改写旧冻结证据包。

第08轮后仅对证据工具补了一处导入副作用修复：离线验包器在导入共享纯谓词之前设置 `sys.dont_write_bytecode=True`，避免其新生成的 `tools/__pycache__` 被全目录清单判断为额外文件。该变更不改任何验收谓词、业务裁定或原证据；[NATIVE 增量独立审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/cleanup-verifier-import-native-independent-review-01.json)确认删去唯一新增行后，builder/verifier SHA 精确回到第08轮所用字节；新模板与独立工具同源。最小外部导入夹具实际证实没有 pyc 副作用，并按预期拒绝故意设置的 incomplete 标记；它不是实际交付包。旧08结果与原审计不改，最终冻结时再按新工具身份导出和真实离线验包。
