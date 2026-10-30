# CR-010 界面修订与右下信息去重实施记录

日期：2026-10-31（Asia/Shanghai）。唯一进度入口为[总控目标索引](00_总控目标索引.md)。本轮直接执行用户验收后的原六项界面调整，以及后续两次明确追加的右下信息去重要求，保留CR-009的既有业务与服务状态合同。

状态：**complete-with-boundary（本轮施工、最终包验收、视觉复核与入口交付完成）**。`feat/desktop-launcher` 本轮起点为 `099aa86e1154cb0d457e2461c2f4822ce3bace38`。最终源码基线 `74076ef51cce2d31ecf21b2eebb5c3a8e6559ad7` 已普通push并以 `ls-remote` 核对一致。candidate-2的 `refinement-04` 主案50项、重开3项全部通过；独立视觉复核无阻断，用户普通入口已指向最终包，未代用户启动。完整身份与证据摘要见[结构化验收](ui-refinement-20261031-validation.json)。

## 需求与实现映射

| 用户要求 | 本轮实现 | 验证状态 |
| --- | --- | --- |
| 移除左下重复状态 | 删除首页 `home-progress`；安装任务的阶段、查看日志和取消操作仅在实际任务运行时放至右侧主操作区 | 原生DOM与两主题布局通过 |
| 修复设置图标 | 统一设置图标改为对称八齿闭合轮廓与内圆，保持24像素视框内边界 | 原生SVG边界与绘制通过 |
| 删除启动按钮旁重复设置 | 保留侧栏底部唯一设置入口，主启动按钮恢复完整圆角 | 原生重复入口移除、唯一设置入口通过 |
| 信息卡上移、放大并换内容 | 常规420×360，小窗口360×330；共享底部变量使卡片与主按钮底边对齐；本地打包原项目封面，两个栏目为项目发布和友情链接 | 原生双主题三尺寸6次底边差均0px；最小窗口三链接无裁切 |
| 浅色补齐并默认浅色 | 共用深浅语义颜色，覆盖管理、日志、设置、导入、信任、壳恢复、对话框及错误控件；无主题偏好时浅色，明确深色偏好继续保留 | 浏览器四种偏好场景通过；原生默认浅色、切换、同WebView重开保留深色后恢复浅色通过 |
| 版本信息移至左上标题栏 | 标题栏取当前训练器版本和实际渠道；移除旧首页版本行 | 原生显示 `3.3.1-dev · dev（开发线）`，与真实版本一致 |
| 追加：移除右下重复状态文案 | 不再显示“可以启动”等文字；仅服务真实healthy且URL非空时显示地址和复制入口 | 浏览器四种context与原生停止/ready/再次停止通过 |
| 追加：删除按钮下提交号与说明整行 | 删除 `launch-footnote`；信息卡与主按钮共用bottom，常规54px、高窗68px，保持底边齐平 | 浏览器与原生DOM通过，实际6次底边差0px |

信息卡固定链接为：

| 名称 | 地址 |
| --- | --- |
| 项目发布 | https://github.com/wochenlong/lora-scripts-next/releases |
| Displace 博客 | http://blog.displace-ai.top/ |
| Bilibili 个人空间 | https://space.bilibili.com/351205898 |
| ModelScope 魔搭 | https://www.modelscope.cn/home |

Bilibili仅移除来源跟踪参数，目标空间未变。链接通过后端固定目标白名单调用，前端不传任意URL。封面来自仓库 `assets/readme/next-trainer-cover.png`，逐字节复制到启动器本地资源，1672×941，1,682,225B，SHA256为 `0aece9b3ce1b10697d3eb02e49795a9c3db7dddc7e82c26ba4f73e11cf895ceb`。项目Logo继续使用本地 `home-logo.webp`。

## 验证与审查

