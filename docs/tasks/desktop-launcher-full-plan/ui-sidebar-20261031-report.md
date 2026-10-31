# CR-013：侧栏叠加展开与标题精简

- 状态：complete-with-boundary，约定UI维护与交付完成。起点 `52c1ac1e0789585db0f0a2d9a8de79f4b57d88d8`，分支 `feat/desktop-launcher`。
- 授权：用户要求移除左上标题栏Logo、版本号左补；将四方块按钮改为侧栏展开按钮，带动画显示按钮名称；只向右变宽，不移动或缩放主窗口内容。
- 路径：既有UI的小幅、可逆维护，采用精简的行为验证，沿用总控和既有交付流程。保留首页大Logo、背景偏好、原安装根与训练数据。

实现：标题栏版本从x120移到x68；侧栏默认56px、展开208px，绝对定位覆盖内容，主内容/标题栏的56px起点保持不变。菜单图标切换展开状态，五个导航显示名称，宽度250ms、文字167/250ms渐显位移；系统或设置的减少动态关闭过渡。支持Enter/Space切换与Escape收起、焦点回开关，展开状态仅本次窗口使用。管理页展开区域用亚克力覆盖后方控件，收起恢复全窗连续材质。

| 验收项 | 验证 | 状态 |
| --- | --- | --- |
| 标题Logo移除、版本号补到x68；首页大Logo保留 | DOM与实际截图 | pass |
| 侧栏56→208且显示首页/版本/环境/日志/设置名称 | 鼠标和键盘、aria-expanded | pass |
| 展开收起过程中主内容/标题栏/信息卡/启动按钮坐标和尺寸一致 | 五页及三尺寸首页bbox对照 | pass |
| 展开动画中间态可见、减少动态生效、切换不跳页 | 定向交互 | pass |
| 最终EXE可使用、入口更新与远端保存 | 包身份、隔离原生、入口回执 | pass |

本轮只读UI验证，不运行安装、下载、训练或真实服务启停。既有工具限制为独立WebView、精确归属窗口/Job，保护用户当前窗口、偏好与业务数据。既有无关未跟踪资料不提交、不清理。

## 浏览器阶段

