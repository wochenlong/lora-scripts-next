# Starward 视觉与技术来源调研

- 日期：2026-10-30。范围：调研与设计输入；没有改动 Next Trainer 产品代码、启动器或现有沙盒。
- 上游：https://github.com/Scighost/Starward 。已浅克隆 main，并用远端 HEAD 实时核对：`df8ae07b5ad4c9c6cb70d288488ce8073ce01478`（提交时间 2026-10-12 02:43:46 +0800）。
- 用户截图三张均为 1184×667；其中“关于”显示 Starward 0.18.2。不能把该界面版本当成当前 main 版本。
- 研究材料根：`E:/OpenSourceTeamWork/workspace/tools/launcher-ui-review-20261030/`；下文 upstream、source-excerpts、reference-assets、tauri-* 等本地路径均相对此根。

## 可直接确认的上游事实

以下链接固定至实际检查提交，不使用会漂移的 main 链接。

| 视觉/结构 | 证据 | 对本项目的设计含义 |
| --- | --- | --- |
| WinUI 3 原生实现，非网页皮肤 | [Starward.csproj L4](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Starward.csproj#L4)：net10.0；L14 UseWinUI；L47 WindowsAppSDK1.8 | 复刻视觉语言不要求迁移框架；XAML不能原样粘贴进Vue |
| 全窗艺术背景，侧边栏不占大块纯色面板 | [MainView.xaml L16](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/ViewHost/MainView.xaml#L16)；L19 Width56；L33–38 LeftCompact | 保留56px图标栏、完整背景、底部设置入口，增加本项目日志入口 |
| 侧栏宽56，主内容顶部保留48 | [MainView.xaml L34](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/ViewHost/MainView.xaml#L34)；L141 Frame Margin0,48,0,0 | 与三张截图的比例可直接对照 |
| Acrylic两种材质强度 | [App.xaml L43](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/App.xaml#L43)：CustomAcrylic TintOpacity0.6、Overlay0.4、fallback #F52C2C2C | CSS图内背景模糊应使用独立变量，不把0.6当成普通opacity直接套整页 |
| 首页清晰背景、其余页面磨砂遮罩 | [MainView.xaml.cs L224](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/ViewHost/MainView.xaml.cs#L224)：Launcher/Blank OverlayMask0，其他1 | 首页体现主视觉，版本/环境/日志页使用同一图的模糊暗色层 |
| 背景cover裁切与右侧暗角 | [AppBackground.xaml L23](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/Background/AppBackground.xaml#L23)：UniformToFill；L33/L46/L60右上/右下/右边渐变 | 大图要设焦点与文字安全区，不能仅放一个纯色渐变替代 |
| 背景到主题色的联动 | [AppBackground.xaml.cs L304](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/Background/AppBackground.xaml.cs#L304)：像素提取AccentColor；L338–341同路径 | 本期可先用截图一致的蓝灰按钮；后续图片取色须另行设计对比度 |
| 主窗1200×676，标题栏48 | [MainWindow.xaml.cs L47](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/ViewHost/MainWindow.xaml.cs#L47)：ExtendTitlebar；L52 CenterInScreen1200,676；L54 dragRect48 | 设计基准建议1200×676；本项目是否保留可缩放是自身决定，不能照抄禁用最大化/缩放（L59–60） |
| 首页左下380宽内容块 | [GameBannerAndPost.xaml L21](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/GameLauncher/GameBannerAndPost.xaml#L21)：Width380，圆角8；L30–31图176+文124 | 本项目可放版本/最近操作/环境摘要，不引入游戏活动公告功能 |
| 首页面板与主操作的锚点 | [GameLauncherPage.xaml L507](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/GameLauncher/GameLauncherPage.xaml#L507)：左下Margin60,0,0,40；L514右下Margin0,0,40,0 | 复制左下信息/右下主操作的构图，替换为启动训练器/打开网页/停止 |
| 右下主操作44高、22圆角、最小180宽 | [StartGameButton.xaml L94](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/GameLauncher/StartGameButton.xaml#L94) | 主操作胶囊可直接复用尺寸体系；健康就绪时显式显示打开网页，与停止并存 |
| 设置二级导航260宽 | [SettingPage.xaml L19](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/Setting/SettingPage.xaml#L19)：OpenPaneLength260；L34标题20；L102右栏Margin24 | 环境页与设置页可用左目录/右设置，避免卡片堆叠 |
| 详情双栏/底部固定操作条 | [GameSettingPage.xaml L12](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/GameSetting/GameSettingPage.xaml#L12)：底部60高；L19 Margin24,20,24,24、ColumnSpacing24 | 对应本项目环境/网络设置的布局参考，业务字段仍用实际能力 |
| 日志为每日文件，带时间/级别/进程/来源 | [AppConfig.ServiceProvider.cs L44](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/AppConfig.ServiceProvider.cs#L44)：Serilog File shared | 可借鉴日志字段与定位，不代表上游有我们要的独立日志页 |
| 上游文件管理可打开日志目录 | [FileManageSetting.xaml.cs L273](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/src/Starward/Features/Setting/FileManageSetting.xaml.cs#L273) | 本轮“侧栏日志页”来自用户明确需求，应按本项目进程/安装/训练日志设计 |

## 视觉采集与约束

已留存三张用户截图原样副本，以及 README英文/中文各一张官方示例（原始WEBP，1778×1001，HTTP200）。每份素材记录原URL、字节数、SHA256、用途；官方截图分别由 [README](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/README.md) 与 [中文README L83](https://github.com/Scighost/Starward/blob/df8ae07b5ad4c9c6cb70d288488ce8073ce01478/docs/README.zh-CN.md#L83) 引用。素材保留在外置研究目录，不混入产品资源。

截图提供的复刻基准是窄图标栏、全幅插画、半透明蓝黑材质、低对比边界、白色20px页面标题、14px正文、右下44px胶囊主操作。设置页的大留白和低密度表单也是构图的一部分，不能变成常见后台仪表盘。

像素取样（`sampled-palette.json`，区域中值；已经包含背景/透明合成，不是上游固定Theme token）：侧栏约 `#141E28`，主操作/强调约 `#8495B2`，设置选中块约 `#3B4448`，底部材质约 `#3C494C`。不把截图取样当作WinUI原始颜色常量。

背景、人物、游戏logo和Starward猫图标属于不同来源；软件MIT不自动覆盖游戏艺术或第三方字体。评审稿可明确标为用户参考图的视觉研究素材，正式包需使用本项目自有/授权图或用户选择图片。直接复用上游MIT代码段需保留版权和许可；本项目AGPL-3.0-or-later不会因此改成MIT。

## 与本项目技术栈的差异

本项目 `desktop-launcher/package.json` 固定 `@tauri-apps/api 2.12.4` 与 `vue 3.5.44`；Rust `Cargo.toml` 为Tauri2；当前 `tauri.conf.json` 窗口900×600/min760×520，尚未声明自定义标题栏。设计保持Tauri/Vue，不迁移WinUI。Starward的WinUI Acrylic是原生合成效果；CSS `backdrop-filter` 是WebView内部图层模糊，不能宣称1:1原生材质或已获得同等性能。可以对图内材质做可控视觉近似；是否启用原生窗口effect须后续Windows样机验证。

官方Tauri2文档已逐个实际读取HTTP200，并保存在 `tauri-*.html` 与 `official-docs-index.json`：

- [自定义窗口标题栏](https://v2.tauri.app/learn/window-customization/)：`decorations=false`，`getCurrentWindow().minimize()/toggleMaximize()/close()`，必须配置所需窗口capability；`data-tauri-drag-region`只对直接标记的元素生效，交互控件需留在非拖动区；也可显式`startDragging()`。
- [Rust调用前端](https://v2.tauri.app/develop/calling-frontend/)：`Emitter::emit`/webview定向事件，前端`listen`；组件卸载时调用返回的`unlisten`。可用来设计服务状态推送，但本项目目前是否已有该链以本地源码审查为准，文档不是实现完成证据。
- [Event API](https://v2.tauri.app/reference/javascript/api/namespaceevent/)：`listen/emit/emitTo`、监听器释放；状态最终以权威snapshot校准，不能只依赖可能错过的事件。
- [Window API](https://v2.tauri.app/reference/javascript/api/namespacewindow/)：Mica标明Windows11 only；Acrylic标明Windows10/11，且提示Windows10 v1903+与Windows11 build22000上拖动/缩放性能较差。非支持系统应降级到静态暗色/预模糊背景，不把Mica设为必需依赖，也不扩大原Windows最低版本。

以上是官方能力和限制的文档事实，不是已在本项目验证过的效果。本轮不添加窗口权限、不改标题栏、不打开或停止用户服务。

## 提交给主设计的建议

1. 首页按截图1的构图复刻：56px侧栏、48px标题区域、左上项目标识、右下胶囊动作、左下紧凑信息块。
2. 版本/环境/日志/设置沿用同张图的模糊暗色材质。环境/设置使用260px内侧二级导航；日志使用尽可能宽的正文空间。
3. 日志不在每个页面底部重复展示。其他页只保留当前操作状态和“查看日志”跳转；侧栏日志页提供时间、级别、来源、操作/服务会话、搜索、自动滚动、复制/导出，并保持切页日志采集。
4. 启停动作区的布局和服务状态分离；日志文字“启动成功”不直接驱动按钮。健康探针成功及时亮出“打开网页”，owned进程退出及端口释放及时恢复启动动作；精确调用链与指标交由本项目性能调研决定。
5. 初次评审至少提供首页、环境页、日志页、设置页以及启动中/服务就绪/停止中/已停止/错误的交互演示；不把静态mock描述为产品实现。
