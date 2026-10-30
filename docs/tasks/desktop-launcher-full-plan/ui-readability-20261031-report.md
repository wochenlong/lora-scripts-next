# CR-011 背景、集中日志与界面可读性修订

日期：2026-10-31（Asia/Shanghai）。状态：**complete-with-boundary（约定UI范围完成，最终包只读验收与交付通过）**。唯一进度入口仍为[总控目标索引](00_总控目标索引.md)，沿用 `feat/desktop-launcher`，不另建长任务书。

用户已直接授权本轮四项修改。采用Lite规模的既有UI维护与行为场景验证；依赖预检7项skills、4项routing通过。源码基线 `6afbed22188198837b3edcbd22db1e50bbe257c8` 已commit并普通push；最终candidate-1、原生只读验收及新版普通入口均完成。关键身份、回执和截图摘要见[结构化验收](ui-readability-20261031-validation.json)，CR-010候选包和验收保留其原制品边界。

| 用户要求 | 实施内容 | 本轮验收 | 当前状态 |
| --- | --- | --- | --- |
| 更换默认背景 | 用户指定本地HTTP poster原件已固化进本地资源包，运行时无需访问该HTTP服务；原显式自选背景继续保留 | 浏览器核默认和原自选背景；原生Image与已加载响应核指定PNG真实字节/SHA | 通过 |
| 去除管理页底部状态和日志条 | 全部管理页删除 `status-summary`；日志统一在专用页，任务取消从日志页可达；中断提示迁为日志内容自然顶部 `operation-warning`，保留恢复入口 | 浏览器真实点击仅取消当前mock任务；原生两主题三尺寸和设置子页均无固定底条 | 通过；实际安装任务取消未重跑 |
| 浅色去除全屏白层 | 删除浅色专用全屏白层，壁纸遮罩与深色共用参数；裸露在壁纸上的文字用浅色，实际卡片和控件内文字用深色 | browser-02与原生15组浅深页面的壁纸/遮罩层参数一致，独立截图复核清晰 | 通过 |
| 提高文字可读性 | 普通文字12px下限，日志默认及最小字号12px；旧小字号归一到12px，显式大字号继续保留 | 浏览器字号迁移和保存通过；原生30布局普通文字最小12px，日志选项最小12 | 通过 |

用户指定poster原件为 **1,680,487B**，SHA256：`cf6f9f00dc25f3a94637604ff8d5a46329df91fe8077b17ca1826ea1c3017473`。最终包实际使用本地 `/assets/launcher-wallpaper.png`，1672×941；通过原生Image加载和主帧 `Page.getResourceContent` 读取已加载响应，字节数与SHA均与指定原件一致。

最终 `npm run build` 通过，输出 `index-CDFokJGK.css` 与 `index-aI9PGKD9.js`；品牌资源生成脚本 `py_compile` 通过。浏览器最终案 `browser-02/browser-report.json` 记录80项检查、30项布局全部通过；页面异常、未建模IPC、外部请求均为零，自有临时浏览器与服务正常关闭。取消能力以日志页真实点击核本次mock任务的IPC，不是实际安装任务取消结果。

首轮 `browser-01` 同样有80项合同、30项布局通过，但根代理实际查看截图发现浅色裸露深字对比不足，未据此定包。之后修正为壁纸上浅字、真实卡片/控件内深字，且两主题共用壁纸遮罩参数不变；重新运行 `browser-02` 全部通过并独立视觉复核。01原件保留，合同通过不冒充视觉通过，最终以02及native-01为准。

本轮验证工具位于仓库外 `E:/OpenSourceTeamWork/workspace/tools/launcher-ui-readability-20261031`。最终 `candidate-1` 已完成离线构建，干净产品输入为 `6afbed22188198837b3edcbd22db1e50bbe257c8`；缓存变化 `cache_changes={}`，构建资源暂存精确清理完成。同一EXE装入便携ZIP与NSIS，ZIP经摘要核对后解压。最终 `native-01/host-status.json` 为passed：实际r12主案70项、30布局及正常重开2项全部通过；两阶段UI和进程退出码0，正常关闭、Job排空、CDP回收、外部哨兵一致均为true，无页面异常。

原生只读覆盖两主题×三尺寸×首页/版本/环境/日志/设置共30布局、设置子页、日志控件与历史控件；15组浅深壁纸层策略一致。测试全程未调用启停、安装、下载或训练，runtime保持stopped，pid/port/run_id均为空；不以只读结果声称本包业务链重跑通过。根代理实际看浅深用户资料/安全4图和浅首页/日志2图，均清晰无异常；资料页底部为正常滚动内容。原生代表图：[浅色首页](../../design/desktop-launcher-ui-review/readability-20261031/light-home.png)、[深色首页](../../design/desktop-launcher-ui-review/readability-20261031/dark-home.png)、[浅色环境](../../design/desktop-launcher-ui-review/readability-20261031/light-environment.png)、[浅色日志](../../design/desktop-launcher-ui-review/readability-20261031/light-logs.png)、[深色日志](../../design/desktop-launcher-ui-review/readability-20261031/dark-logs.png)、[浅色用户资料](../../design/desktop-launcher-ui-review/readability-20261031/light-profiles.png)。

| 最终候选制品 | 字节数 | SHA256 |
| --- | --- | --- |
| EXE | 38,842,368 | `9b809f631b767abd7e33aaa4d17dbb3c029c98e5f2863044a020198b051619e5` |
| 便携ZIP | 20,917,186 | `6f913f5b92f3e6eca1839e583833aa296b745e4e85f1b96f573e010b07f1c251` |
| NSIS安装器 | 17,397,559 | `6910e4a5a4c2133b7b1cf5c5f9234b672f568392df91581ee9ce8f7aa1180d72` |

构建目录：`F:/NextTrainerLauncherSandbox/build-ui-readability-20261031/candidate-1`。已校验解压且通过本轮原生验收的程序目录：`F:/NextTrainerLauncherSandbox/ui-readability-20261031-1/NextTrainerLauncher-0.2.0-windows-x64`。训练器源码继续为 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`，本轮只改变启动器界面资源与呈现。后续文档提交不代表重建产品。

用户入口 `F:/NextTrainerLauncherSandbox/user-20261030/启动新版启动器.cmd` 已备份并更新至本轮最终包，ready报告为 `ready-for-user-test-and-use`，未代用户启动。仅更新新增的入口、使用说明与ready报告，旧三文件备份位于上述工具目录 `user-entry-backup-20261031`，部署回执为 `user-entry-deployment.json`；保留原WebView、自选背景、u13安装、模型、样例和旧入口。已有自选背景的用户需在“设置 → 外观”点击“恢复默认”才切到本轮海报，使用说明已标明。

本轮不重复真实服务启停、下载安装或训练，原因是改动范围为资源、主题、文字和日志入口呈现，服务生命周期、安装事务与训练流程未改；同时沿用用户“验收和测试简略一些”的明确要求。取消能力采用浏览器运行任务场景核入口和调用合同，不为制造取消场景而启动安装、下载或训练。原生验证只读取现有安装与界面，不将本轮结果追认为冷安装、干净Windows、缺WebView2首装或GPU训练通过；当前仍为unsigned/public_release:false开发候选，不作公共发布。
