# 可行性证据快照

日期：2026-10-28；阶段0–2及G1/G2/G3均complete；最终完成/清理证据索引于evidence_root的stage2报告。

| 假设 | 状态 | 实际证据 / 限制 |
| --- | --- | --- |
| F0工具链/下载/真实GUI/Job | inherited-pass | docs/tasks/desktop-launcher-prototype.md P1–P7；tools原型目录的CLI/原生UI/损坏恢复报告。覆盖当前本机，不覆盖新机器 |
| 新Python profile接口 | pass | 本轮补录`python-regression-fixed.log`为184 passed、2 skipped、4 warnings，同12files覆盖A→B→A真实子进程。精确命令/解释器/依赖版本在`python-regression-fixed.json`；使用既有隔离CPython3.10.20，未改系统包 |
| F1正式run/junction重建资料保留 | pass | Rust真实联接测试、`stage1/verification.json`14处目标与哈希、双版本GUI/API及`recovery/summary.json`源码/环境恢复保留profile treehash/inode均通过 |
| F2正式registry/receipt异常不覆盖 | pass | Rust模型测试及`fault-test-20261028-220235-e383a2/report.json`9项17CLI通过：坏/未知registry/profile拒绝、journal显现及清除、receipt重建不激活、回退/删除保护、未知非空根拒绝、精确恢复 |
| F3main/dev安装/切换/回退/资料 | pass | formal-cycle114检查/11图、三类恢复/允许删除/状态故障通过；最终EXE另有77检查/3图和WM_CLOSE/外部listener实证，预算与交付校验齐备 |

构建快照：最终`cargo-test-final.log`15passed，补齐schema/SHA/下载和展开大小负向，fmt/all-targets Clippy/release完成；前端build通过。生产manifest预算统一既有运行时上限，最终EXE SHA256为`11c488343a9f7097ca8c8effe71ecfa595911793ce012e5eb4ce2b5a5db4cc74`，旧`0fb27459…`保留pre-final，catalog未变。`stage1/final-build.json`记录映射，最终新EXE运行复验不能沿用旧结果。计划维护者只读核Rust/构建，亲自运行Python补录。

已发生失败：dev首次安装因uv内部别名junction误拒绝，exit1/236.095秒，原始记录已固定为`attempt1-install-dev.*`。修复后同受限PATH重试exit0/87.221秒，见`install-dev.*`；随后真实GUI完成双版本循环。默认系统Python3.14补日志因NumPy/cv2 ABI及httpx/Starlette不兼容出现7 failed/177 passed/2 skipped，`python-regression.log`保留；改用既有隔离环境同12files达到184/2/4，未改系统依赖。

中断事务修复：健康重试写`Phase::Committed`的行为已通过故障验收，`recovery/03-source-smoke.stdout.json`的interrupted为空。早期截图的Preparing记录保留为历史事实，不改成成功。完整安装耗时与GUI就绪180秒预算分别计算。

自管Python旧P1关闭；基础Python/允许删除/清单负向通过；最终EXE77项复验及WM_CLOSE0.819秒回收3进程/两端口、外部HTTP200保留通过。新增磁盘保守有效载荷合计6,052,497,460B，下载日志估算531,588,607B，明确非NTFS/网卡逐字节计量。ZIP CRC/manifest逐文件SHA/source overlay逐文件SHA校验通过；包身份只引用`delivery/manifest.json`和`delivery-hashes.json`。

决定：本轮全部关键假设、三目标和三阶段通过，底座complete。无自动迁移真实资料授权，无GPU或签名更新验收；全部旧失败和边界保留。
