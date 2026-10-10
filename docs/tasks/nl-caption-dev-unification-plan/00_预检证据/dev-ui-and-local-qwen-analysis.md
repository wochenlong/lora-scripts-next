# 最新 dev 的 UI 适配与本地 Qwen 选型分析

日期：2026-10-10（Asia/Shanghai）。本轮范围：推送当前版本、独立拉取最新 dev、代码差异及模型资料分析。适配实现、模型下载和新模型实测不在本轮执行范围。

## 1. 同步结果与来源

| 项目 | 固定版本 / 位置 | 核验结果 |
|---|---|---|
| 已推送功能分支 | feat/NL-Captioning，21571c5ef72a61a5cd10203596e2653e37b2a8c4 | push 成功；ls-remote 确认一致 |
| 独立 dev 分析副本 | E:/OpenSourceTeamWork/workspace/branches/dev-ui-analysis-20261010 | detached worktree；源码 clean |
| 最新 dev | d9535c356c58c78f0f6b406538f861bafb04bb38 | fetch 成功；ls-remote 与分析副本一致 |
| 两分支共同基线 | fc193789c46f6724bfcc92e203644ba3f77db995 | merge-base 核实 |
| 分叉情况 | 功能分支独有 41 个提交，dev 独有 61 个提交 | rev-list --left-right --count |
| 未提交的无关测试 | tests/test_diffsynth_review.py | 未纳入提交；推送前后 SHA256 一致 |

推送内容包含完整多语言模板、预设统一控制语言/详略、缺省提示词按语言解析、相关测试和证据。32 个文件在提交前完成范围及密钥模式检查。依据现有版本的真实执行日志：前端349项/53文件、typecheck/lint/build通过；Caption后端133项通过。没有新增业务代码修改后沿用这些检查。此结果不代表最新 dev 或未来合并结果已经通过测试。

Git 网络均使用127.0.0.1:11809的每命令代理。Windows schannel握手失败后使用每命令OpenSSL；独立clone传输曾截断。最终按工作区裸仓库/worktree规则 fetch 最新dev，再建立独立目录，Git对象可共享、工作目录独立。未完成clone残留保留于 dev-ui-analysis-incomplete-20261010，未覆盖已有分支或用户手测环境。

## 2. dev 的变化，以及当前缺口

### 2.1 打标页：新版界面已经具备接入位置，真实自然语言链路仍未接入

`frontend/src/pages/TaggerPage.vue` 采用全宽工作区、方法和来源选择行、按族分组的模型选择、运行进度，以及可关闭的参数侧栏。参数按模型、标签、高级分组；使用 `ManagedDatasetPicker` 选择托管数据集或服务端路径。下载源从全局设置取得，页面不再单独要求填写下载端点。

当前 dev 方法行只启用 Tag，Caption 按钮 disabled；来源行只启用本地，API disabled。高级面板确有自然语言模板 CRUD 与语言字段，但 `start()` 仍只提交 `TaggerRequest` 到 `/api/interrogate`，自然语言 prompt/language 不进入生成请求。不要把模板可保存当作自然语言生成已完成。

我们分支具备真实 natural/tag 单模式任务、视觉能力检查、模型目录、单图试标、报告、取消、失败重试、历史回滚、文件哈希保护。适配需要将这些能力接入新版布局，并替换占位；不能只修改 disabled 状态或只保留旧版整个页面。

### 2.2 编辑页：新的自由文本编辑可以承载 Caption，但仍缺少格式保护

`DatasetEditorPage.vue` 已增加图库选择、可收起侧栏、缩略图/原图预览、Tag/自由编辑模式、自动扩展高度的文本框，翻译设置入口移到齿轮菜单。选择范围、文件删除、筛选及分页也有变化。

但是，dev 的 `captionMode` 默认 tags，`captionTags` 对整个 `caption` 执行 `splitCaptionTags`。`DatasetItem` 尚无 `caption_format`、`natural_text`、`caption_sha256`；通用保存没有预期hash。新自由编辑模式只是展示方式，不能单凭“选了raw”证明文件本身安全。直接采用新版逻辑会让自然语言默认成为chips，仍可拖拽/Tag批量操作。

迁移要求：服务端来源/格式为安全依据；natural 自动进入自由文本，禁用 Tag 模式与Tag变更，整段中文译文只读显示；Tag 用户仍可自由编辑，但raw模式不能把真实Tag格式改成natural。mixed/unknown 保留既有保护。自然语言批量Tag清理/排序/去重必须同时在前后端拒绝，图片删除与原文保存按各自既有授权/冲突保护工作。保留草稿、重新扫描、恢复磁盘原文、切图取消翻译和过期响应隔离。

