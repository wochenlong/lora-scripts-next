# CR-017：源码修复配方与历史安装兼容返修

状态：complete-with-boundary，已旁置交付原入口。来源：用户截图报“该发布版没有匹配的可信源码及捆绑前端修复配方”，首页检查并修复不可用。已完成必要回归、同包原生受影响流程与旧用户根只读复核；不重跑四引擎/GPU或全套安装。

## 已确认原因

1. 新4e68df24的可信源码清单为1942文件，而gui_source_repair仍独立校验1741，导致正确的新发布也必定拒绝。修复前6项定向测试中2项真实复现同一错误，证据 `source-repair-before.log`。前轮测试集中服务运行时拒绝主程序修改，没有走停服后的源码修复预览，因此漏掉此路径。
2. 当前用户默认根安装的是89a3b6ca（registry只读核对）。新壳的源码完整性入口只接受4e68，却对所有历史通用GUI recipe标示同一修复能力，导致旧完整安装误报需要修复，修复又不匹配。截图本身不能证明当前使用哪一根；这里分别记录实际默认根与已确定代码缺陷。

## 决定与边界

- 完整性和源码修复共用一个内嵌可信manifest验证入口，校验原字节SHA、归档身份、文件计数/总字节、路径/哈希/Windows别名，不信任本地.source-integrity.json。
- 现行4e68可信清单和从已保存b2436b4a取得的89a3历史清单各自固定。历史1844文件/103757791B，原字节SHA `bce3945607a7ec7925e843cd236e93c8fcd0e7f013291b24d4d84abb3117eccd`。89a3可按原可信身份检查及使用；未封装的更旧发布继续拒绝授信。
- 历史源码可验证不代表新壳有其全套精准修复/登记/重建配方。输出source_supported、maintenance_supported、install_supported独立能力，旧版本不套用新配方，不自动更新、切换或覆写用户环境。
- 旧健康版本保留启动入口；需维护但无配方时明确引导版本管理。不支持的历史安装/准备/修复按钮关闭，不再把缺可信材料称为源码损坏；引擎/资料/信任/壳更新面板继续绑定真实当前发布。
- 用户现有窗口、服务、安装目录、模型和资料只读保护；只在Root原有ec18自有测试根中注释破坏gui.py并验证正式修复，保留原文件备份。

| 编号 | 行为 | 验证 | 状态 |
| --- | --- | --- | --- |
| R1 | 当前源码修复预览共享1942可信清单、旧89严格校验 | 源码修复7项、完整性6项、发布能力1项通过 | pass |
| R2 | 未封装旧版/不匹配归档拒绝，新配方不修历史源码 | 同组含可信清单字节、路径/哈希/别名、历史错误配方负向回归 | pass |
| R3 | 历史版本能力与当前面板绑定明确，英中提示/旧启动正常 | Vue类型/构建、最终兼容18项和原中英18项通过；只读复审无阻断，删去过度承诺文案 | pass |
| R4 | 最终包新版本预览/取消、损坏后正式修复及真实服务恢复 | candidate-2/native-source-05，16项、正式Repair成功、真实网页/API200、保护树不变且正常回收 | pass |
| R5 | 最终EXE对用户默认89安装只读检查通过且不改状态 | final-default89-readonly-03，五项可启动检查全true，38,801项/2.904GB前后严格零变 | pass |
| R6 | 保存源码基线、同包旁置原入口并普通push | 两次产品基线已push；9文件旁置/唯一start行/旧说明字节/旧程序/备份/证据6项全true，最终文档随收尾push | pass，文档远端回执见外部final-baseline.json |

