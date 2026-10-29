# M1-CANDIDATE：GUI 候选包与实测报告

本报告按 v0.4 / CR-003 维护。当前为施工记录，尚未交付可用候选。M1 保持 `in progress`；候选不等于 EXIT-M1、干净 Windows 分发验收或训练引擎验收。唯一进度仍是 [总控目标索引](00_总控目标索引.md)。

## K1：集中关闭环境差异

正式安装使用固定 uv 0.11.16、CPython 3.10.19（build 20260211）及受管 minor alias。旧控制夹具直接使用原始 Python 路径，造成与正式安装生成方式不一致。原登记首案在 `.lock` 安全拒绝；第二案在 CLI 预览因 `pyvenv.cfg` 拒绝，均未进入确认或解释器验证。两案原失败与隐藏原件保持，不计入 CR-003 在 K1 完整关闭后的候选轮次。

| 差异 | 旧证据与当前事实 | 所需严格规则及来源 | 状态 |
| --- | --- | --- | --- |
| 环境根 `.lock` | 独立固定 uv 首次离线安装合成 wheel 后生成 0B 普通文件 | 只接受精确环境根路径的可选空文件，完整闭包计入摘要；拒绝非空、目录、链接与其他隐藏文件 | 已实现并验证 |
| `pyvenv.cfg` 的 home | 正式安装使用经过验证的受管 minor alias；旧模板固定 patch 目录 | 独立受管 uv 的 alias/patch 两种输入命令均输出同一 minor alias；精确五键及顺序与已验证同根 alias 绑定。旧 patch-home 仍须原 v2 复制 EXE，不能混配动态 shim | 最小代码已接入，独审通过 |
| `Scripts/python.exe`、`pythonw.exe` | 正式环境两者均为 45,568 B；旧控制夹具分别是 260,608/248,832 B | 独立复现证明为携带绝对 base 路径的 3 资源 PE wrapper，按固定模板逐字节重建；模板绑定原 uv/Python/recipe，不能固定现场 SHA | 最小代码已接入，独审通过 |
| 其他控制与入口、完整闭包 | 旧环境静态诊断 40/43 一致，27 个入口全部逐字节重建一致；13,106 文件中仅 `.lock` 未列规则，12,738 个原文件摘要通过 | 独立控制完整核对：16/16、27/27、12,738/12,738、81/81，13,106 文件/800,957,063 B，无未知/缺失，固定 base 前后不变 | 来源核对与定向独审通过 |

外部证据统一位于 `E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/`，本报告只引用最终回执，保留原始失败，不再另建同义报告。

K1 摘要入口 `recipe/gui-registration-working/k1-final-control-comparison.json`，SHA256 `c481c27478c2cc0683dcb1e87930b25da147f16b200f939554c35116af5a0cb3`；完整闭包来源证据 `k1-managed-alias-evidence.json` SHA256 `944b6701db3ee2d49be87ebddbdcbf02e688e262d29c0d57ad3764e56c2d4104`。定向独审确认模板仅授权已独立观察的 minor alias 输出，未发现阻断项。

## K2：候选身份与检查

K1 完整关闭后最多两轮新候选。当前计数 `1/2`，第一轮 EXE 已冻结，待 K3 实测。固定训练器源码提交为 `196ff12c16083d59c8be6711476c6fdb70c7112a`；配方为 `gui-cp310-win-x64-v1`。构建产物为仓库 `desktop-launcher/src-tauri/target/release/next-trainer-launcher.exe`，23,152,640 B，SHA256 `ac862fe56a8f4cb73de6f513e826e68f8dd48cb963dfd32fbc21d1c83d671d6b`。独立冻结副本、构建提交和完整摘要将写入本轮 `operations/candidate-round1-20261029/freeze.json`。

本包检查：Rust 184 passed / 0 failed / 3 ignored，fmt、严格 all-targets Clippy、前端类型检查与构建、locked/offline release 均通过。3 个 ignored 沿用原声明：两项仅由父测试调用的子进程入口，以及显式大于 1 GiB 文件验收；不计为新增能力通过。固定训练器前端 ZIP 为 2,440,912 B，SHA256 `3c97a03bc4554248936ee4cbba6bb3f12bc413aecbbac9633400986da6801da1`。计划静态验证通过（44 产物、321 本地链接），仅证明文档结构。

## K3：同一冻结 EXE 的结果

| ID | 场景 | 当前结果 | 证据 |
| --- | --- | --- | --- |
| C1 | 中文空格新独立根，真实安装基础 Python、工具、源码及固定 GUI 环境 | not-run | 可预置已核原资产缓存；禁止成品环境 |
| C2 | 原生启动，版本 API、首页及当前静态资源，停止与正常退出 | not-run | 必须与 C1 同包 |
| C3 | 精确单包损坏、原生预览确认、精准修复及再次启动 | not-run | 完整非目标及资料原字节保护 |
| C4 | 无缓存、登记缺失，独立完整验证与登记恢复 | not-run | 原记录/cache 精确保留，恢复不继承丢失历史健康 |
| C5 | 包身份、中文步骤、WIP 推送及远端完整 SHA | pending | 等 C1–C4 结果后汇总 |

## 能力边界与操作说明

本候选只针对 Windows x64 GUI 安装、启动、固定依赖的精准修复及登记恢复。当前机器已有 WebView2；新独立根验证不等于干净 OS。源码修复、基础 Python 修复、中断恢复及下载预算的旧包证据单独保留，不冒充本包实测。四训练引擎、可信远端更新、资料迁移、独立壳升级与正式分发均未在此候选验收。

候选冻结后补入可执行操作步骤和路径；不会把尚未运行的命令写成已通过。显式重建/同发布回退/旧 pending 扩展保持草稿，`deferred by CR-003`。

## K4：审核停止点

同包 C1–C5 全部通过才报告“M1-CANDIDATE 已交付”；任一失败则报告“候选未通过”及具体阻塞。两种结果均连同 [剩余工作与成本审核表](remaining-work-cost-review.md) 提交用户审核并暂停扩展；M1 不退出、M2 不启动。
