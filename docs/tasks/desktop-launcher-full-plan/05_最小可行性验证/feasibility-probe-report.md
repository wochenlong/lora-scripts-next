# M0 最小可行性执行报告

> 当前修订0.2（2026-10-29）：用户已批准[CR-001资源受限GPU验收skip](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)，实际Goal已恢复active。仅豁免列明的Fast/DiffSynth GPU/完整模型训练子项，其他必测和干净Windows保留；旧0.1阻塞/无豁免文字是历史，不覆盖本修订。阶段完成必须明确授权skip边界，不能报GPU全通过。

## 0.2当前复盘

CR-001已由用户明确批准：资源受限的指定Fast/DiffSynth GPU/完整模型训练子项标skip并列原因，不能称pass；Kohya/Toolkit和DiffSynth普通小张量等可执行验证保留，M0独立P3前置分期到对应引擎配方。Goal已恢复active，当前继续P1干净Windows/未豁免安装预算；M1未解锁。下列0.1原始blocked/超时/无豁免结论是历史事实，不覆盖本修订。新执行证据位于本run的changes/CR-001和M0/resource-feasibility/P1-resume，首次失败不覆盖。

- Date：2026-10-29（Asia/Shanghai）；Plan：`desktop-launcher-full-20261028`，v0.1。
- Result：**blocked**；没有测试豁免，M1不解锁。用户执行授权已生效，实际Goal已blocked。
- Run：`desktop-launcher-full-20261028-155831Z-f6c00a`。
- 原始证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M0/`。
- 新沙盒根：`F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/`。
- 唯一进度：[总控](../00_总控目标索引.md)；合同：[探针计划](minimal-feasibility-probe-plan.md)。

## 1. 实际探针结论

| 探针 | 结果与事实 | 证据及边界 |
| --- | --- | --- |
| P1 干净Windows | blocked。Hyper-V/Sandbox/WHP禁用，hypervisor未运行；限定目录/应用/命令检查未发现可用Windows VM/介质 | `resource-feasibility/clean-windows-report.md/.json`及raw。官方ISO/QEMU仅取元信息，完整EULA、guest启动及缺Python/uv/训练器/缓存/WebView2均未验证；未改变host |
| P2 四引擎资产/资源 | blocked。主要模型revision、LFS SHA256、大小和许可已固定；Fast驱动、DiffSynth显存前置不满足，完整依赖锁/预算路径未关闭 | `resource-feasibility/asset-lock.json`、`resource-projection.json`、`license-map.json`、`engine-assets-report.md`。模型下载/安装/GPU/完整加载反向均not-run |
| P3 独立CUDA微探针 | blocked；CUDA not-run。新Python3.10.19归档22,569,949B校验成功，独立启动、新venv创建两命令退出0；Torch未下载完 | `probes/P3-cuda/`报告与raw。600秒硬截止，实际600.234秒；Torch partial 3,137,339,392 / 3,273,064,440B；未验完整SHA、未安装、GPU0秒；未重试/延长 |
| P4 路径/生命周期基线 | pass-with-boundary，12项；真实中文空格junction复现Fast拒受管extensions，run重建使`.python`标记失效，外部逃逸拒绝，稳定profile哨兵保留 | `probes/baseline-contract-report.md`、`probes/P4-layout/`。首次GBK日志编码失败及attempt1保留，新UTF8 attempt2通过；不是产品RuntimeLayout或真实Python重建验收 |
| P5 能力/只读/worker基线 | pass-with-boundary，7项；真实status代码在合成根复现Fast/Toolkit改pyvenv.cfg、DiffSynth补state；隔离标准库worker在GUI/Torch缺失夹具下读JSON且持久树不变 | `probes/P5-capabilities/`及基线报告。worker仅夹具；产品worker、严格只读、双入口锁及受管Kohya standalone完整门仍pending |
| P6/P7 | not-run，按既定分期归M1/M5前置门 | 不要求M0先实现全部未来功能，不倒填本轮通过 |

## 2. 固定配方资源缺口

Anima Fast固定上游 `sorryhyun/anima_lora@b43928b5e4b82b907bfca1a322383a33088d0bdd` 要求driver≥595、Python3.13 / Torch2.12 / cu132；当前RTX4060Ti架构CC8.9满足，但driver591.86不满足。CUDA13.2编译工具链尚未确认。官方Torch及FA匹配资产存在；有链接不等于已安装。未改驱动或以普通Anima/旧配方替代。

DiffSynth固定上游 `7686e54d41d25c0e8ed5f1318acc23b6bb832654`，本项目当前支持Qwen-Image-2.1 BF16。缓存代码整体将完整Qwen3VL文本编码器移到GPU。固定配置/结构给出的BF16参数保守下界 **17,202,995,200B（16.0215GiB）** 已超过本卡 **17,175,674,880B（16380MiB）**，尚未计其他模块、上下文及激活。没有实跑OOM；这是完整驻留路径的资源下界证明。训练offload未覆盖该缓存步骤，不能据此承诺24GiB可完整训练。

Kohya / AI Toolkit的官方SD15为候选，尚未加载/反向；Fast用真实Anima，DiffSynth用真实Qwen，不以tiny/random/其他引擎抵扣。Anima实际模型许可是CircleStone Non-Commercial v1.2；Qwen是2026-09-20 Research License。本地评估条件与产品再分发分开，模型不捆绑、不代用户接受额外条款；NVIDIA来源及最终SBOM/notice审计尚未闭合。

主要模型每条独立路径 **42,333,430,894B（39.426GiB）**。M6网络预测55.7–72.4GiB，高端超过60GiB分配；完整保留开发与M6两套资源的F峰值约253–379GiB，高端超过300GiB。串行释放的140–235GiB方案仅待验证调度候选，不降低累计网络、不借开发缓存、不降低最终验收。阶段网络可在总额内显式调剂，但必须先完成依赖锁/账本/总控更新，不得突破200GiB。

## 3. 真实基线验证与远端保存

执行前134文件备份共962,508B；102文件allowlist覆盖底座及本功能设计/计划，32无关未跟踪文件保留且哈希保持。来源、敏感/大物扫描及暂存范围独立复审记录在`allowlist-review.json`、`precommit-review.md/.json`。没有整目录暂存或reset/clean。

| 验证 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| Rust测试 | 15项pass | `baseline-checks/`命令JSON与stdout/stderr |
| Python相关回归 | 184 passed / 2 skipped / 4 warnings | 已有隔离兼容Python3.10，skip不抵扣真实验收 |
| 前端构建、Rust fmt、严格all-targets Clippy | pass | 同上，不代表原生窗口或安装验收 |
| offline release build | pass | 同上，不是最终冻结候选包 |
| 静态计划校验 | pass，42产物/41 Markdown/7阶段；链接数以最新JSON为准 | `plan-validation.json`及状态更新后的`plan-validation-final.json` |
| WIP commit / 普通push / 远端完整SHA | pass，`f8ed00b8c3424777bec5600ef6482838b9e1b2e6` | `wip-push-receipt.json`、`wip-ls-remote.raw`；不是EXIT-M0 |

issue #516再次刷新API得到403，错误raw保留；使用`updated_at=2026-10-28T09:59:30Z`快照，不声称核对新增评论。历史底座原生UI/EXE仅为历史证据，本轮未重跑。

## 4. 资源计量与保留

P3实际接收HTTP正文 **3,159,909,341B**，包括Python完整归档与Torch partial；主会话元数据2,841,978B、P2元数据1,202,846B、P1测得835,304B（合账保守预留2MiB）；P4/P5网络0，所有GPU0秒。以上是HTTP正文计量，TLS/代理/Git传输开销未知，不能填0或冒充网卡wire实测。详细分类、额外保守预留和E/F足迹在`resource-ledger.json`。

P1最初只读命令格式错误保留并修正；报告收尾含许可元信息超过15分钟约105.135秒，没有额外OS下载/启动。P3下载在600.234秒停止，包含证据/足迹审计的结案墙钟833.002秒；截止后没有继续联网/安装。P4首轮编码失败raw保留。F卷inode返回0导致P3原去重足迹低估，结案改用Win32真实文件ID/分配审计，保留文件实际分配3,229,349,936B、逻辑上界3,222,470,013B（不含目录/MFT元数据）；旧字段不入总账。

本轮不清理：保留新Python/venv、不可用Torch partial、合成夹具/junction及原始失败。partial未完成校验，不作为可信安装资产。未读写真实用户资料，未改变宿主功能/驱动，未安装训练引擎、启动VM或运行GPU；没有因本轮启动的产品服务需要终止，不操作根外服务。

## 5. 完成门与恢复条件

GATE-11、GATE-14与EXIT-M0保持blocked，M1–M6 pending。纯状态S提交保存报告/总控/门禁/复盘，最终完整SHA由外部`status-push-receipt.json`记录，避免自引用递归。WIP/状态保存均不解锁M1。

下一步补齐满足固定配方的CUDA实测机及允许范围、合法可启动的干净Windows与缺WebView2基线、完整依赖/预算路径，然后新attempt运行独立CUDA微探针。已向用户询问CUDA资源，尚未回复；不因沉默借远程机、改宿主驱动、超预算或降低四引擎验收。
