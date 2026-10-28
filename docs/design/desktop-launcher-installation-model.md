# 桌面启动器安装清单、版本目录与用户资料模型

日期：2026-10-28。需求：[独立启动器 #516](https://github.com/wochenlong/lora-scripts-next/issues/516)。本设计将已通过真实验证的 Tauri/Rust 管理核心接入正式目录和状态合同；当前交付为正式启动器的基础版本，后续引擎精确诊断、网络管理和自身更新沿同一合同扩展。

## 1. 设计依据与取舍

样包证明桌面窗口、校验下载、独立 uv/Python、源码恢复、完整 GUI 环境安装、Job Object 进程归属和语义健康检查可行。样包的问题是单一硬编码版本，源码、运行数据混杂，恢复后只能手动从备份找数据。

采用三种独立身份：release（不可变发布清单，按完整 Git commit 标识）、environment（发布对应的 GUI 环境）、profile（用户资料与数据架构版本）。版本号只用于展示，不能作为唯一键。本次实际核实 main 和 dev 的 VERSION 都为 3.3.1-dev；它们仍是不同发布。

允许 source 与 environment 分别修复；禁止用默认整包重装替代单项操作。用户资料永不属于发布卸载或源码修复的删除范围。首次安装组合调用已验证步骤，并展示分阶段日志；后台检查或启动窗口不触发安装。

## 2. 安装清单

`desktop-launcher/catalog/releases.json` 为 schema_version=1 的嵌入清单。关键字段为 id、channel、version、完整 commit、archive.url/sha256/bytes/unpacked_bytes、python、uv 资产及二进制哈希、environment_recipe、profile_schema_version、data_contract、required_files。

- id 必须为安全的单段路径，channel 为 main/dev，commit 为完整十六进制哈希；URL 为 HTTPS，SHA256 格式和体积有限额。
- 仅接受编译进启动器的发布清单；UI 只能传 release ID，不能传任意 URL、路径或命令。
- 源码归档缓存以归档哈希命名；只有下载校验与解压/入口检查通过的目录才可登记已安装。
- environment_recipe 明确依赖配方身份；本期按 release 隔离环境，不凭“版本号相同”共享环境。requirements 仍包含范围版本，完整 wheel 锁和签名的远程发布清单列为后续发布工作。
- 本地 receipt 记录原始发布清单及安装时间。状态文件丢失时，可从 receipt 与实际源码重新发现版本；receipt 不能代替源码哈希及环境的实际检查。
- 下载体积与展开源码体积均来自归档实测。它们不冒充完整依赖下载量或安装后的磁盘占用；依赖、Python、备份另占空间。

## 3. 目录合同

```text
选择的安装根/
  .launcher-workspace                 正式布局 schema 的所有权标记
  .launcher-lock                      跨进程安装/运行互斥
  state/registry.json                 当前指针、上次健康版本、安装记录
  state/journal-<release-id>.json      分版本安装/修复阶段日志
  releases/<release-id>/
    release.json                      发布 receipt
    app/                              已校验源码和已构建前端
  environments/<release-id>/gui/       该发布的完整 GUI 虚拟环境
  run/<release-id>/                    兼容工作目录，程序从这里启动
  profiles/default/
    profile.json                     用户资料 schema 与身份
    user_data/                        共享 settings/presets/task archives/auth
    library/{models,tagger-models,datasets,output}/
    compat/<release-id>/              旧版配置、队列、日志、插件和引擎
  python/<python-version>/            按 Python 版本隔离的自管解释器
  tools/ cache/ staging/ backups/
```

`releases` 属于管理层；`profiles` 属于用户。`run` 是可重建的工作目录，拥有副本源码和指向 profile 的目录联接。它不是另一个发布源，健康检查和修复始终以 receipt/源码事实为准。源码修复保留旧源码，重新生成工作目录，不移动 profile。

旧版兼容映射：user_data→共享 user_data；sd-models/tagger-models/datasets/output/outputs→共享 library；config/toml/logs/.runtime/extensions/train/assets/.cache→compat/<release-id> 同名目录。首次只补齐缺失的版本默认文件，不覆盖已有用户内容。Windows 目录联接不要求用户打开开发者模式；联接目标由启动器固定映射，不能由 UI 输入。

assets 内包含旧版 assets/config.json，因此整个 assets 按 release 保存；大模型缓存由明确 library 或兼容路径承接，不复制到发布源码。用户指定的外部绝对模型/数据路径保持原义。

## 4. Python 新接口与旧版兼容

`NEXT_TRAINER_DATA_ROOT` 指向绝对 profile 根；`NEXT_TRAINER_STATE_ROOT` 指向 profile/compat/<release-id>。新 `mikazuki.paths` 只负责路径解析，未设环境变量时维持当前 CLI/整合包的所有默认行为。UserDataStore 使用共享数据根，队列、旧配置、网络设置等使用版本状态根。

旧版本不认识上述变量，仍通过 run 目录联接获得相同隔离结果。启动器不向外部源码注入 Python 补丁，也不改变系统 Python 或全局配置。任意第三方插件写入私有硬编码路径不在当前隔离保证内；正式插件应使用受支持的资料接口。

profiles/default 使用 schema 1。切换仅允许清单明确兼容此 schema 的发布。未来有破坏性数据升级时，新 profile 或有快照的显式迁移必须先完成，不能让旧版本直接打开新 schema。任务队列、引擎环境和插件先按 release 隔离；共享 user_data 的配置架构必须兼容，manifest 是发布方的声明而非自动推断。

## 5. 安装、切换和回退

安装：持根目录锁→持久化事务意图→校验缓存/下载→独立 staging 解压→入口/完整性清单→发布 receipt→原子发布目录→登记安装记录→准备环境并实际导入→首次安装才选择当前版本。后续安装另一发布不改变 current。

切换：停止本启动器进程→核对 profile schema→实际校验目标源码与环境→原子替换 registry。不会下载已安装版本，不移动用户资料。启动成功且健康接口版本与 Job 归属均正确后，才标记该发布为健康。previous_known_good 保留上一个真正健康且可回退的发布，不能把“解压成功”当可用版本。

回退：检查 previous_known_good 对应 receipt、源码、环境及 schema→原子切换指针。失败时保留现有指针并给出具体缺失原因。源修复只修源码，依赖修复只处理 GUI 环境；基础 Python 修复不修改版本目录。

删除：当前版本和保留的回退版本不可删；其他版本的源码/环境/工作目录移入备份后才移除登记。用户 profile 和共享资料不纳入删除，旧版状态仍保留供用户核对。自动清理策略本期不启用。

## 6. 事务、损坏与安全边界

- registry 使用同目录临时文件、flush/sync 和 Windows 原子替换；损坏或未知 schema 报错并拒绝写入，禁止静默重置。重启后忽略未提交 staging，并显示待处理事务。
- 目录发布与 registry 不可能跨文件原子：已发布 receipt 但未登记时 reconcile 可重建 installed；current 不凭磁盘扫描自动猜测。旧指针仅在明确切换且校验通过后变更。
- 已存在的非空未知目录和样包旧布局均拒绝直接接管。本次使用全新根；旧安装迁移另设“扫描→预览→复制→校验→切换”的显式流程，不能在打开软件时自动搬迁。
- 固定 release ID、拒绝路径穿越和 Windows 保留名；写路径拒绝重解析点逃逸。只对本程序创建的 Job 管理进程，不按端口或名字杀未知进程。
- 全过程不自动删除失败现场、备份、用户资料。异常后先显示磁盘事实和日志，用户可重试对应阶段。

## 7. 本次可执行验收

1. 全新中文空格目录执行首次安装，真实启动GUI和前端资源；系统 PATH 不提供 Python/uv。
2. 安装两条真实 main/dev commit，分别启动，已安装版本切换和回退不重新下载。
3. 通过 user-data API 写入设置/预设并创建 library sentinel；切换、回退、源码恢复后保持内容和路径。
4. 删除 registry 的副本/损坏 registry/未知schema/中断事务：可从receipt发现，或明确拒绝变更，不能覆盖旧状态。
5. 损坏源码和解释器分别走修复，不搬移 profile；检查备份与进程/端口回收。
6. 原生三页UI验证安装引导、版本列表/切换/回退/删除保护，以及具体环境错误。

完整阶段和执行状态以 `docs/tasks/desktop-launcher-foundation-plan/00_总控目标索引.md` 为准。GPU训练、各引擎精准检查修复、启动器自更新、签名安装器和干净机器验收属于后续 #516 工作，不因本次基础模型落地宣称完成。