- `vue-tsc --noEmit && vite build`通过，最终资源 `index-DVmfQTLm.css` / `index-46waeMRs.js`。
- `browser-02`：31项检查、7组布局对通过（1184五页，1024/1440首页，合计14个展开/收起状态）。标题版本x68、Logo删除、名称/选中语义、真实导航、Enter/Space/Escape、减少动态、背景偏好保持均通过；卡片/主内容/标题栏/启动按钮坐标尺寸恒定，动画中间宽度125、158.92等，全部帧主内容x56。
- `browser-03`：仅最终CSS小案6项通过，确认管理页收起过程中材质保留至250ms宽度动画结束，最终56px恢复透明无残块，减少动态立即切换；没有重复全页矩阵。Root已看最终环境展开图及此前首页展开/收起与设置图，无视觉阻断。
- `browser-01`因设置按钮欠缺aria-current失败；已补齐与主导航一致的当前页语义，02已通过。保留失败原件，未降低合同。
- 独立代码/截图review无阻断；面板展开遮住左侧152px为叠加设计，页面未移动；Escape在侧栏内生效，点击正文不自动收起。开关控制展开，不再跳转首页。
- 工具与原始证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-ui-sidebar-20261031`。上述案零页面异常、外部请求或业务变更IPC，自有浏览器/服务器正常收尾。

## 产品基线与制品

- 源码 `7f2d02df31b71f8f19e4ffe80af7a04ae809937f`已普通push，并实核远端一致。产品scope干净，无关未跟踪资料保留。
- 预检通过固定训练器前端摘要与14项工具锁；候选离线构建通过，cache_changes={}。输出 `F:/NextTrainerLauncherSandbox/build-ui-sidebar-20261031/candidate-1`。
- 全部制品摘要、ZIP CRC和成员安全路径、解压后EXE/helper/清单均核对通过。解压至全新 `F:/NextTrainerLauncherSandbox/ui-sidebar-20261031-1/NextTrainerLauncher-0.2.0-windows-x64`。

| 制品 | 字节数 | SHA256 |
| --- | ---: | --- |
| EXE | 38,866,944 | `3bd89c35b84b01cb80e81fb1c7ca5bdfc041a05544513385d683ef2fa8079478` |
| 便携ZIP | 20,942,099 | `b8f9d9094926be18e1a7ed1707fc8c5c36599a6d66b55cd98e550a859b976197` |
| NSIS安装包 | 17,412,094 | `d91a4a89b44f4b6507601a50e1ce36a4f5a293e850b15bfb69fabbd47b84f86c` |

## 最终包与入口验收

- `native-01` 总体passed=true，最终EXE主案22项/5布局对（1184首页/环境/设置，1024/1440首页）、正常重开3项全过；只覆盖受影响界面和操作，没有重复旧版材质/下拉/训练完整矩阵。
- 两阶段UI与原生退出0，正常关窗、Job排空、CDP回收，外部只读哨兵前后一致；没有遗留本次测试窗口。保持既有r12的服务stopped，不执行启停/下载/安装/训练。
- Root实际看最终原生收起首页、展开首页和展开环境；独立代理另看这三张及展开设置，无视觉阻断。主内容与标题栏固定56px，卡片/启动区位置与比例不变。
- 已备份并只更新用户新增3文件：`F:/NextTrainerLauncherSandbox/user-20261030/启动新版启动器.cmd`、`新版启动器使用说明.md`、`new-launcher-ready-report.json`。目标为上述ui-sidebar-20261031-1新包；10项部署校验全true，包括EXE/hash、原WebView、清调试参数、安装根、备份和ready报告一致。
- 备份/回执：工具根`user-entry-backup`、`user-entry-deployment.json`、`user-entry-verification.json`。自选背景、用户profile、u13、模型样例与旧入口保留，未代用户启动。回退只需正常关闭新窗口后恢复这三个备份入口文件，不清安装根或用户WebView。
- 代表图：[收起首页](../../design/desktop-launcher-ui-review/sidebar-20261031/collapsed-home.png)、[展开首页](../../design/desktop-launcher-ui-review/sidebar-20261031/expanded-home.png)、[展开环境](../../design/desktop-launcher-ui-review/sidebar-20261031/expanded-environment.png)、[展开设置](../../design/desktop-launcher-ui-review/sidebar-20261031/expanded-settings.png)。结构化结果见[验收JSON](ui-sidebar-20261031-validation.json)。
- 产品基线普通push已核远端；本报告/JSON和四张原生代表图随最终文档提交保存，最终HEAD由工具`final-git-baseline.json`记录，避免提交自引用。

本轮约定施工与交付已完成，没有剩余UI实施事项。没有重测真实业务或干净Windows/WebView首装，历史真实训练结果不算本包新验收。

## CR-014追加：点击内容区收起（施工中）

用户明确追加要求：展开后点击主页面自动收起。主内容容器在pointerdown捕获阶段收起侧栏，适用于首页和其余内容页；保留原控件的点击、输入、滚动事件，不加遮挡层、不阻断点击。侧栏导航和展开开关不属于主内容，不误触收起。仅增加一行Vue事件绑定，展开宽度/动画/正文位置继续沿用CR-013。

精简验证：浏览器检查首页空白、同次点击信息tab、侧栏内部导航、管理页、坐标和减少动画；最终包只做受影响交互的原生只读冒烟，不重复旧矩阵、重开、下载、训练或启停。下一步：构建及受影响点击验证。

用户同轮追加：删除首页“让灵感，成为你的模型。”标语；NextTrainer标题改为单行，与Logo水平并排、垂直居中。保留Logo、信息卡及启动区位置，增加DOM/水平对齐小检查，不重跑旧矩阵。

浏览器定向已完成：最终资源 `index-CYZRtk0d.js` / `index-BeuXJSj6.css`，`launcher-ui-sidebar-dismiss-20261031/browser-01` 7项全部通过。标题与Logo中心Y均124px，标语段落和拆行span均为0；首页空白、同次友情链接tab、侧栏内部导航、再次展开、管理页空白、减少动态下点击收起均通过，主内容/信息卡/启动区几何保持。零页面异常、外部请求、未建模或业务变更IPC；自有浏览器和服务器正常关闭。Root已实际看首页最终图，独立只读代码复核无阻断。CR-013中“点击正文不自动收起”仅属旧版行为，以本追加为准。下一步：干净源码基线离线打包、最终EXE仅3项原生只读定向验证，通过后更新既有入口。
