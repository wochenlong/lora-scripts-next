# Tag 单图试标与持久化页面链路

2026-10-08；源码父提交35e5189；绑定Issue #409。实际模型验收尚未执行，本记录使用真实源码/API及受控fake Tag。

Tag页面批量操作已从旧/interrogate切换至同一/tagger/jobs任务链路；旧接口继续兼容。TagJobRequest显式转换recursive/conflict_action，保留Tag模型ID和阈值/后处理，不携带Caption提示词、语言、Profile或生成参数。Tag预览复用批量_prepare_tag_model/_generate_tags，不写盘。原生推理取消时直到当前调用结束并卸载才释放共享reservation，避免同时加载另一个模型。公开Tag快照仅含适用参数；自然语言不接受Tag参数，Tag不接受Caption参数。

页面统一底部任务状态/计数、开始/停止、仅重试失败项、历史报告和任务页链接；Tag保留模型预下载。报告deep-link按snapshot.mode选择模型，支持Tag。KeepAlive及独立mount均加载服务端状态。

验证：

- Tag API试标/批量配置一致、已有标注预览不改写、完全不读取LLM配置、能力参数拒绝、取消期间reservation保持：44专项通过。
- 相关Caption/LLM/Tagger/Editor来源/Tasks后端回归：299 passed / 4既有warning / 39.69秒。
- Node22完整check：341 tests / 52 files；typecheck、lint、build通过，2既有EngineStatusBar warning。最初联合类型导致一项测试未收窄类型，已明确mode判别；独立mount有2项状态测试失败，补充无KeepAlive初始化后完整复验通过。
- 实际新fake browser：默认本地WD，单图预览rectangle, white background，批量3/3，三个txt与预览字符串一致，provider请求0；snapshot仅Tag参数并归档。
- 任务页报告回到正确WD模型与UUID；390px横向溢出=false，底部开始/试标/预下载操作可见。

真实验证工具已适配本版：隔离user_data root，显式桥接任务档案；Tag工具增加HTTP预览与逐字节比对/默认跳过；自然语言工具移除combined入口，明确覆盖用于缓存复验并另验默认跳过零请求。工具修改不代表执行通过。

剩余：当前源码真实ONNX/Qwen、正式lifespan Zero-Short、最终测试矩阵、准确输出绑定的质量评分和全新隔离重建。Agent/plugin源码未修改；已有Windows symlink权限失败未核销。