`npm run build`、`cargo fmt --check`、`cargo check --locked --offline` 已通过。只读源码审查未发现阻断问题：深色变量从应用壳继承到各面板和壳内确认框，ShellPanel随全局色板变化；主题迁移继续保留背景、遮罩、模糊、动态效果及日志字号；安装任务取消与日志入口仍保留。源码结论不能代替实际可读性和布局验收。

最新独立浏览器验收 `browser-05/browser-report.json` 已通过28项检查（27项主题、外链和UI合同，加1项零外部网页请求检查），覆盖全新默认、旧设置缺theme、明确dark、无效theme四种场景；每种context均核对停止态右下重复状态和提交号/说明脚注已移除。旧背景、遮罩、模糊、动态效果和日志字号经切换、保存及刷新后均保留。五个可见外链入口（封面及发布按钮共用releases）真实点击只产生四种固定target，未打开系统外部浏览器、未发送外部请求；页面脚本异常和未建模IPC均为零。本次自有浏览器与服务正常关闭。该证据是浏览器IPC夹具合同，不代表原生系统浏览器打开行为或服务运行验收。

`browser-03`的24项合同虽然通过，其截图尚未等待页面过渡稳定；`browser-04`已补齐稳定等待。用户右下追加需求到达后再运行`browser-05`，以05为当前合同与浏览器截图证据，旧案原件保留。

本轮验证工具在仓库外 `E:/OpenSourceTeamWork/workspace/tools/launcher-ui-refinement-20261030/`。最终案为 `refinement-04`，原生主案50项、同WebView正常重开3项通过，实际界面与服务均未模拟：

1. 独立浏览器IPC夹具核对四个外链的真实点击调用、主题偏好兼容和追加右下去重，已通过；完整回执位于上述目录 `browser-05/browser-report.json`。
2. 冻结EXE复用既有完整安装根 `F:/NextTrainerLauncherSandbox/r12`，新建独立WebView；真实一轮启动、HTTP版本与网页JS/CSS读取、停止通过，版本为 `3.3.1-dev`。
3. 浅色与深色分别核1024×640、1184×667、1440×900首页，共6次卡片/按钮底边差均0px；版本、环境、日志和设置共8页无横向溢出。最小窗口友情链接3项完整可见；Logo与封面通过原生Image和已加载响应的实际字节摘要核验。
4. 正常关闭后使用同一WebView新进程重开，深色和r12目录保留；最后恢复浅色。双阶段UI与进程退出码均0，正常关闭、Job排空、CDP回收、外部只读哨兵一致均为true。

| 真实启停时序 | 启动 | 停止 |
| --- | --- | --- |
| 点击到过渡状态可见 | 1.5ms | 3.2ms |
| 后端ready/stopped成立到对应按钮可用 | 4.0ms | 14.6ms |

时序符合250ms点击反馈、1s完成后按钮刷新上限；测量不包含首次完整检查或启动前必要校验的耗时。测试仅移动本次精确归属的原生窗口至屏幕外，避免用户桌面并发操作干扰，不改变正常交付入口的位置。

根代理已独立查看浅/深首页、三尺寸布局及浅环境截图；主题代理独立查看浅/深环境、日志、外观和用户资料共8张管理页截图，均未发现阻断问题。本轮代表图：[浅色首页](../../design/desktop-launcher-ui-review/refinement-20261031/light-home.png)、[深色首页](../../design/desktop-launcher-ui-review/refinement-20261031/dark-home.png)、[浅色最小窗口友情链接](../../design/desktop-launcher-ui-review/refinement-20261031/light-friends-1024.png)、[深色最小窗口友情链接](../../design/desktop-launcher-ui-review/refinement-20261031/dark-friends-1024.png)、[浅色日志](../../design/desktop-launcher-ui-review/refinement-20261031/light-logs.png)、[深色日志](../../design/desktop-launcher-ui-review/refinement-20261031/dark-logs.png)。