### 2.3 全局 API 设置：界面方向合适，后端仍需统一

dev 新增 `/settings/api`、`ApiSettingsPage.vue`，将endpoint/model/key与本地运行时集中到设置页，编辑页只选择翻译来源。这符合打标/翻译共用管理的方向。

但它目前读写 `/api/tag-translation/config` 的 `remote_profiles`、`active_remote_id`、`llm_mode`，安装的仍是旧纯文本0.8B。我们的统一层使用 `/api/llm/*`、text/vision能力、语言、可用状态、远程优先/本地显式兜底和运行时密钥注入；只替换页面外观会出现两份来源状态。

dev 翻译弹窗可选择词典/本地/API，`llm_mode=local` 可驱动旧翻译优先走本地。这与用户已锁定的“LLM远程始终优先、本地显式兜底”不一致。自然语言译文必须走共享text路由，不得走Tag词典。保留Tag词典选项；LLM来源的展示语义要调整为远程配置及可选本地兜底。

源码中 `OnlineServiceConfig.save()` 会将包含api_key的完整config落盘，只有响应做掩码。新版UI适配应使用当前分支运行时注入、持久数据仅保存掩码的链路。不得为了接新版设置页回退到旧明文保存，也不要修改Agent认证系统。

### 2.4 预设与任务：两边都有持久化，必须收敛存储

dev 的 `frontend/src/tagger/captionPresets.ts` 使用通用 `/api/user-data/presets`，`train_type=tagger-caption`，`config`只包含prompt/language；还在load时自动导入浏览器 `nt.tagger.captionTemplates`。用户预设和任务档案已有公开通用接口。

我们分支 `/api/llm/prompt-presets` 有完整template/system_prompt/language/output_format/max_length/model_capabilities及内容revision、草稿确认、事务与并发冲突保护、显式旧预设导入。不能保持两套独立可编辑列表，否则默认预设、修订和重试会分叉。

推荐适配方案：以dev `user_data/presets` 为单一物理存储和通用管理入口，保留自然语言预设的完整领域schema与冻结revision；旧 `/api/llm/prompt-presets` 可成为兼容适配层，不能再独立持久写另一套文件。自然语言子集的事务/并发保护须保留，不能直接降级为无revision的通用PATCH。迁移需备份/预览/显式确认、ID冲突处理与可重入，两个旧来源导入全部成功才标记完成。训练预设继续按train_type隔离。

任务层沿用dev的user_data档案与TaskManager统一投影，并保留Caption执行快照、SQLite报告/回滚记录。任务页隐藏、清除历史、删除档案不能互相误当成删标注；不能生成两条相同任务或两个执行器。

## 3. 模拟合并结果与推荐路径

执行 `git merge-tree --write-tree HEAD origin/dev`，没有更改任一工作目录、分支或索引。冲突15处，见 `merge-tree-summary.json`：

- .gitignore、README.md、README-zh.md。
- frontend/src/api/client.ts、frontend/src/api/tagger.ts。
- frontend/src/components/dataset/TagTranslationSettingsDialog.vue。
- frontend/src/dataset/caption.ts。
- frontend/src/i18n/messages/en-US.ts、zh-CN.ts。
- frontend/src/pages/DatasetEditorPage.vue、TaggerPage.vue。
- frontend/src/styles/dataset.css、settings.css、tagger.css。
- mikazuki/app/proxy.py。

无文本冲突不等于行为安全：新增ApiSettingsPage、通用预设/任务模块、自动旧预设导入和local_only路由均可能自动合入但仍不符合本功能契约。`api/client.ts` 必须同时保留dev新增httpStatus与我们detail错误解析；下载源必须保留dev全局设置并经过既有后端白名单。proxy冲突按各端已发布行为核对，适配不能扩大到Agent改造。

推荐从已推送feat分支建立独立适配分支/工作目录，merge固定dev后逐项人工解决，保留已发布历史和变更归属。新版dev布局为前端实现基础，现有natural能力为领域与安全基础。此次只分析，尚未创建适配分支或执行merge。

