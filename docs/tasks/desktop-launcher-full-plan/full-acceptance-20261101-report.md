# NextTrainer 桌面启动器自动验收报告

本轮自动验收已执行并完成证据整理，**结论为未全部通过，不能签收为“所有按钮和功能均已测完且可用”**。已观察226个可达模板入口，但 AI Toolkit 与 Anima Fast 仍各有5个具体按钮未操作，另有业务失败、受阻及候选包适用性待复核项。无需用户再人工重走清单；下面直接交付结果、缺口和截图。

验收对象为 **FINAL06**，产品提交 `4e1b4cc78939e8b906252b27dcc20692ad347a08`，EXE SHA256 为 `11804c053d8667b1c9b91512d72055481aeb27d58be2ac32d181ede42413cbca`。最终输入于 **2026-11-01 13:06:50.900033 UTC（北京时间21:06:50.900033）**冻结，候选身份核对通过。本轮未开启真实训练；服务启动、依赖导入及入口探针不等于模型或 GPU 训练验收。测试位于独立安装根，主机已有 WebView2，未验证缺少该组件的干净 Windows 首装。

## 结果与覆盖范围

| 口径 | 冻结结果 |
| --- | --- |
| 固定清单227行 | 193通过、24部分通过、8失败、1受阻、1待复核 |
| 四引擎52个具体单元 | 3通过、8部分通过、8失败、22受阻、1未测、10待复核 |
| 至少一次真实操作或明确预期禁用 | 226／226个可达模板入口；不是四引擎每个具体按钮都已点击 |
| 当前源码不可达 | `GUI-LIFE-07`：继续未完成的实例回退，未伪造状态强行触发 |
| 证据引用 | 329条精确 proof，其中319条符合观察合同；每条保留实际运行包与原状态 |
| 包内证据原图 | 353张，按SHA保存；外层浏览器预览图另列 |

227行为 APP117、环境及恢复88、原生系统交互22；四引擎52是13个模板在四个目标上的展开，不能与227相加。源代码交叉盘点的181个交互节点均有清单映射。通过数采用最终候选包适用性核对后的汇总，不能以各 owner 更宽的原始统计替代。旧包上的真实操作仍保留旧包身份；没有足够适用性证据的成功记为待复核。

**10个具体按钮仍未点到：** AI Toolkit 和 Anima Fast 各自的 `ENG-06 收起检查结果`、`ENG-07 高级选项`、`ENG-08 仅检查文件`、`ENG-09 重新安装环境`、`ENG-10 运行检查`。最后三案共15个后序目标按钮未进入（每个引擎5个），其中上述10个在 AI Toolkit 与 Anima Fast 上从未操作；两种计数范围不同。Kohya 有历史目标操作，但保留旧包身份，最终候选仍有6个单元待复核，不计作新包通过。三案均在首个健康查询等待900秒后失败，不能用其他引擎的同名按钮补齐。完整分支见[227行明细与截图图集](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/index.html)和[52单元矩阵](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/adjudication/combined-engine-units-52.json)。

## 必须处理的问题

1. **P1：主程序实例恢复自阻挡。** 真实重建提交故障留下 pending 后，正式恢复把自身事务当作其他版本冲突，在任务持久化前失败；原 pending 和登记保留，未观察到数据丢失。[内存失败原件](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/cleanup/reconciliations/cf49fdc6ab8233ac-readonly-log-and-memory-0640.json)的 `/memory_snapshots/0/snapshot` 与[独立根因审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/cleanup/reconciliations/4b07353a15083648-gui-rebuild-recovery-self-block-independent-review-01.json)保留确切结果。后来“恢复旧实例事务”专用路径已成功，属于另一个入口，不能覆盖本缺陷。
2. **维护和启动等待过长、内部进度不足。** 一次普通源码修复成功耗时 **54分41.498秒**，一次保留旧实例的正式重建成功耗时 **85分27.836秒**；轻量 `not_run` 概况直接启动到 HTML/API200 用时 **156930毫秒**。[源码修复原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/9e98aef876b86166-environment-report.json) `/checks/3`、[重建终态](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/ab40b9d810566637-preserveddual-final06-terminal-analysis-01.json)与[冷启动原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/55d9a3735183f075-native-report.json) `/checks/0`分别保留始末和结果。源码审查确认重建内有重复完整保护核验、候选扫描，内部进度未逐次发布；这不能定位活任务的具体调用点，也不能将进程累计 I/O 当作该操作增量。经所有权验证的 `t...` 引擎树被排除，不能称其反复扫描四个 Torch 实体。
3. **多包损坏场景的普通重装确认未出现。** 专用高级导航已经成功，随后“重新安装环境”等待30秒没有确认窗，原 `/checks/6` 失败，具体原因 **unknown（未知）**。另一个场景预览和取消成功不抵消本次失败；高级导航的独立衍生通过也不改变 ENV 父分支失败。见[原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/9e98aef876b86166-environment-report.json)和[终态分析](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/6f7d8d7f8f0ab8b7-mainvariants-cleanroot-final06-terminal-analysis.json)。
4. **引擎查询失败阻断完整维护验收。** DiffSynth 原后台任务成功、实例 ready，后续 UI 查询超时；AI Toolkit 原安装成功，但原失败图到了版本页，页面变化原因未知。最后的[AI Toolkit](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/685b205b02b679b4-ai06-maintenance-only-terminal-adjudication-01.json)、[Kohya](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/fbbb0b8eacfa3451-kohya06-maintenance-readypaths-terminal-adjudication-01.json)、[Anima Fast](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/7ab512b5f12272ce-anima-fast06-maintenance-readypaths-terminal-adjudication-01.json)三案都在首次健康查询900秒后失败，尚未运行修复、重装、probe或取消。这些应称查询验收失败，不能改称三次修复失败，也不能用 ready 记录证明界面通过。

