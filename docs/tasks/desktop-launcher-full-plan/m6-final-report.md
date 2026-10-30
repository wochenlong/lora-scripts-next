# 桌面启动器 #516 最终交付报告

> **2026-10-30 交付后补丁 CR-007：** 默认下载已取消额度设置前置，新安装器/便携包及新 EXE 原生专项已通过，见[补丁交付记录](download-policy-followup.md)。下文第 4 候选及 M6 结果保留其原身份与范围；新包只补测受本次改动影响的链路。

> 2026-10-30 最终归档。整体状态：complete-with-boundary（施工完成，约定的可执行沙盒验证完成，系统与生产边界单列）。最终保存提交及远端完整 SHA 以本 run 的 M6/git-baseline/final.json 为准。

**交付结论：M0–M5 施工完成；已执行的 M6 验收为 `pass-with-boundary`（在明确边界内通过）。** 第 4 个 Windows x64 开发候选已完成空根缓存安装、真实服务启停、资料导入/组合回退、GUI 精准修复/补登记、可信清单、四引擎微型夹具、独立 helper 三案，以及非管理员当前用户安装/卸载。GPU/真实引擎训练、干净系统与未展开的故障矩阵仍按下述边界记录；生产签名/许可条件尚不满足公开发布。资源磁盘与精确清理已留证，最终代码与报告的普通 push/远端核验见保存回执。

工作分支为 `feat/desktop-launcher`，仓库工作副本为 `E:/OpenSourceTeamWork/workspace/branches/dev`。阶段保存回执如下；各阶段原始回执保留，最终远端核对结果另记在 `M6/git-baseline/final.json`。

| 阶段 | 已保存提交完整 SHA | 保存证据 |
| --- | --- | --- |
| M0 审核与基线 | `e294e53ffbd0ff4e08abcb40a9d5d42beacb092f` | `M0/baseline-final.json`；代码提交另为 `bf8cd7056ed28a1e68fa9c09de972bd69d2b4433` |
| M1 可靠安装与精准修复 | `776cf4f2a03fe2766db1647d1ddf4cb7de6062c9` | `M1/construction-v06/baseline-final.json` |
| M2 首批引擎与共享控制 | `dd9925fe9e94997b8e549601e54f1ec2af7bb180` | `M2/construction-v06/baseline-final.json` |
| M3 四引擎与可信清单 | `0d095dc8cb185b4c9e4d6f4971eba26ea3a1b47e` | `M3/construction-v06/baseline-final.json` |
| M4 独立资料与完整组合 | `b27423d7ab9c53112be55be6d064cd3b0f9a36ab` | `M4/construction-v06/baseline-final.json` |
| M5 独立 helper 与分发 | `500751e349ea0176f4b2631510a1cb8762fef759` | `M5/construction-v06/baseline-final.json` |
| M6 最终验证与收尾 | 由同次收尾提交保存 | `M6/git-baseline/final.json` 记录普通 push 结果和远端完整 SHA，避免提交自引用 |

所有相对证据路径基于 `E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/`。

## 最终候选包

冻结候选目录：

`F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/M5/windows-candidate-20261030-4/`

| 文件 | 大小（字节） | SHA256 |
| --- | ---: | --- |
| `NextTrainerLauncher-0.2.0-windows-x64-portable.zip` | 17,567,887 | `e8e0dacb54eb3be92a151499c33aa1e6e9c3a06fc03c576de2db94f6cc1b24e8` |
| `installers/Next Trainer Launcher_0.2.0_x64-setup.exe` | 14,227,866 | `f7add27d2b5d6ba115edbd404f6f8cb13755ae7623897b5d6719ea0a6e974338` |
| `NextTrainerLauncher-0.2.0-windows-x64/next-trainer-launcher.exe` | 35,830,784 | `896051564cc3722d45c4ac927c5a2c8823916961ff19a34e594b29a4cf94abba` |
| `NextTrainerLauncher-0.2.0-windows-x64/next-trainer-updater.exe` | 1,016,320 | `d71390cea30cc16e8d17f749aea16241431119bcc5bbf42a5b0c9f5adfa16054` |

