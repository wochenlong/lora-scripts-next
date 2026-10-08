# Issue #409 当前源码真实Tag、本地Caption和Zero-Short

2026-10-08；业务源码6829ec8；Python3.11.15、Node22.17.1。该轮使用新输出/配置/SQLite/user_data目录，但复用中间验证资产和依赖，不属于Phase5从零重建。

## 真实Tag

工具：tools/verify_caption_real_tag.py；固定公开样本及SHA见旧冻结manifest（仅复用样本定义）。真实wd14-convnextv2-v2 / revision bf364499ea843a403cc2770072f31f5cfb2ffa58，model.onnx SHA e91daa19cd9e8725125b7d70702d1560855fb687f8d8c4218eddaa821f41834a，selected_tags.csv SHA 8c8750600db36233a1b274ac88bd46289e588b338218c2e4c62bbc9f2b516368。

三图新旧Tag逐字节一致，HTTP单图预览与批量结果一致，预览无txt写盘；Tag数13/11/8。已有标注明确ignore后skipped3/succeeded0。任务config/task档案存在。总12.451秒。请求执行器包含CUDA但缺少cublasLt64_12.dll，ORT自动使用真实CPUExecutionProvider；未宣称GPU通过。模型逐图卸载。

## 真实本地Caption

工具：tools/verify_caption_production.py --local（仅natural）。模型Qwen3VL-2B-Instruct-Q4_K_M.gguf SHA 089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae；Q8 mmproj SHA f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82；llama.cpp b11327，llama-server.exe SHA 32d43779061d318ab36d0cf8156f314f81ac7e5b805298b7fe9facf3cf0cc82d。模型revision 52d6c8ffea26cc873ac5ad116f8631268d7eb503。

- 三张图片3/3，strict JSON/语言/长度校验通过；启动4.540秒，批量16.334秒，峰值RSS 3,068,416,000字节。
- 请求4次、JPEG data URL4次（批量3+单图1），模型已停止。
- 明确copy的缓存重放命中3、零新增请求；另验ignore跳过3、零请求；预览未改变txt。
- config/task档案存在；safe model snapshot包含managed-local模型身份/能力/revision，未包含凭证。
- profile_revision 970dfbb537a07d93a082a1c2，prompt_revision f27bd880bde909f515423f53。

三条文本SHA与用户此前评分的B组精确一致：chelsea 8aea8bddb74ef798e5761bb362e25d9d3b19222a3c8bd2827dead6cd6c01cf1c；coffee e69d511397aebf1aaedaa493127e17ac97e7e930d30048724e0d1855ee5866a9；rocket 20ff84d8abb6428fddd34312416fb07f3933e35b4a32d083811f6780bf122f67。仅这些相同文本引用原human-evaluation-approval.json的五维4分记录，不声称用户进行了新的评分，不扩大至其他提示词/输出。

## 正式Zero-Short

工具：tools/serve_caption_acceptance.py，actual FastAPI lifespan=on及最新源码构建的dist。修正harness的user_data隔离环境变量后，用全新root验证，无Profile/Key/词库/视觉模型/runtime/预设/任务：LLM config、local-vision status、tagger status、prompt-presets、jobs、tasks均HTTP200，词库status=missing/installed=false。无配置connection-test明确失败，HTTP502/llm_capability_vision_required，不发起模型请求。

实际UI：API标签数量0，Qwen生成禁用，显示“安装本地视觉模型和运行时”按钮；390px横溢出false。系统提示CPU torch不支持训练GPU，但应用继续启动，未把该提示算打标失败。最初浏览器检查未展开模型系列且误用placeholder查找search，超时后按实际summary+type=search重做通过；没有用强制点击代替可操作性验证。

服务已停止，浏览器about:blank，tracked dist恢复源码基线。资产与数据库仅保留在私有sandbox用于后续审计，未加入Git。尚未运行新契约远程实际路径；已有历史remote-first与fake回归保持原边界。Phase5未开始。
