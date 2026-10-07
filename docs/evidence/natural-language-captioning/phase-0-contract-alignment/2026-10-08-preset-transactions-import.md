# 2026-10-08 预设事务、跨进程并发与显式导入验收

基线9574f03；本轮继续Issue #409/#405对齐。不是最终完成门或Phase5。

## 实现

- user_data/presets Caption存储采用线程RLock与OS文件锁。Windows为msvcrt字节锁，POSIX为flock，5秒有界等待；进程退出释放锁。所有读写和恢复使用同一锁。
- 预设变更、删除、上一份有效备份及settings默认引用纳入同一事务。prepared journal先原子落盘，逐文件flush/fsync+replace，全部成功后标记committed。写入失败恢复旧字节；进程硬退出后下一次读取先恢复未完成事务；已提交事务保留新版本并清除journal。
- 文档revision覆盖完整settings，其他设置字段改变也触发冲突；保留其他类型预设、settings schema_version和未知设置。拒绝ID大小写/外部类型冲突、不可移植ID、符号链接/junction路径和journal越界写入。
- 显式旧预设导入：必须确认，用户已有ID胜出；旧配置原样保留；导入标志与预设同事务保存，重复导入幂等，前端成功后隐藏入口。
- 系统提示词可编辑，名称/系统提示词/正文/语言/长度一起参与未保存保护和撤销；每模型草稿包含已保存快照。
- 增加刷新预设入口，只更新服务器列表/revision而保留当前草稿。并发409提示明确要求刷新后重试。

## 实际验证

1. 预设专项16 passed：真实两个独立Python进程在同一revision竞争，1 saved/1 conflict；写settings时注入OSError，预设/默认引用/备份字节完整恢复；os._exit(91)模拟写到一半和commit之后退出，分别恢复旧完整文档/保留新文档；保留训练预设与其他设置；外部设置变更失效revision；Windows junction实际拒绝；拒绝journal写auth.json。此junction测试不替代此前四项Windows symlink权限测试。
2. 相关后端矩阵223 passed/4既有依赖warning/35.03秒。随后新增API中文冲突提示，preset/http focused37 passed/2warning/3.05秒。没有把其他未运行全仓测试当作通过。
3. Node22.17.1完整check：340 tests/52 files，typecheck/lint/build通过；2项既有EngineStatusBar warning，最终构建8.31秒。新增确认/取消导入、导入冲突不丢草稿、系统提示词与名称撤销、刷新revision不丢草稿。
4. 新独立fake browser fixture：实际源码构建dist+FastAPI API，lifespan=off，无真实Key或模型调用。UI取消导入后user预设0；确认后1，旧配置仍1；当前未保存正文保持；import标志持久保存，入口消失。
5. UI另存为跨浏览器模板，默认ID及正文/系统提示词在独立BrowserContext中完全相同；停止后端并用fixture marker resume重启，再刷新浏览器仍一致；console零error。新增refresh按钮随后由组件测试/最终build验证，最终隔离验收仍须实际浏览器复验。

Browser root: workspace/sandboxes/nl-caption-presets-browser-20261008（仅fake业务验收，不能用于Phase5重建）。所有本轮自建fake server和子进程已停止，浏览器about:blank，tracked dist恢复基线；用户数据/备份/journal/lock均不进入Git。

## 边界和下一步

Caption文件锁协调本模块读写；后续#405共享存储合入时应复用统一锁接口。本轮验证进程崩溃恢复，不宣称已测试机器断电/文件系统损坏。无Agent接口或凭据系统修改。

仍未完成：user_data/tasks档案与现有TaskManager/TasksPage联动、从任务页停止真正取消Caption、重启状态/只重试失败项、档案写入失败禁止推理；Tag单图试标；完整矩阵/真实远程与本地/正式lifespan/Phase5从零重建。

单一下一步：将Caption任务注册到既有TaskManager，创建user_data/tasks/dataset-tagger/<date>/<time>_<job-id>的配置/任务档案，并打通任务页停止与重启状态。不得新建第二套任务调度器。Goal active。