汇总中的8个失败行是 `APP-ENV-004`、`ENV-MAIN-01`、`ENV-MAIN-06`、`GUI-LIFE-05`、`ENG-01`、`ENG-02`、`ENG-04`、`ENG-09`。其中包含共享入口及原尝试的失败，并不等于8个已确认独立产品根因。`APP-HOME-014 取消启动`有旧包操作事实，但候选适用性未完成，保留待复核。

## 各模块实测结果

| 模块 | 已有证据与限制 |
| --- | --- |
| 下载、安装与版本管理 | 已执行正式安装、下载取消、双健康版本切换与回退、版本详情及删除保护；旧89合法健康环境、部分损坏和占用分支仍未闭合 |
| 服务启动、打开网页与停止 | 有真实 ready、HTML/API200、系统浏览器打开、停止与端口回收；本次从“尚未检查”概况直接启动，最终 ready 且 HTML/API200；启动后台仍执行正式完整验证。stop_failed重试等分支仍未测，不能宣称所有状态均通过 |
| 主程序检查修复与恢复 | 有简化源码修复成功、高级依赖及基础组件恢复、登记恢复和独立重建；专用旧实例恢复成功。P1自阻挡、普通重装确认及部分缺损分类仍有失败或缺口 |
| 四引擎独立维护 | 真实安装、receipt、独立目录及部分维护事实已保留；本候选严格结果见下表，未开启训练 |
| 设置、语言、托盘与窗口 | 已观察设置分类、保存重读、中英文、关闭到托盘/完全退出、托盘恢复、最小化、最大化及外部链接等实际系统效果；不代表外部网站内容可用 |
| 日志、资料导入与保护 | 有集中日志筛选、系统剪贴板、UTF-8导出、真实资料导入/恢复及保护摘要。提交阶段取消、重复请求/终态控件和部分响应竞争分支未独立闭合 |

| 引擎／每个13单元 | 通过 | 部分通过 | 失败 | 受阻 | 未测 | 待复核 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Kohya | 0 | 0 | 3 | 4 | 0 | 6 |
| Anima Fast | 0 | 0 | 1 | 9 | 1 | 2 |
| AI Toolkit | 1 | 1 | 2 | 9 | 0 | 0 |
| DiffSynth | 2 | 7 | 2 | 0 | 0 | 2 |

专用旧实例恢复真实点击及确认后，任务 `download-1793533097-235536-0` succeeded，旧 generation2 恢复 clean、形成正式 receipt，当前新实例绑定保持，原123个 profiles 文件 SHA不变。见[恢复原报告](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/95f08759b0602cd0-environment-report.json) `/checks/0`。此前重建成功后 helper 的“读取实例记录”locator 等待30秒失败仍单独保留，原因未知，不是正式重建任务90分钟超时。

冷启动停止步骤原 `/checks/2` **仍失败**：全 profiles 文件集合比较发现唯一新增 `config/.update_cache.json`。[独立缓存审查](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/sessions/5ea37af6987b87f3-cold-profile-diff-native-independent-review-01.json)确认原123文件未改未缺，新增文件是固定发布源码写出的更新检查缓存。失败前已执行 runtime stopped、API不可达、首页启动按钮恢复及绑定保持的断言，但不据此将整步或整套改为通过；后面的停止后 main 可用、日志及首页任务控件断言没有执行。

## 截图、原件与复核

