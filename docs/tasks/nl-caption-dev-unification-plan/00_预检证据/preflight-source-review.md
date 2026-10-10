# 预检事实、来源与实施风险

2026-10-10 规划快照。本文没有新增真实模型试验结果。开工必须重验会漂移的状态。

| 项目 | 已核实快照 / 来源 |
|---|---|
| 工作区规则 | `E:/OpenSourceTeamWork/workspace/README.md`：裸仓库、branches 与 sandboxes 分离，用户 resources 不清理 |
| 功能分支 | `feat/NL-Captioning`，HEAD `21571c5ef72a61a5cd10203596e2653e37b2a8c4`，上一轮已推送核验 |
| dev 分析快照 | `d9535c356c58c78f0f6b406538f861bafb04bb38`，`workspace/branches/dev-ui-analysis-20261010` |
| 共同祖先 | `fc193789c46f6724bfcc92e203644ba3f77db995`；feature 独有41、dev独有61个提交 |
| 未提交用户修改 | `tests/test_diffsynth_review.py`；规划前 SHA256 `8620DB361C56816FE938C2B41F81B462A41233D39205DBA5CEE0A0B39DD2ED3D` |
| 初步合并 | `git merge-tree` 发现15个冲突，仅模拟，未 merge |
| 既有验收 | 旧分支前端349、Caption133；旧VL-2B三图/翻译有效，仅作历史对照，不证明合并版本 |
| 资源快照 | i5-12600KF、约32GiB RAM、E盘约149.5GiB空闲；GPU能力本计划未核实，不作为依赖 |
| 工具链 | Python 3.11.15；Node 22.17.1；开工复核锁文件与 dev 的工具链要求 |

## 来源索引

- [归档分析](dev-ui-and-local-qwen-analysis.md)和[模拟合并摘要](merge-tree-summary.json)：从 `workspace/tools/nl-caption-dev-analysis-20261010/` 原样复制的只读证据。
- [既有设计](../../../design/natural-language-captioning-tagging-design.md)、[最新设计增量](../../../design/nl-caption-dev-unification-design.md)。
- [Issue #409](https://github.com/wochenlong/lora-scripts-next/issues/409)；相关 #365/#405；既有设计记录已读契约，不以第三方README作为用户授权。
- 模型官方卡、配套量化资产 revision/size/SHA、llama.cpp 源码在原研究目录保存；U1必须将最终候选完整资产清单复制入本轮证据，避免依赖未跟踪绝对路径。
- 现有真实对照：`docs/evidence/natural-language-captioning/2026-10-09-natural-translation-results.json`。

## 风险登记

| ID / 等级 | 风险与影响 | 处理 / 门 |
|---|---|---|
| R1 P1 | dev 可继续变化，15处冲突不代表完整风险 | U0重新fetch并冻结；逐文件语义审查；AC-U0 |
| R2 P0 | dev旧配置明文保存Key、双路由绕过远程优先 | 使用当前运行时注入方案；迁移与日志检查；AC-U2/U4 |
| R3 P0 | 新编辑器默认按Tag拆自然语言，破坏标注 | 格式来源+前后端守卫+expected hash；AC-U3/U4 |
| R4 P1 | 双预设/任务写入导致丢失、重复执行 | 单物理预设存储、单执行权威、幂等迁移；AC-U2 |
| R5 P1 | Qwen3.5量化/mmproj组合和双用途质量未知 | 用户指定合并后探测；U1硬门，未验证前不选定默认 |
| R6 P1 | 从零重建变成复用旧环境，安装不真实 | 新根、空缓存、重新下载校验、正式入口；AC-U5 |
| R7 P1 | 范围runner遗漏新user_data/settings用例 | collect清单/遗漏审计，不以旧133数量为门；AC-U4 |
| R8 P1 | 旧平台例外、旧人工评分被重复核销 | 每项当前commit验证；人工后续，真实API必测 |
| R9 P1 | 旧用户测试改动被合并覆盖 | 原字节备份/hash，隔离合并，仅显式路径提交；AC-U0/U6 |

R5 是已计划验证的技术假设；允许 U0 开工、阻挡 U2 默认模型实现定稿。R2/R3/R4 是必须保持的安全契约，不能作为延期交付的豁免。规划无未回答的产品决策；执行时真实API凭据是否可用仍须私下检查，不在文档保存 Key。
