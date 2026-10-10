# U3 最新dev打标与编辑UI完整适配

目标T4；依赖AC-U2。目的：在新dev页面布局中交付真实可用的打标、自然语言编辑与翻译。

## 执行步骤

1. 先读`frontend/AGENTS.md`。保留TaggerPage全宽/参数栏/ManagedDatasetPicker/全局下载源，能力驱动模型与参数，接通jobs试标/批量/进度/取消/重试/报告/回滚。
2. 预设唯一控制语言、详略、格式；英文默认且system/user全文英文。保存/另存为/恢复默认/草稿保护联通统一预设服务；旧独立输出选项不复活。
3. `ApiSettingsPage.vue`接统一Profile与默认模型一键安装，同步TagTranslationSettingsDialog及页面入口；安装ready与实际运行时状态一致，远程优先语义明确。
4. DatasetEditorPage按服务端格式显示natural raw，完整原文/只读中文译文、中文短路、Tag操作禁用、hash保存、重扫/重入与草稿恢复、取消/晚到隔离。修复空草稿遮蔽等已知回归。
5. TasksPage显示唯一任务投影，停止/隐藏/重试与打标页状态一致；WD/CL旧流程和Tag词典保留。
6. 补必要组件/交互测试和中英文文案，桌面与390px走实机浏览器；记录实际网络请求与文件结果，不只截图静态页面。

## 输出、验证与完成门 AC-U3

输出新版UI、API类型/状态管理、翻译组合函数与针对行为的回归测试。证据`docs/evidence/natural-language-captioning/dev-unification-20261010/U3/`。

前端`npm run check`通过；浏览器完成试标不写盘、批量写盘、进入编辑器看到完整caption、翻译/中文零请求、草稿切换、hash冲突、任务停止/重试。两宽度没有阻断操作的问题；范围内后端守卫再次通过。不得仅启用按钮或只恢复旧页面作为完成。

## 失败退回

接口/迁移差异回U2修复并更新契约；自然语言Tag化或漏原文属于P0/P1优先修复。不要改Agent或训练系统为页面问题兜底。完成后canonical登记实际证据，进入U4。