失败和中止原件均保留：`refinement-01`是harness对已为light时再选light仍等待写存储的误等，不能归为产品主题保存失败；`refinement-02`在用户追加要求后由owner主动取消，属于需求变更中止；`refinement-03`的requestAnimationFrame采样漏掉约7ms的停止过渡，实际stopped后按钮23.9ms已恢复，不能写成产品停止迟缓。04补即时DOM采样后用同candidate-2完整重跑主案与重开通过。前三案不作为整案通过，不覆盖或删除。

## 最终candidate-2身份

最终构建提交 `74076ef51cce2d31ecf21b2eebb5c3a8e6559ad7`，训练器源码 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`。locked/offline构建成功，缓存变化 `cache_changes={}`，本次资源暂存仅精确清理归属文件。同一EXE用于便携ZIP、NSIS及本轮原生验收。

| 制品 | 字节数 | SHA256 |
| --- | --- | --- |
| EXE | 37,273,600 | `2d2063e8f2ae2ad52e022c4cc2383995b6b1220b45b5db8bc95500b0d26a2be6` |
| 便携ZIP | 19,348,401 | `e31714fca82e07860c545efeb9b3815053e1b465c2610782100acf9b6586e08e` |
| NSIS安装器 | 16,160,593 | `02cea12fd903d39245db41120f8bbcce733c3cd5e4a535e5938335ad6a915db5` |

构建目录：`F:/NextTrainerLauncherSandbox/build-ui-refinement-20261031/candidate-2`。从ZIP校验解压后的最终程序：`F:/NextTrainerLauncherSandbox/ui-refinement-20261031-2/NextTrainerLauncher-0.2.0-windows-x64`。详细catalog/recipe/源码摘要见同目录 `delivery-manifest.json`；构建时的`validation`为当时快照，后续原生验收以本轮结构化回执为准。后续文档提交不表示产品重新构建。

## 已被替代的candidate-1身份

**superseded（被用户追加要求替代，保留原件）**。candidate-1的locked/offline构建已完成，同一EXE同时装入NSIS与便携ZIP；未作为本轮最终包交付。其构建提交为 `69cdf634d987ae1276b8658731293d51882f46dc`，训练器源码仍为 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`。

| 制品 | 字节数 | SHA256 |
| --- | --- | --- |
| EXE | 37,273,600 | `b9d624656fe614b6aa6ea027c79ff324756ef9628cab8df62d72d5e662f44b85` |
| 便携ZIP | 19,348,326 | `326db52afcd32f13c7187bff0e57bd31874336b54e39c478c8260ae9b667b6d7` |
| NSIS安装器 | 16,157,474 | `663edb227d79b15694c627ba706b962a807c233fd590253ce4d410f7e3f87ab8` |

构建目录：`F:/NextTrainerLauncherSandbox/build-ui-refinement-20261031/candidate-1`。从ZIP校验解压后的目录：`F:/NextTrainerLauncherSandbox/ui-refinement-20261031-1/NextTrainerLauncher-0.2.0-windows-x64`。上述身份只用于区分旧案，不是本轮最终入口。

## 实施边界与交付

用户入口 `F:/NextTrainerLauncherSandbox/user-20261030/启动新版启动器.cmd` 已更新并读回核对，状态为 **ready-for-user-test-and-use**：指向最终candidate-2，复用原用户WebView且清除CDP参数，未代用户启动窗口。只备份并修改本次新增的启动入口、`新版启动器使用说明.md` 与 `new-launcher-ready-report.json`；旧入口、u13安装、模型和样例均未改动。备份位于 `E:/OpenSourceTeamWork/workspace/tools/launcher-ui-refinement-20261030/user-entry-backup-20261031`，部署回执为同工具目录 `user-entry-deployment.json`。后续由用户双击新版入口进行使用验收。

本轮只验证原六项界面修改、右下信息去重追加和既有服务启停，不重装环境、不重新下载模型、不训练；不把已安装r12称为干净Windows首装。不启动外部网站，固定链接的IPC合同与后端白名单分别核对；未实测系统浏览器打开或点击系统剪贴板复制。公开发布、生产签名、干净Windows与缺WebView2首装仍沿用既有边界。
