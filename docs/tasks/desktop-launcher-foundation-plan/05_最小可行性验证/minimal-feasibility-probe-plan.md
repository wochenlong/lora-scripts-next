# 最小可行性验证计划

Date：2026-10-28；Plan：desktop-launcher-foundation-20261028；Result：complete-with-boundary。F0–F3及完整目标/清理/预算/交付验证已通过，原始失败和后续未测边界见报告。

## Critical Assumptions

| ID | 假设 / 风险 | 已有证据 | 新探针 |
| --- | --- | --- | --- |
| F0 | 本机原生窗口、受限PATH自管工具、真实GUI、Job可用 | 原型及正式最终EXE77检查/关窗证据 | 已通过；不重复原型 |
| F1 | run junction能承接旧版写入，重建视图不丢profile；假则P0 | Python A→B→A、14处实际联接和双版本GUI/损坏恢复资料哈希已过 | 已验证，原始路径/哈希在stage1与recovery证据 |
| F2 | receipt/registry/事务失败不会改当前可用指针或profile；假则P1 | model fixture及真实故障9项17CLI已过，自管Python旧P1关闭 | 已验证；其他删除/base Python等目标2余项仍补测 |
| F3 | 两commit各真实启动并共享资料而隔离compat | 原生114+77检查、14图、三类恢复/故障/允许删除/清理与交付通过 | 已通过；下载日志估算和后续未测边界保留 |

## Probe Matrix

| Probe | Command/Method | Resource / Limit | Evidence | Cleanup |
| --- | --- | --- | --- | --- |
| F1 | 管理核心在新fixture生成run及固定联接；PowerShell Get-Item -LiteralPath查看LinkType/Target；通过run写人工sentinel后按正式修复路径重建；校验目标内容SHA256和immutable app未变 | Windows本地；≤120秒；≤64MiB；不联网 | stage1/junction-probe/：实际绝对路径、前后哈希、stdout/exit | 仅解除受控联接/停止本Job，保留fixture与报告；不递归删除目标 |
| F2 | 核心单元/契约fixture中构造缺失/坏registry/未知schema/未完成事务；比较失败前后current/profile哈希 | 本地≤120秒、≤32MiB；不安装GUI | stage1/state-probe/：case输入输出与哈希 | 保留损坏文件；停止受管进程 |
| F3 | 以当前CLI --manage install-release/select/rollback/smoke与原生UI真实启动，API写入fixture再复读 | 全轮8GiB/1GiB；每GUI180秒；无GPU | stage2/完整矩阵 | 回收本Job/端口，保留profile和证据 |

CLI完整参数以执行时main.rs为准并记录原始命令。若F1必须绕开固定路径保护才能成立，视为失败，修改映射实现后复跑；不能用任意联接目标的手工成功代替管理核心。

## Failure Handling / Decision

F1或F2失败则GATE-11保持conditional/改fail，阶段2不解锁；保留已验证F0和Python证据，回到阶段1修复，不重做无关原型。F3失败阻止本轮完成。无“未验证但默认通过”的豁免，用户已授权隔离探针，不需要新增用户批准门。