从[离线证据首页](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/index.html)搜索控件ID，展开实际截图、JSON Pointer、运行包身份和回收记录。代表原图如下；任务成功、文件 SHA、绑定及 API结果由配套 JSON证明，不能只看截图。

| 实测状态 | 真实原图 |
| --- | --- |
| 冷启动服务就绪及打开网页入口 | [冷启动 ready](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/dc7c08db2ec49473d211ffdfff70ca63634f2d1c5ed9fb7786ffbd32b545c637.png) |
| 普通源码确认修复成功 | [修复结果](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/a3259755f0f8530ba81c79b5f31e4ccb2cfe5e0b1ec78cf31aecd22a30a426bd.png) |
| 多包重装确认未出现 | [原失败时页面](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/d97e46792d56f0a13cc24043483922eda8822459cda723ebb64a9700fecdd152.png) |
| 旧实例专用恢复确认 | [恢复确认窗](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/91da7c43eebd137909c512cec8da57a2dfc326e811948800f6b393f0155eafb6.png) |
| 三次健康查询超时 | [AI Toolkit](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/760c340987759f92302c28f5872042ffef41033f878b62e910b03c0e6e6f9eac.png)、[Kohya](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/8d0d91a5bb80bb38478789d097db70578c04a6370a4da78227e6664ecc72a915.png)、[Anima Fast](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/screenshots/56fa8f3e3e59c51a0396be2ee47090cc89e2a1ddcf515b3086c4c051a5506376.png) |

最终输入检查实际读取735个输入，前后 SHA稳定，`errors=[]`；保留两条明确 warning：历史规划引用已漂移且旧字节未找到、一次异常资源回收由独立证据确认。两者均不授业务通过。导出后已分别运行外部验包器与包内 `tools/verify_bundle.py`，两次实际退出码0；这证明包完整性，`acceptance_complete=false`保持不变。浏览器最终复核实际通过 `file://` 打开图集：初始227项、失败筛选返回8项、引擎矩阵52单元；展开 `GUI-LIFE-06` 后对应原图成功加载，AI Toolkit、Kohya、Anima Fast 三次查询失败的指定原图也逐个解码成功，页面无错误。浏览器关闭工具返回 `No open tabs`。本次复核未启动预览服务器；随后只读核对旧预览脚本进程及18763/18764监听均为空。精确观察见[浏览器与资源回收原记录](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/final-evidence-browser-review-02.json)，截图见[总览](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/delivery-final-evidence-browser-overview.png)、[失败详情](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/delivery-final-evidence-browser-failures.png)、[旧实例证据](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/delivery-final-evidence-browser-life06.png)、[最终展开核对](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/delivery-final-evidence-browser-verified02.png)及[三次查询原图加载](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/delivery-final-evidence-browser-queries02.png)。这些只验证证据可读性与复核资源回收，不增加业务通过项。

环境独立语义复核核验23项、34件包内原件，原生独立收尾复核核验26项，均无硬错误；两者仅确认记录、身份与边界正确，`acceptance_complete=false`保持不变。见[环境独审](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/final-delivery-environment-independent-review-01.json)、[原生独审](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/final-delivery-native-closeout-review-01.json)。两次原验包结果与最终输入检查的副本也在外层收尾目录，[13件收尾文件摘要清单](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/closeout/manifest.json)逐件列SHA。该目录属于外层材料，不在内层 verifier校验范围。

[机器汇总](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/manifests/generation-report.json)、[精确路径映射](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/manifests/path-map.json)与[原始失败索引](E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/delivery-final06-20261101/evidence-bundle/failures/attempts.json)可用于追溯。公开投影保留原SHA、投影SHA及删除Pointer，原始失败未修改；三窗口同期退出仍为原因未知，未当作产品崩溃结论。

本报告与[历史执行报告](full-acceptance-20261101-execution-history.md)位于内层证据包之外，**不属于包内 verifier校验范围**。历史稿逐字节保留为59,165字节，SHA256 `2cd198d447be11b84b6260bbb7e986e8f7c8a4f6887c10bda0b168fdec39daac`；其中原始绝对路径只在本机有效。只有外层交付读者稿使用可随整个交付目录搬移的相对链接；仓库中的报告副本使用本机绝对证据链。最终交付目录本轮未执行物理搬移，不声称已做搬移后验包。内层不含EXE、安装大树、模型或原始偏好备份。

建议后续先修恢复自阻挡、普通重装确认与查询等待问题，随后对失败路径和上述10个未操作的具体引擎按钮补测。当前交付保留真实未通过结论，不要求用户再人工验收，也不通过抹去失败形成全绿。