以上为第 4 个候选包，冻结回执为 [frozen-package-20261030-2.json](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/frozen-package-20261030-2.json>)，其中 delivery manifest SHA256 为 `ad0bdba32dd28c278b443bff82722033b98262b8e3ccdd85f4311826696f4e29`。旧 `frozen-package-20261030-1.json` 属于第 3 个候选包，不能混用。

训练器源码为已推送功能提交 `0d095dc8cb185b4c9e4d6f4971eba26ea3a1b47e`，壳构建提交为 `02cd5c4632e91eb719d13a827f7c224aee0a5181`；M5 后续文档基线与实际构建提交分别记录。catalog 摘要为 `659d0237a7e41aa950b7db04e3a1101187fbd3cf236dfceeb8441e62a88a1bb1`，recipe 摘要为 `612124245bff0c62ab9d2e15aa95f86ff9b9359874f3e28e3fa99ad93007f67a`。安装器配置为当前用户安装，WebView2 配置为微软在线引导安装。

## M6 同包结果矩阵

以下结果属于第 4 个候选包，同 EXE `89605156…cf94abba` 与 helper。主流程从全新受管根 `F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/M6/新 空` 开始，复用 84 项经正式 SHA256 核验的缓存，**属于空根安装，未声称冷下载或干净操作系统**。按照 CR-006 简化矩阵并复用核心施工检查；未单独执行的专项不作 M6 通过结论。

| 验证范围 | 当前结果 | 证据与通过边界 |
| --- | --- | --- |
| 空根安装、900×600 三页、实际 API/HTML/JS/CSS、健康启停 | **通过** | [主流程第 8 次回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/native-final-20261030-8/receipt.json>) 为 `passed:true / main_complete`；[UI 报告](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/native-final-20261030-8/ui-report.json>) 核实际安装、语义健康、版本 API 和冻结前端资源一致，停止后监听释放。可信缓存复用，本次网络计量 0。 |
| 资料预览/导入、凭据排除、外部引用、完整组合绑定/回退 | **通过** | [续验第 8 次资料报告](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-8/data-and-recovery/report.json>) 的已完成子链证明正式 import/binding/rollback 成功，imported/default 各自健康启动、读取独立 settings 并停止。导入不自动激活；回退保留 profile 和源原字节。该次整轮超时的 false 仍保留；[第 11 次资料报告](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-11/data-and-recovery/report.json>) 再核源七个文件、profile 原摘要与默认组合。 |
| GUI toml 单包精准修复 | **通过** | [第 9 次 UI 检查](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-9/ui-report.json>) 证明目标原字节恢复，同实例 `g38b73c0b08089e50` 的 generation 1→2、绑定代次一致且 clean；第 11 次真实健康启动和停止完成修复后闭环。 |
| 缺失登记补建及正式幂等恢复 | **通过** | [第 9 次正式补登记操作](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-9/data-and-recovery/operation-registration-restore.json>) 为 succeeded；[第 11 次资料报告](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-11/data-and-recovery/report.json>) 核完整发布身份、合法登记时间、正式 recover 成功、新收据原字节/实例代次保持且零新增网络，再完成真实 health/settings/绑定健康/停止。 |
| 可信清单与普通根拒绝 | **通过（固定开发测试签名）** | [第 11 次 UI 报告](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-11/ui-report.json>)：有效签名、篡改/重放拒绝与历史保持、旧 key 授权轮换、过期/错平台拒绝、撤销与离线历史重验；普通新根拒绝引擎测试夹具和未配置生产签名的壳更新，且根未创建。主安装会话仍 seq1。 |
| 四引擎入口/正式配方计划及同 EXE 微型夹具 | **通过（限定模拟夹具）** | 第 11 次检查四引擎入口与固定计划；[最终微型夹具第 5 次](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/four-engine-final-20261030-5/receipt.json>) 为同 EXE exit 0、12 项检查通过。四引擎分别 ready→damaged→只修 fixture_alpha→ready/gen2，fixture_beta 原字节保持；共享非目标写入拒绝并保留 dirty。uv 为固定小写入器模拟，控制/归档/hash/state/事务为实际执行；不作为真实引擎安装、导入或训练验收。 |
| 训练器运行中关窗与隔离回收 | **通过** | [第 11 次回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-11/receipt.json>)：最后一次真实健康启动后 WM_CLOSE 正常退出 0、Job 排空，端口 12772 已释放，外部 HTTP/PID/创建时间哨兵不变；计量器 request/socket 为 0、线程停止。 |
| helper 正常提交、trial 拒绝、文件占用后正式恢复 | **通过** | [shell 第 14 次回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/shell-final-20261030-14/receipt.json>)：normal committed、reject restored，均有真实 trial 窗口/rendered ACK及 verified/rejected；控制文件原字节、规范化路径快照一致，主壳正常退出 0、Job 排空。occupied 在锁定 CURRENT 时 recovery_required、无 trial；释放句柄后正式 recover restored，原控制/EXE 原字节与 helper/恢复壳退出均通过，哨兵保持。 |
| 当前用户 NSIS 安装、同 EXE 原生启动、卸载保留资料 | **通过（实际非管理员）** | [NSIS 最终回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/nsis-final-20261030-1/receipt.json>) 为 passed:true、elevated_token:false、non_admin_specialty:pass。当前用户安装仅登记 HKCU，安装文件逐项与冻结 portable 的字节/SHA 一致（只新增 uninstall.exe）；安装所得同 EXE 展示原生三页并完成一次正式只读 inspect；卸载退出 0、Job 排空，程序目录及相关 HKCU 登记移除，profile/合成源保护与外部哨兵保持。 |
| 资源与精确清理；最终 push | **资源/清理留证完成，push 待保存回执** | [资源来源](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/resource-source-index.json>)、[磁盘 current](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/disk-final.json>)、[清理回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/cleanup-final.json>)、[最终四制品身份](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/identity-final.json>) 已保存；最终阶段 SHA 由外部 baseline 回执补充。 |

