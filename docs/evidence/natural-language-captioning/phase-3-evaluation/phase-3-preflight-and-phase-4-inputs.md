# Phase3 开工资源与Phase4输入

源码基线2cdb77f，Phase2已核销。评测集frozen-eval-manifest.json和rubric v1已冻结，评分pending；不能以P1代替当前adapter验收。

- Remote：用户已授权SiliconFlow /v1/chat/completions、Qwen/Qwen3.6-27B。Key仅后端进程瞬时注入，重启须重新注入；每一验收批最多8次模型请求，每次≤90秒、max tokens≤512，总执行≤15分钟，失败停止计量并留报告，不无限付费重试。
- Local：锁定Qwen3-VL-2B Q4_K_M+Q8 mmproj和llama.cpp b11327，具体revision/SHA见local_vision.py manifest；CPU-only/4线程/单请求，预估峰值3.1GB、上限6GB，总批≤15分钟，每图≤90秒。远程优先，显式fallback才准使用local。
- Phase3输出：新的sandbox nl-caption-eval-20261007下面分批独立state/models/output/report；中间可复用P1资产且必须说明，不称Phase4。只公开冻结样本，不处理用户图片。报告保留hash/修订/数量/资源摘要；不要保存完整provider envelope或Key。
- 清理：停止自己启动的进程、取消下载；保留脱敏可审计结果，模型/图片/cache/DB都不进Git。最终清理先校验绝对目标在指定sandbox内，使用单一PowerShell LiteralPath操作；不要跨shell拼删除。
- 回滚与失败：已有failure-report-template；job备份已存在，但安全回滚/清理接口与验证待本阶段完成。不能在外部hash变化时覆盖用户修改。

## Phase4固定输入清单（当前仅准备，不代表通过）

1. 全部必要源码已提交的准确commit；新worktree完整清洁状态。不得带未提交源码或当前测试输出。
2. Python3.11.15新venv、项目requirements以及完整训练测试所需依赖清单/锁；缺依赖与Windows symlink适用验收问题必须先闭环。
3. Node22.17.1、新node_modules、npm ci和check，从源码产出dist；不能复用当前依赖目录/产物。
4. 全新LLM/dictionary/HF/model/runtime/config/SQLite/queue/log/output根；空配置、无Key、词库/模型缺失正式启动及health。禁止旧模型或配置hardlink/copy。
5. 模型二文件和runtime从登记public URL重新获取、验证SHA/revision；Tag ONNX/CSV所需资产也新下载。资源充足后才开始。
6. 三个冻结样本从URL重新下载并校验SHA；API Key仅运行时注入。
7. actual Tag/natural/combined、remote-first/fallback、preview/cancel/retry/conflict/atomic、mixed editor安全、rollback/clear、完整矩阵/EDD/桌面窄屏键盘人工验收与扫描。
8. 失败回到对应阶段修复，提交后新建另一个fresh隔离root；不能沿用失败环境称从零验收成功。

下一步：完成安全job回滚/清理，然后当前adapter真实验收与完整回归失败闭环。GATE09/10仍未通过。
