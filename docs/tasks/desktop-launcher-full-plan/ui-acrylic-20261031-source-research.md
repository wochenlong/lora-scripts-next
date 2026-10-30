# CR-012：Starward 亚克力界面源码复核

本报告支撑 2026-10-31 用户要求的界面重做：尽可能还原 Starward 的字体、材质、渐变、按钮、下拉框、容器与动态效果；首页保持清晰海报和侧栏分区，其他页面与侧栏共享连续的亚克力背景；删除深浅色选择。项目 Logo、Qwen-Image-2.1 默认海报、项目信息卡封面及训练器业务按 Next Trainer 的实际需求保留。

## 1. 来源与核查边界

- Starward 仓库：<https://github.com/Scighost/Starward>。
- 逐命令通过 `127.0.0.1:11809` 代理执行 `git ls-remote … HEAD`，远端 HEAD 为 `df8ae07b5ad4c9c6cb70d288488ce8073ce01478`；已有只读源码目录 HEAD 与远端一致，工作区干净。
- 本地源码：`E:/OpenSourceTeamWork/workspace/tools/launcher-ui-review-20261030/upstream/Starward`。
- Starward 的 `src/Starward/Starward.csproj:47` 使用 Microsoft.WindowsAppSDK `1.8.260804001`，并非 HTML 控件。为解开其标准画刷和控件资源，本次另读取 Microsoft 官方 WinUI 源码同代 release 1.8.11，提交 `ba3b6cd989b4bac7c82791ad76a28d837bbf903b`。此标签不等于上述 NuGet 包的逐字节源码，以下将 Starward 显式参数与 WinUI 同代实现分开表述。
- WinUI 官方主线 `8194eb3c1a21b86c16ad4c2de0ddf549f1dddd2d` 也进行了交叉核对，关键材质常量、暗色画刷、字号与 1.8.11 一致。正式数值引用以下均采用 1.8.11 的路径和行号。
- 官方下载摘录和树索引保存在 `E:/OpenSourceTeamWork/workspace/tools/launcher-ui-acrylic-20261031/source-research/`；`release18-` 文件对应 release 1.8.11。调研未构建或运行 Starward。用户截图提供视觉目标，不能用静态截图推断某个动画已经实测。

## 2. 核心结构：一个全窗材质层，而非每页各自变暗

源码永久链接基准：<https://github.com/Scighost/Starward/tree/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward>。

| 项目 | 已核实源码 | 对启动器的含义 |
|---|---|---|
| 原始背景 | `Features/ViewHost/MainView.xaml:16` 首先放置 `AppBackground`；`Features/Background/AppBackground.xaml:23` 图片居中，`Stretch=UniformToFill` | 一张图片按整窗坐标覆盖，CSS 对应 `center / cover`；不能从 56px 后另起图片，否则边栏颜色与正文错位 |
| 永久侧栏材质 | `MainView.xaml:19` 左侧宽 56，`Background=CustomAcrylicBrush` | 首页仅左侧为亚克力，正文保持原图；侧栏宽度保持 56px |
| 全窗管理材质 | `MainView.xaml:24` `Border_OverlayMask` 覆盖整个 Grid，使用相同 `CustomAcrylicBrush`，初始透明度 0 | 管理页应直接覆盖全窗，不另做更深的导航条、二级导航背景或蓝色底板 |
| 页面分支 | `MainView.xaml.cs:208` 的 `NavigateTo`；首页／空白页在 `:226` 将覆盖透明度设为 0，其他页在 `:230` 设为 1 | 用户补充的“主页有侧边分界，其他页面同材质”有直接源码依据 |
| 导航和标题区域 | `MainView.xaml:34` `CompactPaneLength=56`；`:141` Frame 顶部 margin 48 | 主内容起点 `(56,48)`；管理材质继续覆盖标题栏与侧栏，不在 y=48 处截断 |
| 窗口 | `MainWindow.xaml.cs:47` 标题栏扩展到内容，`:49` Tall；`:52` 默认 1200×676，`:54` 拖拽高度 48 | 我方保留可缩放窗口，但以约 1200×676 和用户截图 1184×667 为主要对照尺度 |

原版层级是「整窗图片 → 左 56px 亚克力 → 可淡入的整窗亚克力 → 导航／页面」。HTML 重建可以用共享全窗亚克力图层，在首页裁出左侧，在管理页显示全窗；管理页导航本身透明，避免重叠材质造成侧栏变暗。这样保留视觉语义，而不用机械复制多次采样的 WinUI 渲染图。

