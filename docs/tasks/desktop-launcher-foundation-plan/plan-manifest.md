# Plan Manifest

```yaml
plan_id: desktop-launcher-foundation-20261028
version: 1
last_updated: 2026-10-28
mode: normalize existing docs
scale: Full
canonical_progress_file: 00_总控目标索引.md
execution_readiness: complete
active_stage: none
stage_status:
  阶段0_正式模型与目录合同: complete
  阶段1_管理核心与资料隔离: complete
  阶段2_真实双版本与故障验收: complete
review: pass-with-boundary
project: E:/OpenSourceTeamWork/workspace/branches/dev
branch: dev
source_commit: 9ca2de963122f34599e34e5ff382199de9188811
evidence_root: E:/OpenSourceTeamWork/workspace/tools/launcher-foundation-20261028
inherited_evidence_root: E:/OpenSourceTeamWork/workspace/tools/launcher-prototype-20261028
budgets:
  additional_disk_gib: 8
  total_download_gib: 1
  gui_readiness_seconds_per_run: 180
next_action: 本轮完成，无待办实施动作；后续范围另立任务
```

状态只在总控维护；本文件的阶段字段是其同步索引。更新时间不是预检在代码施工前完成的证明。

## Required Artifacts

| 类别 | 必需文件 |
| --- | --- |
| 入口 | `README.md`、`plan-manifest.md`、`00_总控目标索引.md` |
| 预检与治理 | `00_预检证据/README.md`、`preflight-source-review.md`、`gate-validation-checklist.md`、`governance.md` |
| 目标 | `01_目标计划书/00_目标计划书索引.md`、`01_目标1_安装清单_实施验收计划.md`、`02_目标2_版本管理_实施验收计划.md`、`03_目标3_用户资料_实施验收计划.md` |
| 任务书 | `02_长程任务书/阶段0_正式模型与目录合同_目标1_长程任务书.md`、`阶段1_管理核心与资料隔离_目标2_长程任务书.md`、`阶段2_真实双版本与故障验收_目标3_长程任务书.md` |
| 开工清单 | `04_阶段开工清单/阶段0_正式模型与目录合同_执行前清单.md`、`阶段1_管理核心与资料隔离_执行前清单.md`、`阶段2_真实双版本与故障验收_执行前清单.md` |
| goal | `03_goal提示词/桌面启动器正式化底座全程执行_goal提示词.md` |
| 可行性 | `05_最小可行性验证/minimal-feasibility-probe-plan.md`、`feasibility-probe-report.md` |
| 复盘 | `06_开工前最终复盘报告.md` |

Full 产物全部保留。测试、失败、完成、清理、风险授权、变更控制与可行性报告模板合并在 `governance.md` 的独立章节，避免七份重复规则；无门禁被删除。

## Goal To Stage Mapping

| 目标 | 阶段0 | 阶段1 | 阶段2 |
| --- | --- | --- | --- |
| G1 安装清单 manifest | 冻结字段与真实身份 | 解析、校验、receipt/登记 | 真实归档与异常清单拒绝 |
| G2 版本管理 versions | 冻结状态转换 | 安装/选择/回退/修复/删除保护 | 双 commit 启动与回退实测 |
| G3 用户资料 profiles | 冻结共享/隔离边界 | Python 根目录、兼容工作视图 | API 写入、联接、损坏恢复后保留 |

## Sources / Evidence / Gates

- 设计依据：`../../design/desktop-launcher-installation-model.md`。
- 继承报告：`../desktop-launcher-prototype.md`；原型 P1–P7 不解锁正式双版本完成门。
- 实施接口：`../../../desktop-launcher/catalog/releases.json`、`../../../mikazuki/paths.py`、`../../user-data.md`。
- 已生成的根目录基线/构建/安装/Python日志直接索引；阶段1完成报告、14处junction及最终制品映射在`stage1/`。运行证据实际目录为`ui-test/artifacts/formal-cycle/`、`recovery/`、`python-remove/`及`fault-test-20261028-220235-e383a2/`，关窗报告在根目录，`stage2/stage-completion.md`索引完成材料。最终构建为`cargo-*-final.log`，新EXE必须复验，不虚构旧证据属于新EXE。
- GATE-00–14见 [gate清单](00_预检证据/gate-validation-checklist.md)。G1/G2/G3与三阶段均complete，运行/清理/预算/交付校验报告齐备，残余P0/P1为none。包身份固定引用evidence_root下`delivery/manifest.json`和`delivery-hashes.json`，ZIP为`NextTrainerLauncher-0.2.0-win-x64.zip`，不嵌入字面SHA。完成计划冻结后由主执行者重打含完成状态的源码overlay并再次校验，只更新独立包清单。
