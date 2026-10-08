# 真实浏览器、本地模型、编辑器与验收修复

2026-10-08；后端起始基线6829ec8，本记录与对应前端/取消/归档恢复修复一并提交。中间验证复用探针资产，不是Phase5。

## 真实UI生成与停止

正式lifespan服务，真实Qwen3-VL-2B/Q8 mmproj/b11327。通过页面启动本地模型、明确开启fallback，单图预览和三图批量3/3成功，natural来源、实际模型身份、提示词修订和user_data任务档案正确。此轮使用UI默认系统提示词，prompt_revision为543e625a7759e434bf355f7e。

从任务页实际停止生成中的模型任务：停止前phase=captioning，最终cancelled/succeeded0/cancelled1，TaskStatus=TERMINATED，零txt。原生模型运行时随后通过页面停止，进程检查确认没有该环境的llama-server。

最初两次取消检查的定位器错误（未展开系统提示词、误认确认按钮/停止按钮文本），模型正常完成，不算取消通过。用新目录和实际控件文本重做后通过。过程中发现打标弹窗仍标题“终止训练”，已改为“停止打标”和保留完成结果的说明。

猫、咖啡文本SHA与旧B组评分精确一致；火箭UI输出SHA为1df733846810cc99cf4eda6293dc739c2a35a21caa081ee7e77ab51932d466ef，已单独向用户请求五维人工评分，尚未回复，不能沿用旧火箭评分。

## 编辑器安全

真实模型输出加载进编辑器后显示natural，Tag清理/排序/拖拽/批量Tag禁用，Tag chip数量0。按原文保存为单字“猫”仍记录natural/tags=[]。实际撤回与重做保留格式，撤回恢复原始完整文本和换行。

在测试拥有的公开样本副本中模拟外部修改，UI保存返回409并提示刷新，磁盘保留外部内容；刷新后来源unknown，Tag操作继续禁用，用户未保存草稿保留。测试结束将副本恢复冻结原始SHA。首次手工SQLite查询未按Windows normcase规范化路径，结果null；按实际存储键复验得到natural/tags=[]，不是生产来源丢失。

## 修复与验证

- 输出语言下拉框只展示模型声明支持的语言，Qwen实际为zh-CN/en；不支持的旧草稿显示提示，不自动丢弃。
- Escape取消模板切换时，正文和实际presetId保留，但原生select原先仍显示新模板；已将选择提交交给父组件，取消后下拉框和草稿都保留，浏览器复验before/after均为空ID，Tab进入预设名称控件。
- 批量Tag取消原先只设置job事件，下载器使用另一个共享事件；现在同步请求下载取消，TaggerCancelled计入cancelled而非failed，未启动推理或写盘。专项覆盖实际任务回调→共享下载事件→终态。
- Tag下载进度放在模型旁，本地视觉安装/运行时控件移到模型旁；终态刷新模型目录的下载状态，保留提示词草稿。
- 损坏的合法JSON状态/计数/时间戳不能阻止其他档案恢复；不可用档案根目录保留错误并保持恢复入口可用。

修复后专项50 passed/2 warning；前端Node22完整check 342 tests/52 files，typecheck/lint/build通过，2个既有EngineStatusBar warning。完整功能矩阵需在本批提交后复跑。所有自建模型/服务停止，浏览器blank，tracked dist恢复；私有证据和公开样本副本保留在sandbox，不入Git。