外部证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-source-repair-20261031`。保持原美术标签，训练器配方不重冻（Python未修改），四引擎和GPU本轮不实装、不训练。所有旧失败保留。

最小静态检查：`cargo fmt`、定向发布能力测试、`cargo clippy --locked --all-targets -- -D warnings`、`npm run build` 和 `git diff --check` 已通过。只读独立复审确认旧current面板绑定和现行配方入口无功能阻断；反馈的“此版本可继续使用”提示已收紧，避免在真实损坏时承诺可用。

实现基线 `b13d0d731f9e86517b6bb8208f643baf4319eefb` 已普通push并核对远端。最终文案微夹具 `compat-ui-03` 18项通过；首次文案选择器不匹配记录独立保留。

## 最终候选与中止记录

- 当前最终候选为candidate-2，编译基线`5dc68bea`、输入干净，训练器仍为4e68df24。EXE SHA256 `8560e16af584cf56459e45cb498b2149fc4b7e01593eefa7e8c47b96dec7c1b8`；便携ZIP `0ccf61afce72bbea1d0e9f5087209cef0b215b4f4a3cc958f89f04f59f6d73a7`；NSIS `9493b4a84c454a4facf1877a054558c7e495c0bbfc5ede8af5b99450b5cab2d5`。最终原生源码与旧根只读检查统一使用这个EXE。
- 历史candidate-1（EXE `1ec96d6a65fa75df6fd1ed74ff1755f1e4095404682ea35d20b9914cb75f2f9e`）完整保留；前置未安装环境优化后由candidate-2替代。
- `native-source-01` 已通过自有ec18的当前源码/环境/前端检查，在全根SHA快照工具阶段中止，尚未追加损坏探针。正常退出exit0、Job排空及CDP/服务端口回收均通过；保留原报告，工具调整后继续。
- `final-default89-readonly-01` 在前快照的cache内深路径遇到Windows MAX_PATH，尚未执行inspect；不算产品失败或审计通过。仅修改外部工具支持长路径后继续，不改用户目录。
- `native-source-02` 在UI自动完整检查90秒工具上限中止，未进入预览或探针，正常退出与端口回收通过。`final-default89-readonly-02` 的inspect达到300秒上限，不能计为可启动通过；但完整前后快照38,801条目/2,903,625,404字节完全一致，1844可信源码前后均通过。树SHA均为`80926eb0a88427ac21fb589765c179a17a13754d4c41a93ab961716a42ce5d25`。
- 为排除重复校验，已确认旧实现对每个未安装的受管历史版本也先完整扫描4184个Python文件，最后才检查环境是否存在。新增最小前置保护：先验证环境目录和解释器存在，缺失即返回原失败语义；已安装环境仍执行所有可信Python、绑定、配置和导入检查，不建立跨调用缓存。独立代码复审与严格Clippy通过。正在运行的`native-source-03`为此正常中止并保留，改用新候选完成验收。
- `native-source-04` 在新包首次UI检查通过后，因夹具试图替换不可写的Tauri invoke属性而无法记录返回，未进入预览或探针。之前“被初始化覆盖”的推测由属性descriptor证据纠正为`writable=false/configurable=false`，保留纠正说明；正常退出exit0、Job和端口回收通过。随后完全去掉hook，改为UI真实操作、只读官方IPC独立核验和磁盘结果，不再冒充捕获原返回。

## 最终包原生结果

`native-source-05` 对同一个candidate-2 EXE完成16项正式验证，`fixture_session=false`。UI真实展示1942条源码及2条其他预览项目，与独立官方只读IPC逐行一致。预览取消后41,107条目全根快照无变化。只在自有ec18的gui.py追加有备份的精确注释，正式检查source=false；通过界面确认的唯一Repair任务`download-1793459659-208468-0`成功，gui.py恢复SHA `9450e21ddb1fa1bbc042662cf0085f7ffd639cdd70dddc57f3aa996fe6ecede1`。环境、Python、资料和非目标版本保护树`changes=[]`，registry绑定/generation保持；修复后source/environment/frontend全部通过。

随后通过UI启动真实4e服务，run `start-a493fa84-c287-403a-a753-81bf5388090f`、服务PID206104/端口11582，网页和`/api/version`均200；通过UI停止同一服务并明确退出启动器。宿主PID208468/FILETIME134379329588634224为exit0/graceful，Job active0/drained，CDP1860及服务11582端口回收。健康预览、损坏预览与服务就绪三张PNG保留，Root及独立代理目视核对通过。

本轮最终官方只读inspect分别17.659s（初始）、15.148s（损坏）、21.856s（修复后）；初始UI自动完整检查约24s。完整全根SHA快照169.37s属于测试工具的额外证明成本，不当作产品操作耗时。没有把前轮超时旧包数字与本轮当作同条件性能基准；本轮证据只证明未安装历史环境不再重复完整扫描且受影响功能可用。

## 旧用户安装只读复核与交付

`final-default89-readonly-03` 使用同一最终EXE，对默认旧89安装执行`--manage inspect`，exit0，实际耗时120.317s，uv/python/source/environment/frontend五项全部true。source_supported=true、maintenance_supported=false、install_supported=false；这表示旧版可以严格检查并继续启动，本包没有旧版的全套安装/精准维护材料，不自动更新或切换。该深目录完整检查仍需要约两分钟，本轮没有将其宣称为即时检查。

完整前后38,801条目/2,903,625,404字节严格零变化，树SHA均`80926eb0a88427ac21fb589765c179a17a13754d4c41a93ab961716a42ce5d25`，可信1844源码前后全匹配。未操作用户窗口或服务。

已通过只读部署预检并旁置到`F:/NextTrainerLauncherSandbox/user-20261031/launcher-source-repair`。原`启动启动器.cmd`仅替换唯一start行，WebView/网络配置字节保留；原说明015/016完整字节保留并追加017。9个制品文件与最终包完全一致；旧程序/入口备份及验收证据保留，6项交付检查全true。备份位于外部证据根`user-entry-backup`，回执为`user-entry-update.json`及用户目录`source-repair-update.json`。

用户需先从托盘右键完全退出旧启动器，再双击原入口；单击关闭按钮默认仅隐藏，已运行程序不会自动变成新版。本轮没有代用户启动新版或停止旧窗口、改动安装/模型/资料。

最终结构化结果见[source-repair-20261031-validation.json](source-repair-20261031-validation.json)。旧失败/中止及归因全部保留。本轮没有重跑从零全安装、四引擎实装、GPU训练、干净Windows/WebView首装或托盘双语原生矩阵；后两能力沿已交付代码保留，新增文案中英回归已过。本包仍为开发候选，不作为公共发布。

Next action：本轮约定返修与交付完成，用户可从原入口继续实测；最终文档提交与远端SHA回执保存在外部`final-baseline.json`，避免提交自引用。