| 阶段 | 输出与验收点 | 优先级 |
|---|---|---|
| A 适配基线 | 固定双方SHA、隔离合并、完整记录冲突；原开发/手测保持 | P1 |
| B 共享配置与预设 | `/settings/api`接共享LLM；text/vision、运行时Key、远程优先、唯一预设存储；迁移幂等与revision | P0 |
| C 新打标UI | 新版方法/来源/模型行实际可用；仅Tag/natural；预设总控语言/格式；试标与批量同配置；取消、重试、历史 | P1 |
| D 新编辑UI | 自动按格式选raw；自然语言整句翻译/中文零调用；禁用Tag变更；hash冲突、草稿恢复、外部写入再载入 | P0 |
| E 本地共用模型 | 一个安装入口/资产ID/运行时；安装与健康检查成功才ready；text/vision复用、取消与失败清理 | P1 |
| F 完整验收 | 新旧用例合并，全量前端check和相关后端矩阵、真实API/本地生成、桌面/390px、新用户/已有用户/从零安装 | P1 |

## 4. Qwen小体量双用途模型

本轮通过官方Hugging Face API、固定revision模型卡/config、GGUF元数据和llama.cpp源码读取资料，仅保存文本与资产清单，没有下载模型或运行新候选。

| 候选 | 主模型与视觉组件 | 合计下载，十进制GB | 当前依据 | 建议 |
|---|---|---:|---|---|
| Qwen3-VL-2B-Instruct | 官方Q4_K_M 1,107,409,952 B + Q8_0 mmproj 445,053,216 B | 1.552 GB / 1.446 GiB | 项目既有三图英文、strict JSON、整句中文翻译成功；实测峰值RSS约3.07GB | 现有可交付基线及对照 |
| Qwen3.5-2B | Unsloth Q4_K_M 1,280,835,840 B + F16 mmproj 668,227,264 B | 1.949 GB / 1.815 GiB | 官方统一视觉/文本模型；有固定版本GGUF配套；本项目尚未实测 | 新默认模型的首选探测候选 |
| Qwen3.5-0.8B | Unsloth Q4_K_M 532,517,120 B + F16 mmproj 204,987,232 B | 0.738 GB / 0.687 GiB | 下载最小；官方质量指标明显弱于2B；本项目尚未视觉实测 | 可作为低内存候选，暂不作质量默认 |

上述不包含llama.cpp运行时，下载体积不等于常驻/峰值内存。Qwen3.5两项来自社区量化，原模型为官方Apache-2.0；配套文件来自同一仓库固定revision，后续仍需验证GGUF元信息与实际匹配。没有确认到可直接使用的 `Qwen/Qwen3.5-*-GGUF` 官方公开仓库，API返回401，不能把社区包标成Qwen官方发布。

### 4.1 为什么优先2B而不是直接选最小0.8B

Qwen3.5-2B官方config包含 `Qwen3_5ForConditionalGeneration` 与vision_config，确为图文模型。官方模型卡有翻译指标WMT24++：2B=45.8、0.8B=27.2；该表是Thinking口径、55语言汇总，不能当本项目英译中非思考量化结果。

视觉同表MMMU：Qwen3-VL-2B=61.4、Qwen3.5-2B=64.2/64.2、0.8B=49/47.4；OCRBench分别79.2、84.5/85.4、74.5/79.1；HallusionBench分别54.9、58.0/51.3、53.1/46.7。Qwen3.5双数字是Thinking/Non-thinking；有的指标更好，有的没有优势，不宣称全面超过VL-2B。

因此产品候选先考察Qwen3.5-2B是否能提高整句翻译同时维持客观视觉描述。Qwen3-VL-2B已有真机证据且下载更小，保留为基线；未通过公平A/B前不替换。0.8B适合“极小”目标，但不能仅凭体积认定“翻译和打标都还行”。官方还提示0.8B思考模式更容易循环，Caption应禁用思考、限制长度并实际验证取消；`/nothink`不是Qwen3.5官方软切换方式，应使用runtime/chat模板参数。

### 4.2 已有0.8B不能直接声明视觉就绪

项目旧 `ggml-org/Qwen3.5-0.8B-GGUF` 安装资产为Q4_0主模型，没有mmproj。官方原模型有视觉，不等于当前安装包具备视觉输入链路。不要解除当前 `asset_id=qwen3.5-0.8b-local` 的text-only校验来假装完成；新视觉资产应有独立、版本化完整manifest，迁移确认后再设为默认，旧安装/配置仍可辨识。

### 4.3 运行时与一键安装要求