## 3. 材质配方：模糊、亮度混合、着色、颗粒

### 3.1 Starward 显式画刷

`App.xaml:44` 定义 `CustomAcrylicBrush`：`FallbackColor=#F52C2C2C`，`TintColor={ThemeResource ControlOnImageFillColorDefault}`，`TintOpacity=0.6`。`:48` 的 `CustomOverlayAcrylicBrush` 同样设置，但 `TintOpacity=0.4`。导航默认背景、对话框、弹出面板也指向这些画刷，见 `App.xaml:54`、`:58`、`:63`。

这些参数不等于「背景上直接覆盖 60% 黑色」。颜色本身包含 alpha，WinUI 还会计算亮度层和修正 tint 强度。原有 CSS 的整窗 `brightness(.53)` 加深蓝遮罩会显著压暗背景，和截图中仍清晰可辨的青、紫、红色块不同。

### 3.2 WinUI 同代实现

官方源码基准：<https://github.com/microsoft/microsoft-ui-xaml/tree/ba3b6cd989b4bac7c82791ad76a28d837bbf903b/src/controls/dev>。

| 参数 | WinUI 1.8.11 文件与行 | 数值 |
|---|---|---|
| 暗色图上填充色 | `CommonStyles/Common_themeresources_any.xaml:33` | `#B31C1C1C`，A=179，RGB=(28,28,28) |
| 主文字 | 同文件 `:5` | `#FFFFFF` |
| 次要文字 | 同文件 `:6` | `#C5FFFFFF`，约 77.3% 白色 |
| 普通控件填充 | 同文件 `:15` | `#0FFFFFFF`，约 5.9% 白色 |
| 控件悬停填充 | 同文件 `:16` | `#15FFFFFF`，约 8.2% 白色 |
| 控件边界 | 同文件 `:38` | `#12FFFFFF`，约 7.1% 白色 |
| 高斯模糊 | `Materials/Acrylic/AcrylicBrush.h:64` | `sc_blurRadius=30.0f` |
| 颗粒强度 | 同文件 `:65` | `sc_noiseOpacity=0.02f` |
| 模糊边缘 | `Materials/Acrylic/AcrylicBrush.cpp:523` | Hard；避免边缘透明混入 |
| 噪声叠加 | 同文件 `:532` 起 | 噪声纹理无限重复，以 2% opacity 在材质上 SourceOver |

`AcrylicBrush.cpp:189` 计算有效 tint；`:209` 按 HSV 明度和饱和度压缩 tint alpha；`:278` 计算 luminosity 层；`:380` 起实现 luminosity/color 两层混合；`:519` 起先模糊再混合，最后加入噪声。注释说明 Win2D 内部 `Color` 与 `Luminosity` 枚举名存在交换问题，不能把内部枚举字面值直接当作 CSS 混合模式。

以本次固定暗色视觉和 `CustomAcrylicBrush` 为例，可复算的近似值是：

- 输入 alpha 为 `179 × 0.6 ≈ 107`。
- 灰色 tint 的 HSV V 为 `28/255`；修正系数约 0.861，有效 tint alpha 约 `92/255=0.361`，RGB 仍为 `#1c1c1c`。
- luminosity 的 V 至少钳制为 0.125，即 RGB 约 `#202020`；其 alpha 映射到 `0.15 + (107/255) × (1.03-0.15) ≈ 0.519`。
- 最终不是两个普通黑层相加，而是保留背景色相的 luminosity/color 合成，再叠加 2% 噪声。

我方应重建这一材质结构：全窗共享约 30px 模糊、降低局部对比但保留背景大色块、灰色亮度混合与细小颗粒；不得用浓重纯蓝填充来替代。浏览器 CSS blur 的边缘和 Windows Composition 不会逐像素一致，因此最终参数仍须以实际 WebView 截图对照调整。报告中的原版配方不是对当前实现已经像素一致的声明。

### 3.3 原图渐变

`Features/Background/AppBackground.xaml:33` 和 `:46` 分别在右上、右下放置 400×400 矩形，方向分别向右上／右下；渐变前 50% 透明，末端 `#50000000`。`:60` 右侧另有 200px 宽竖条，从左透明到右端 `#30000000`。这只是边缘保护，不是从整张图片左侧到右侧的深蓝全幅遮罩。首页尤其应避免全幅暗膜损失海报亮度。

## 4. 字体、尺寸与控件

