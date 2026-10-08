# Phase5 从零重建执行记录（进行中）

候选源码：`25ef85b363bddfe39458b92a7659397d2d0c0669`。Phase4 前置批准见 `../phase-4-real-evaluation/2026-10-08-user-gate-approval.json`；新火箭评分20/20，四项Windows symlink权限失败采用Linux原始case补验的组合口径获批准，原平台限制保留。

## 首次重建失败记录

隔离根标识：`nl-caption-phase5-409-20261008-r1`。fresh detached worktree、新下载Python3.11.15、新venv、重新下载requirements和Node22依赖、重新下载三样本与视觉模型。没有复用P1/旧sandbox模型或数据库。

前端typecheck/lint通过（两个既有warning）；Vitest默认并行：341通过、1项DatasetPage刷新/草稿恢复超过原5000ms时限。原文件以`--maxWorkers=2`单独诊断4/4通过，仍不核销首次失败。后端首次508通过、4项已批准Windows权限失败、3项TaskInsights因为测试辅助SummaryWriter缺torch而skip。没有把skip记为通过。

首次根标记不接受，停止其资产下载，不在该根补齐后宣告完成。下一次必须全新源码、Python/venv、Node依赖和公开URL资产重下；既有失败输出保留用于追溯，不能复用。

## 第二次重建环境准备

新根标识：`nl-caption-phase5-409-20261008-r2`，同一候选commit，尚未发生业务源码修改。重新执行全部安装/下载。前端只限制测试workers为2，保持原断言和5000ms时限，完整执行typecheck、lint、52文件Vitest和build。后端额外重新下载CPU torch2.7.0用于三项TaskInsights真实SummaryWriter验证，GUI requirements仍按项目原文件安装；测试runner使用pytest9.1.1。

本次远程Profile未配置，也无运行时Key输入。远程真实路径按锁定计划属于可选配置路径，准确记录未执行，不能宣称当前fresh远程通过。

当前仍进行环境准备/下载与测试。必须补充正式lifespan Zero-Short、fresh ONNX/Qwen三图、严格JSON/data URL/缓存/资源、真实HTTP取消/仅失败重试/冲突/Editor/rollback/clear、浏览器检查、完整矩阵、隐私和进程清理证据。未满足最终完成门。

## 第二次重建结果与验收脚本修正

前端342/52、typecheck/lint/build通过；后端511通过、四项已批准Windows权限失败、0skip/17subtests。公开URL所有资产重新下载并校验通过。正式lifespan五项API200、空Profile/缺视觉资产、390px无横向溢出、安装入口和禁用生成通过。真实ONNX新旧/HTTP预览三图逐字节相同13/11/8 Tag；真实Qwen三图3/3、严格JSON、四次JPEG data URL、缓存3命中零请求、默认跳过3、启动10.675s/批量25.878s/峰值3,068,403,712B、模型停止通过。

HTTP脚本初次漏先调用本地runtime启动；正确返回502/llm_capability_vision_required，验收脚本断言失败。保留该失败，不在r2宣告从零通过。诊断脚本补显式启动后全部22项通过：真实preview/三图写回/跳过、natural单字/undo/redo/外部hash冲突、真正取消0写回、坏图部分失败修复后仅重试1项/parent、推理中外部写入冲突、rollback/clear、user_data预设revision和停止/原子无残留。此结果仅诊断证据。固化工具verify_caption_rebuild_http.py，下一步新r3根完整重建和重跑，严禁复用r1/r2依赖与资产。业务源码未变。

## 第三次重建下载失败与第四次准备

候选8134295的r3根在首个公开样本下载后校验失败：chelsea应240512字节，收到48210字节，尾部无PNG IEND，证明网络传输截断；SHA不匹配，未发布文件、未进入真实验收。r3根不接受。下载器新增至多3次从头下载，每次清除part，不复用部分内容；始终固定SHA/size，三次不匹配仍失败并要求新根。可控截断首失败次成功/持久坏SHA拒绝已通过。业务代码未改，第四次将从最新工具提交和全新公开下载开始。