现有运行时固定llama.cpp b11327；读取该tag的 `src/models/qwen35.cpp` 可以确认文本架构支持，同时有Qwen3VL视觉投影路径。这只是源码支持依据，尚未证明所选Qwen3.5 mmproj在现有二进制上的startup/data URL/JSON兼容，不应无理由直接升级运行时或宣称可用。

一键入口放全局API/LLM设置，打标与编辑只链接/读取同一状态。动作应覆盖下载匹配模型与mmproj/运行时 → SHA/大小校验 → 启动 →健康和text/vision就绪验证→注册共享Profile。一个进程、一个模型目录、两种能力；不同请求串行或有界排队，避免翻译/打标分别启动服务并占用双份内存。

“一键安装即用”是用户点一次后的完整流程，不要求应用启动自动推理。保留remote-first和显式local-fallback；无需Key也能启动UI，安装不自动发送私有图片。安装取消/网络截断/坏hash/启动失败不能ready，重试幂等；手动配置的其它Profile与旧模型不自动删除。停服要更新可用状态，取消生成不能写部分结果。

另一个待修正点：当前 `/llm/local-vision/manifest` 语言仍只有zh-CN，而local_vision运行状态/Profile已支持zh-CN和en。模型目录、manifest、UI和试标可用性应从同一资产声明派生，避免英文预设错误禁用。

### 4.4 后续最小真实选型矩阵（尚未执行）

1. 候选Qwen3.5-2B与对照VL-2B，同机器/CPU线程/图片预处理/上下文/非思考策略，6张不敏感图，英文详细/简短及中文预设验证；包含照片、商品、插画、构图和带少量可见文字场景。
2. 12条英译中：训练描述、Tag短语、逗号/换行、数值/颜色/方位/否定、图中文字；另测中文输入零模型调用。人工评估事实、中文准确度、训练实用性，不仅看JSON通过。
3. 两种请求完整通过既有结构/实际语言/长度校验；不能悄悄放宽解析以帮新模型过关。记录启动、首个生成、每图耗时、峰值RSS、CPU和取消到稳定状态；给8GB/16GB个人电脑建议，数据缺失时不承诺性能。
4. 一个干净安装与一个已有0.8B/VL-2B配置升级场景；断网/截断/坏hash/取消/重启/并发文本与视觉请求/远程优先与兜底验证。
5. 结果达到当前已锁定的验收门后再决定默认；模型更换必须重跑缓存身份、任务快照、严格JSON、翻译与自然语言编辑回归。

## 5. 验证边界和下一步

本轮完成推送、最新dev固定副本、只读代码对比、模拟合并、模型与运行时资料核实。尚未运行dev应用/测试、实施适配、下载新模型或进行新候选质量评价。既有模型实测结果引用当前仓库证据，属于历史版本的真实验证，不冒充本轮新测试。

唯一推荐下一步：基于双方固定SHA形成适配增量任务书，并先冻结共享配置/预设迁移与编辑安全契约；随后在隔离适配目录实施，并安排Qwen3.5-2B/VL-2B小样本A/B探测。

## 6. 可核对来源

- GitHub dev：https://github.com/wochenlong/lora-scripts-next/tree/d9535c356c58c78f0f6b406538f861bafb04bb38
- 已推送分支：https://github.com/wochenlong/lora-scripts-next/tree/feat/NL-Captioning
- dev模板存储设计：独立副本 docs/superpowers/specs/2026-10-09-tagger-caption-presets-design.md。
- 项目既有真实翻译/英文打标：功能副本 docs/evidence/natural-language-captioning/2026-10-09-natural-translation-results.json。
- 官方VL-2B模型卡：https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct/blob/89644892e4d85e24eaac8bacfd4f463576704203/README.md
- 官方VL-2B量化清单：https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/tree/52d6c8ffea26cc873ac5ad116f8631268d7eb503
- 官方Qwen3.5-2B模型卡：https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/README.md
- 官方0.8B模型卡：https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/2fc06364715b967f1860aea9cf38778875588b17/README.md
- 社区2B量化：https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/tree/f6d5376be1edb4d416d56da11e5397a961aca8ae
- 社区0.8B量化：https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/tree/6ab461498e2023f6e3c1baea90a8f0fe38ab64d0
- 固定runtime架构源码：https://github.com/ggml-org/llama.cpp/blob/b11327/src/models/qwen35.cpp
- 多模态双文件协议：https://github.com/ggml-org/llama.cpp/blob/b11327/tools/mtmd/README.md

此目录保留原始README/config、资产size/SHA/revision与merge-tree结果，可复查，未保存用户配置或真实Key。