Starward 未给正文注册自带字体，使用 WinUI 自动字体回退；`App.xaml:66` 仅给图标配置 Segoe Fluent Icons。WinUI `CommonStyles/TextBlock_themeresources.xaml:11` 使用 `XamlAutoFontFamily`，正文 14、说明 12、较大正文 18、小标题 20、标题 28，见 `:3`–`:8`。英文可由本机 Segoe UI 系列呈现，简中使用本机 Microsoft YaHei UI 等系统回退；HTML 不能声称与 XAML 的逐字形回退和栅格化完全一致。应使用本机字体，不复制、分发 Windows 专有字体文件。

| 元素 | 已核实结构 | 我方复刻要点 |
|---|---|---|
| 常规文字 | WinUI Body 14，Caption 12；`Setting/ToolboxSetting.xaml:49` 卡片说明显式 12 | 主正文与按钮14px，元信息／说明12px，避免全部缩成12px |
| 设置二级栏 | `Setting/SettingPage.xaml:23` 宽260；`:34` margin 16,12,0,8，标题20 Bold | 流式透明导航；选中行用少量白色填充、左侧强调短线，其他背景保持连续 |
| 设置正文 | `SettingPage.xaml:102` margin 24,24,0,0 | 在标题48px之后保持24px顶部／左侧空间；设置项直接排版 |
| 设置分节 | `Setting/GeneralSetting.xaml:22` 等显式20px；行间12px或20px | 大块透明留白、细分隔线；避免给每条说明套实体卡 |
| 下拉框 | `GeneralSetting.xaml:23` 高36、最小宽260，左padding18.5，无边框，圆角8,18,18,8 | 特定长选择器为右端胶囊；其他普通下拉使用标准较小圆角，不全局强制胶囊 |
| 普通下拉 | `ComboBox/ComboBox_themeresources.xaml:32` 等跟随淡白控件填充、细边、系统字体与箭头 | 展开浮层与闭合按钮必须一起统一材质；只改原生 `select` 背景仍无法还原弹出菜单 |
| 工具卡 | `ToolboxSetting.xaml:18` 宽180高220；图标40，图片48；顶部区域100；行距8 | 轻微白色半透明填充、细边和低圆角，背景大色块透出 |
| 启动按钮 | `GameLauncher/StartGameButton.xaml:94` 高44，最小宽180，圆角22，主题阴影Z=16；`:36` 背景BrushTransition 83ms | 胶囊强调色、轻阴影，避免厚边、亮光或强烈放大 |
| 首页信息卡 | `GameLauncher/GameBannerAndPost.xaml:21` 380×304，圆角8；图片区176、正文124；Tab16 Bold；阴影Z=16 | 沿用此前用户要求的适度放大尺寸，改成相同亚克力正文与Tab材质；不要误换信息卡封面 |
| 首页布局 | `GameLauncher/GameLauncherPage.xaml:508` 信息卡 margin60,0,0,40；右下操作区margin0,0,40,0，底部40px行 | 卡片与按钮沿同一视觉基线；我方保留之前已确认的位置和功能 |
| 对话框／弹层 | `App.xaml:57` 默认 ContentDialog 与 Flyout 背景指向CustomAcrylic，Flyout边框0 | 二级弹层同材质、有阴影，不出现系统白菜单或浓蓝面板 |

强调色并非 Starward 固定“品牌蓝”。`Features/Background/AccentColorHelper.cs:69` 起对背景隔像素采样，计算平均RGB，再将HSV饱和度设为0.6；`:109` 起混合白／黑生成多个系统强调色。截图中的灰蓝按钮由当前海报与该算法产生。可针对 Next Trainer 海报选择相近低饱和强调色，或同样从背景计算；不得称截图颜色就是 Starward 的固定源代码常量。

## 5. 动效与交互

