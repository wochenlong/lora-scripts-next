# M1：已有实体的安装登记恢复

本切片承接 #516 的精准修复要求：源码、基础 Python 和 GUI 环境仍完整时，离线补齐丢失的安装登记。正式入口为环境页的“恢复安装登记”，同时提供 CLI 与 IPC。M1 整体仍在施工，本文描述已实现合同；实际通过范围以总控索引和外部测试回执为准。

## 身份与信任来源

恢复限于内置 Catalog 与固定 GUI 配方匹配的发布，以及原位置的受管实例。预览不执行解释器、下载或安装依赖；它验证完整源码、基础 Python、既有状态及环境文件，返回候选实例、阻塞原因和计划 SHA256。多个候选必须明确选择，同 ID 在两个存储命名空间中出现时拒绝猜测。

环境文件的信任来自固定原始归档生成的随壳索引。81 个 wheel 的原文件、固定 uv 生成的控制文件、入口程序、解释器归属和完整目录闭包均须通过；本地 RECORD 不能扩展可信文件集合。删除下载缓存后，仍可核验已安装文件。索引来源、摘要和复现方法见 `desktop-launcher/scripts/registration-index/INDEX-PROVENANCE.md`。

已有干净实例保留其状态。实例记录缺失时，通过完整独立证明建立新的登记恢复 epoch，记录来源和固定索引身份；保留旧 binding 所知代次的下界。损坏或未知格式的状态、dirty/pending 事务、配方或 binding 不一致均阻断补登记。

## 实际验证与提交

用户确认预览的实例与计划 SHA 后，操作持有工作区独占 lease，重新核验输入，并实际运行解释器、依赖检查和 GUI 入口。入口使用事务备份目录内的独立源码副本、profile、state 与日志；再次验证副本后才执行。入口探测核验 `/api/version`、首页及本地静态资源，随后停止自有进程树并检查监听释放。

探测子进程配置自有 loopback 拒绝代理，避免按用户网络设置向上游转发；这是子进程网络配置约束，不宣称操作系统防火墙隔离。真实网络证据单独计量。探测不连接生产 profile 或既有 runtime view 的资料联接。

完整验证后才持久化精确提交意图。每个目标记录都有旧值、候选新值及独立快照摘要；临时写入位于本事务备份目录。所有记录先验证为预期旧值、新值或原定缺失，遇到第三种状态拒绝覆盖。已落盘意图使普通变更与启动暂停，重启后由“继续未完成登记恢复”重新核验实体并续办。

补登记可以恢复 release receipt、缺失的实例记录和 registry 安装/binding 记录。它不重建 venv，不恢复历史健康时间，也不根据目录顺序推断丢失的 current/previous。登记成功后由用户选择版本并正常启动，产生新的实际启动健康事实。

## 接口

CLI 使用同一 EXE：

```text
--manage preview-gui-registration <root> <release_id> [instance_id]
--manage restore-gui-registration <root> <release_id> <instance_id> <plan_sha256>
--manage recover-gui-registration <root> <release_id>
```

IPC 对应 `preview_gui_registration`、`restore_gui_registration`、`recover_gui_registration`。恢复操作沿用任务进度、取消和错误回执。预览状态为 `ready`、`blocked` 或 `pending`；阻塞原因直接展示，计划输入变化后必须重新预览确认。

## 验收边界

必须分别验证：可信索引及拒绝未知文件、提交记录的第三态/快照篡改/中断恢复、普通入口的事务门、无缓存登记丢失后的原生操作，以及完整环境与资料原字节保持。此前安装、单包修复、基础 Python 和预算的新旧包证据均保留自己的包身份，不能替代此切片的新包实测。显式新路径重建属于后续独立事务；它不得清除旧 dirty/pending 事实。