第 11 次冻结终态为 `passed:true / remaining_complete`、465.69 秒、UI 32 项检查全通过、`errors:[]`；资料报告为 passed 且 `mutations:[]`。其 receipt SHA256 为 `9267ecf9efd53ca2050ce360b6df52e8eace32f2835d774870091fd64b6f3ebd`。微型夹具、helper 和 NSIS 不属于第 11 次回执范围，分别由上表三个独立最终回执证明。

## 缺陷修复与保留的失败

| 记录 | 分类与处理 | 保留证据 |
| --- | --- | --- |
| 旧包主流程 1–3 | 测试脚本 fixture 查询竞态、262>259 路径预检拒绝、下载 TLS 提前关闭；分别保留失败，第 1 次强制回收不能记正常退出。 | `native-final-20261030-{1,2,3}/receipt.json` 与 `ui-report.json` |
| 旧包主流程 4–6 | 同根下载/恢复尝试的原 false 与计量各自保留，不覆盖为后续通过，也不抵扣新包结果。 | `native-final-20261030-{4,5,6}/receipt.json` 与 `ui-report.json` |
| 旧包第 7 次导入 | **产品缺陷，已修复并重建第 4 个包**：目录检查漏列已扫描空目录所需的 `compat/<版本>` 祖先。仅补精确祖先，仍拒绝清单外目录，未改扫描/事务格式。定向回归 1 passed、格式检查通过；新包真实导入已通过。 | [旧导入失败](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/native-final-20261030-7/data-and-recovery/operation-import.json>)；第 8/11 次新包资料证据 |
| 续验第 8 次 | 资料/绑定/回退子链通过后控制器 600 秒超时；整轮 `passed:false` 保留，随后正常退出、Job 排空、哨兵保持。 | [回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-8/receipt.json>) |
| 续验第 9 次 | **测试脚本断言过强**：补登记成功，新旧收据仅 `installed_at:1793298935→1793300745`，完整 schema/release、实例/gen2 相同。合同允许对已丢失收据记录本次补建时间；不会读取测试脚本私有备份来找回旧时间。 | [原 false 回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-9/receipt.json>)、[原收据备份](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-9/data-and-recovery/release-receipt.original>) |
| 续验第 10 次 | 测试脚本把补登记后尚待真实健康启动的状态误作续验前置条件；未进入后半链，原 false 保留。第 11 次修正测试前置条件后通过，产品包未变。 | [回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-10/receipt.json>)、[失败检查](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/remaining-final-20261030-10/ui-report.json>) |
| shell 第 12 次 | **测试脚本等待上限不足**：点击检查后沿用 Playwright 默认 30 秒，完整根核验尚未完成即中断；未建立更新事务，原壳正常退出 0、Job 排空。只改测试脚本，产品包身份保持；第 14 次实际通过另列。 | [原 false 回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/shell-final-20261030-12/receipt.json>) |
| shell 第 13 次 | normal 已真实 committed/ACK/控制字节保持，但独立快照路径键混用 `/` 和 `\`，测试比较误报 false。仅规范化分隔符并拒绝重复路径键后，第 14 次三案通过，产品包不变。 | [原 false 回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/shell-final-20261030-13/receipt.json>) |
| 微型夹具第 1–4 次 | 1/2/4 保留原 Windows 路径/前缀调用失败；3 为测试脚本错误要求新根已存在 registry，未调用 CLI。第 5 次改用独立短根完成同包夹具，不回写这些 false。 | `four-engine-final-20261030-{1,2,3,4}/` 原始证据 |

旧包证据只用于解释对应旧包行为；未覆盖的后续功能不从失败时点的保护结果推定通过。完整 release 身份始终要求精确一致；同一补登记事务的 recover 已在第 11 次证明新收据原字节不再变化。

## 未覆盖范围与发布边界

- **真实引擎安装、真实损坏修复、GPU、完整模型、反向/训练与权重：`skip + CR-004`。** 用户明确没有合适 CUDA 机器并要求跳过；微型夹具与计划检查不能替代这些结果。
- **干净 Windows、真正缺 WebView2：`blocked/not-run`。** 本机已有 WebView2，新建根和限制 PATH 不证明干净操作系统；不重启失败 VM 准备链。
- **A2/A3 未跑完整原生矩阵。** 本轮完成选定安装、恢复、真实启停与运行中关窗；没有逐一覆盖下载/解压/依赖/提交各点取消或强退、Range 被忽略/源变化/代理错误、真实磁盘中途不足。CR-006 下复用对应核心施工检查，未执行的原生专项保持未验证。
- **显式新实例重建、同发布实例回退、旧 pending 事务恢复** 已有 M1 核心施工检查，本次未在最终包原生流程中分别重跑；不能把资料组合回退当作这些专项通过。
- **格式升级恢复为 `no_migration`。** 本候选不自动改变资料格式，壳更新案例只验证现有控制合同及恢复，不宣称未执行的格式迁移/故障恢复通过。
- **CLI 微型夹具需要短根的开发测试限制。** 原主根夹具深路径及第一个短根快照仍触发 Windows 路径限制，前缀 CLI 另有 os error 1；最终在本 run 所有的 `F:/NextTrainerLauncherSandbox/e` 独立短根完成。经同 EXE 原生 IPC 正式授权 seq1 后复制受管 Python（4,184 文件、61,989,621 字节），由最终 EXE 内置 manifest 全量核验；[设置回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/four-engine-short-setup-20261030-2/setup-receipt.json>) 记录授权壳正常退出/Job 排空。主安装根未改写产品状态。短根夹具通过不能消除这项开发测试长路径限制。


按 CR-006 复用的施工证据只支持其原包和检查范围：A2 的 [旧原生 22 项检查](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/native-20261029-012036Z/ui-report.json>) 与 [旧中断恢复 17 项](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/native-gui-recovery-20261029-0400Z/ui-report.json>)；A3 的 [130 passed / 2 ignored](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/verify-20261029-041831Z/tests.stdout.log>)、[下载预算 157 passed / 3 ignored](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/download-budget-20261029-0440Z/test-attempt3.log>) 及 [原生预算 UI 16 项](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/native-download-budget-20261029/ui-report.json>) / 同目录 CLI 6 项。显式 GUI 环境重建、同发布环境实例回退和旧 pending 复用 `M1/construction-v06/rebuild/` 的 8+1 项定向检查。它们没有变成最终包完整 A2/A3 原生矩阵或真实磁盘满实测，也不冒充 M6 真实服务链；本轮已通过的 profile 健康组合回退单独列在矩阵中。

这是 **0.2.0 开发候选**：`public_release:false`、`unsigned-development-candidate`，维护者生产密钥/渠道未配置，生产自更新默认拒绝。公开 RFC8032 测试密钥仅用于显式固定沙盒，SHA256 用于文件身份核对。

包内保留根 LICENSE（AGPL-3.0）、NOTICE、中文安装与恢复说明及 LICENSES 资料。许可清单共 534 个锁定依赖：184 个本机缓存缺失、149 个声明许可未知、192 个未取得包内完整原始许可；包含构建、可选与其他平台依赖，不能称为生产许可审结。

## 资源、清理与保存

[resource-source-index.json](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/resource-source-index.json>) 逐项记录来源字段、口径与重复关系。根 `resource-ledger.json` 只是旧 M0 索引，不能作为全程总量，也不能与其子账重复相加。

| 口径/来源 | 已记录字节 | 限制 |
| --- | ---: | --- |
| M0 HTTP 正文：`M0/resource-ledger.json / network.measured_body_total_bytes` | 8,270,582,469 | 已包含 P1 resume，不再加根索引或子回执。 |
| M2 本次正文：`M2/construction-v06/runtime-assets.json / charged_body_bytes_this_invocation` | 25,989,295 | 仅此 invocation，不是 M2/M3 所有获取流量。 |
| M5 训练器归档正文：`trainer-candidate-20261030/network-receipt.json / known_received_payload_bytes` | 57,257,800 | npm 离线下载 0；candidate-receipt 内为同一份记录。 |
| M5 工具已知正文：`prepare-nsis-20261030/prepared-tools.json / known_downloaded_body_bytes` | 2,430,073 | 已含 ZIP、DLL 和 source-downloads，不能再加各子回执。 |
| M1 CONNECT/TLS 代理 RX+TX：`M1/resource-ledger.json / completed_network_charge_bytes` | 1,013,413,437 | 已累计 completed_sources，包含失败/重试。 |
| M6 CONNECT/TLS：主流程 1–8、续验 8–11 独立终态 receipt | 483,605,683 | 每次只加 `network.charged_bytes` 一次；不再加 rx+tx 或 network.jsonl；四引擎/helper/NSIS使用本地固定材料，未独立作wire计量。 |

HTTP 正文与 CONNECT/TLS 分栏保留，**不把两者相加冒充同口径全程实测总量**。M2/M3 部分源码/解释器/解析元数据获取、API403、Git 及未测传输开销为 unknown，不能用资产文件大小推算网络。M5 第 4 包构建明确离线出站 0，不抵扣之前获取成本。

[最终磁盘回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/disk-final.json>) 是一次元数据扫描：本 run E 逻辑文件 2,947,271,207 字节（2.744860 GiB）、F 70,986,929,391 字节（66.111730 GiB）；另两处有归属标记的微型夹具短根合计 124,437,283 字节，来源见 [短根资源汇总](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/four-engine-final-resource-summary.json>)。当时磁盘余量 E 89,553,276,928 字节（83.402988 GiB）、F 998,492,672,000 字节（929.918766 GiB）。跳过 211 个受管 reparse 项而不跟随目标；这是 **current 逻辑字节，不是分配字节或历史峰值，peak 为 unknown**。

[清理回执](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/cleanup-final.json>) 记录：本 run 自建 HTTP 哨兵通过 stop.json 自退，精确原 PID 正常停止、7463 关闭；NSIS 程序目录已由本次卸载移除。未知外部进程未杀或写入，所有成功/失败根、缓存、原件及恢复材料保留，没有递归清除。四个交付制品及 manifest 已由 root 最后重核，见 [identity-final.json](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/identity-final.json>)，全部与上表一致。

阶段基线及最终代码由同次 M6 收尾普通 push 保存，远端核对回执在 `M6/git-baseline/final.json`。保留既有 32 项无关未跟踪文件，不自动合并或公共发布。

**归档结论：** M0–M5 施工及约定的可执行 M6 验证完成；逐项结果与保留边界见 [统一验收矩阵](</E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M6/acceptance-matrix.json>)。干净 Windows/缺 WebView2 为 blocked/not-run；真实四引擎/GPU/训练为 skip+CR-004。当前交付 0.2.0 开发候选，生产签名、渠道和完整许可审结仍待正式发布工作处理。