| 动作 | 源码事实 | HTML／WebView 的实现要求 |
|---|---|---|
| 页面材质切换 | `MainView.xaml:27` 的 OpacityTransition 使用 `ScalarTransition`，未写自定义时长 | 对全窗覆盖层做短暂透明度切换；以连续材质为主，减少动态效果时直接切换。不能把猜测时长标为Starward显式值 |
| 页面导航 | `MainView.xaml.cs:223` Frame.Navigate 使用默认导航，只有换游戏时 `:117` 明确 SuppressNavigationTransitionInfo | 适度进入过渡，保留已挂载业务状态，不通过销毁整个页面重置日志／操作 |
| 背景加载 | `Background/AppBackgroundImageExStyle.xaml:45` 新图300ms淡入；旧占位图延迟300ms再以300ms淡出 | 首次／替换背景连续淡入，减少动态效果时禁用 |
| 按钮悬停／按压 | `StartGameButton.xaml:36` 83ms；普通状态对应DefaultButtonStyle的资源 | 短材质色变化，完整Normal、Hover、Pressed、Disabled、Focus，不用大幅缩放 |
| 下拉展开／收起 | WinUI `ComboBox_themeresources.xaml:395` 展开opacity250ms，`:401` 收起167ms | 自绘浮层保持鼠标、键盘、失焦收起、Escape、屏幕边缘定位与滚动；不能只做静态画面 |
| 通用缓动 | WinUI `Common_themeresources_any.xaml:578` `ControlFastOutSlowInKeySpline=0,0,0,1` | CSS `cubic-bezier(0,0,0,1)` |
| 通用时长 | 同文件 `:579` Normal250ms，`:580` Fast167ms，`:582` Faster83ms | 共用时长token，减少杂乱不同步 |
| 通知 | `MainWindow.xaml:20` 宽度最大600、margin24,72,24,72、底部堆叠；AddDeleteThemeTransition | 底部短暂反馈与错误保留，不重新引入各页固定状态条 |

## 6. 本轮实施与验证映射

本报告只负责调研，产品改动与最终验证由主任务记录。建议验收包含：

1. 首页原图清晰、边栏有单独材质；切换任一管理页后，同一图片坐标和同一亚克力配方覆盖全窗，导航与正文之间不出现深色断层。
2. 页面、设置分类、日志、版本列表、环境卡、导入和安全弹层统一文字、按钮、输入、选择器和容器材质；既有错误／取消／恢复功能仍可访问。
3. 深浅色选项完全删除，历史保存的theme字段不再影响当前材质；保留本地背景、字号与减少动态效果配置及用户数据。
4. 下拉菜单实际展开，验证浮层材质、键盘与边界；检查按钮焦点／禁用态、透明度动画及减少动态效果。
5. 浏览器与最终原生WebView截图均需真实查看，至少包括首页、管理页、设置、日志及展开下拉。几项DOM数值相同不能替代视觉验收。

WinUI 的 Composition acrylic、DPI字形栅格化、AnimatedIcon 的系统动画与网页实现存在技术差异。目标是在当前 Tauri/WebView 架构内复刻视觉和操作反馈，不在本轮重写原生WinUI外壳。任何“所有效果逐像素完全一致”的结论都需要额外证据，不能由源码参数一致直接推出。

Starward 和 WinUI 源码均提供 MIT 许可；若实际移植具有实质内容的源码，应保留相应版权声明。项目自己的 Logo、海报与封面继续使用现有资源，不复制目标项目的游戏素材或打包 Windows 字体。

## 7. 修复后的独立浏览器视觉复核

2026-10-31 独立查看了 `workspace/tools/launcher-ui-acrylic-20261031/browser-02/` 的实际截图：1184×667 首页、环境管理、外观设置、日志、展开的字号下拉，以及1024×640首页与环境管理。对应前端资源为 `index-Beuu4fHA.js`、`index-Ch2v-Bhn.css`；浏览器报告为43项检查、15组布局通过且没有页面脚本错误。此处结论只属于 MS Edge 独立临时配置的浏览器版本，尚不能替代最终 EXE 的原生 WebView 验证。

此前两项缺陷已修复：首页版本、品牌标题与标语现在根据局部背景亮度选择深／浅文字，在默认 Qwen 海报上清楚可读；管理页实际使用 `backdrop-filter:url("#fluent-acrylic")`，SVG定义包含30px模糊、0.51925亮度层和0.36078颜色层，避免了独立像素探针中CSS子层重复混合的偏暗结果。截图中背景大色块保留，侧栏、标题区与管理内容连续；没有恢复全幅白膜或另加深色侧栏。

环境操作、设置字段、日志正文和筛选控件均可辨认；展开下拉的选择行、焦点、边界与浮层层级清楚，没有在所查尺寸看到遮挡主要操作或横向溢出的阻断。项目Logo、海报、信息卡封面与Next Trainer自身功能结构得到保留，深浅色选择入口已删除。本轮未发现需要阻止进入原生打包验证的视觉问题。

边界：当前海报与参考图不同，管理背景自然呈现不同色相和亮度，本复核不要求复用目标游戏壁纸；也未宣称字体栅格化、系统动画或材质输出与WinUI逐像素一致。动画、键盘和配置迁移的运行检查以同目录浏览器报告为准；本次独立复核没有运行训练、下载、安装或启停服务。
