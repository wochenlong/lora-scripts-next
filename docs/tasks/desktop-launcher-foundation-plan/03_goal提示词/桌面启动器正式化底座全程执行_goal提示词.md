# 全程执行 goal 提示词

本轮已complete；以下保留为历史执行/核验提示词，不自动创建goal、不重复执行已通过任务、不授权对外发布。

~~~text
/goal 执行 E:/OpenSourceTeamWork/workspace/branches/dev/docs/tasks/desktop-launcher-foundation-plan 中定义的桌面启动器正式化底座全程任务。

以00_总控目标索引.md为唯一进度真相。先读README、plan-manifest、预检资料复盘、gate清单、governance、三目标计划、当前阶段任务书、当前阶段开工清单、最小可行性计划与报告、最终复盘。设计依据为docs/design/desktop-launcher-installation-model.md；原型报告只继承已证明的P1–P7。

当前三个稳定阶段及G1/G2/G3均complete，先核唯一总控和stage2完成/清理报告，不重复已过项。Rust最终15项、隔离Python同12files184/2/4、fmt/all-targets Clippy/前端/release通过；原生114检查/11图、三类恢复/允许删除/状态故障、最终EXE77检查/3图/WM_CLOSE与外部listener全部通过。预算与ZIP CRC/manifest逐文件SHA/source overlay SHA验证齐备，包身份以tools目录delivery/manifest.json和delivery-hashes.json为准。计划冻结后仅由主执行者重打纳入完成计划的源码overlay并重复包校验，不嵌入循环ZIP hash。

总目标是固定main@0785419e7dc1a3058bd8710a9aa933fec0aabdee与dev@9ca2de963122f34599e34e5ff382199de9188811真实安装/并存/切换/回退，profile独立且源码/解释器损坏恢复后资料保留。两个VERSION均3.3.1-dev，以完整commit和receipt/实际路径证明身份；不称main为稳定版。

只使用tools/launcher-foundation-20261028下新独立中文空格root与人工fixture；禁止接管/迁移真实用户数据、改系统Python或全局设置、commit/push/issue消息、模型下载/GPU训练/对外发布。整轮新增磁盘≤8GiB、累计下载≤1GiB、每次GUI健康≤180秒；超限停止相关动作并记录，不静默放宽。只管理本Job进程，结束/失败/关窗核PID和端口回收，保留失败日志、profile、backup和哈希。

按任务书完成unit/contract/integration/gray/real/Zero-Short或具体不适用说明。正式旧发布须有run/junction目标与资料哈希；真实GUI须有/api/version、HTML/JS/CSS和Job成员证据。API写设置/预设+library sentinel跨切换/回退/修复不变；registry坏schema/中断事务不静默覆盖；current/known-good删除保护有效。原型成功与UI标签不能代替这些正式证据。

阶段报告、失败、cleanup、变更控制及总控台账已经齐备；全部原始失败和边界保留。当前无待办实施动作，后续范围另立任务，不擅自重开已完成计划或扩大用户授权。

只有G1/G2/G3与阶段2完成门都有实测证据且无未处理P0/P1，才把本轮底座标complete；如有not-run/unknown原样报告。GPU、精准引擎修复、签名更新、已有接管、完整取消续传和干净机仍是#516后续，不宣称issue全部完成。
~~~
