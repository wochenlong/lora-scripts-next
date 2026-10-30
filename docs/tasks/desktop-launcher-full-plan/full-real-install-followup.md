# CR-008 实际安装失败返修与真实训练冒烟

当前状态：本轮要求的功能修复与真实验证完成。下载预算整个删除；最终第5候选包在新空根 `r12` 真实网络下载安装、GUI服务与前端、正式Kohya安装/imports/CUDA、正式 `/api/run` 两步GPU训练和实际权重读回均通过。同版手测部署已成功，正常无CDP窗口已打开并预选r12，自动检查完成、显示“可以启动”且“启动训练器”按钮可用，已就绪供用户手测。工作副本 `E:/OpenSourceTeamWork/workspace/branches/dev`，分支 `feat/desktop-launcher`，返修前HEAD `b2340e65f61b0426d5474852ec8c9f4861157df3`。

证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/full-real-20261030/`。既有手测根 `F:/NextTrainerLauncherSandbox/test` 失败现场保留，新的真实验证使用独立短根，不用旧缓存冒充从零下载安装。

| 要求 | 执行/验证 | 状态 |
| --- | --- | --- |
| 定位用户实际失败 | 原生窗口截图、state/operation/partial元数据；下载账本写入不确定错误 | 已定位并留证 |
| 删除下载预算 | 前端UI/状态/类型、后端账本/限额/CLI/IPC移除，旧账本不再读取 | 实现完成；19项下载+1项终态回归、严格Clippy、前端构建和4项工具测试通过 |
| 完整下载安装 | 新EXE，空工作区，真实下载源码/工具/Python/wheel并完成环境检查 | pass；最终第5包、r12空根、原生UI真实下载和安装，无缓存预种 |
| 真实服务可用 | 主程序启动、版本API、前端HTML/JS/CSS、正常停止/重启 | pass；同第5包、同r12，实际接口和资源通过 |
| 正式Kohya安装与CUDA | 原生环境页正式独立安装、收据/ready绑定、实际关键导入、独立解释器CUDA张量 | pass；第5包真实安装operation succeeded，收据SHA与state/固定锁一致，5.5.3/0.22.2与CLIP/Qwen3.5符号导入通过，CUDA矩阵sum3680 |
| 真实训练冒烟 | Kohya SD1.5 LoRA，公开许可固定4.26GB底模、两张合成512图、2步真实梯度更新，权重落盘与读取 | pass；正式API任务12eb6aac-48ec-4dee-9dea-944095005c12 FINISHED/rc0，576有限张量，192个LoRA up非零 |
| 同版交付 | 新安装器/便携包、已安装可操作沙盒、精确提交/push/远端SHA | pass；第5包及dfc70369已push，manual部署回执deployed、EXE SHA一致；正常无CDP窗口已打开且自动检查完成，显示“可以启动”，启动按钮可用 |

已有记录：用户窗口报“下载计账写入结果不确定，停止读取；释放session后持租约重新核对”；源码partial 12,845,837 B，磁盘operation仍running。上次仅完成源码预取和界面就绪，不能证明本次完整安装或训练可用。

方法采用实际故障回归与用户流程验收，沿用既有任务书，不创建重复规划体系；结果逐项区分pass/fail/not-run/资源限制，不以静态构建或夹具代替真实训练。

## 追加：新用户沙盒准备（2026-10-30）

用户要求另建新沙盒供实测和日常试用。交付目录为 `F:/NextTrainerLauncherSandbox/user-20261030`，独立受管安装根为 `F:/NextTrainerLauncherSandbox/u13`；原 manual/r12 不修改。本轮复用同一最终第5包和按固定摘要校验的不可变安装归档，正式在新路径创建主程序及 Kohya 环境，不复制 venv、旧用户配置或任务状态，因此不另称一次网络冷下载。证据位于本轮根下 `user-ready-20261030/`。

当前为 ready：新根主程序安装、版本接口与网页资源通过；Kohya 正式安装、收据提交和实际 imports/CUDA 通过，独立 Python 为 `u13/e/t4d70c934b39a4eb/Scripts/python.exe`。Kohya 本轮计划/安装/自身校验约 11 分 22 秒。已本地复制并核验 SD1.5 底模、分词器、两张合成图片与 caption、原始许可，共 11 文件、4,266,774,393 B；两步/二十步 TOML 均已通过真实页面导入和最终序列化预览核对。

新页面经“开始训练”及确认弹窗实际单次提交，任务 `7e2e99e4-eb38-4603-9ce8-a209ca65cc24` 已 FINISHED / returncode 0，19:48:04–19:48:52（北京时间）；命令使用上述 u13 受管 Python。权重 `user-20261030/output/user-sd15-smoke-2steps.safetensors` 为 3,476,992 B，SHA256 `8a70ed40a78102c3641d05ca36860a23b285d6feb20bd1be4dd180e1da2218f1`；实际重新读取验证 rank4、576 张量全部有限、192 个 LoRA up 非零。`training/ui-real-training/` 内 ui-training-report / train-result / artifact-verification 均 passed=true，浏览器错误为空。二十步配置只验证导入，未运行二十步训练；自有测试浏览器已关闭。

本次确认训练后同步校验约 232 秒，实际训练约 48 秒；首次页面状态与安装检查也有等待，使用说明据实注明。原自动化漏点二次确认时未创建任务，发现后仅在同一页面补确认，没有重发 API 或创建重复任务。

原测试控制器已正常关闭，exit0 / graceful / Job排空 / CDP回收均通过。新普通窗口 PID170640 无 CDP，预选 u13，启动时检查已通过并通过真实按钮启动服务；普通服务 `http://127.0.0.1:7584` 的版本接口返回 status=success、version=3.3.1-dev，见 `normal-api-health.json`。已通过本窗“在浏览器打开”按钮打开系统浏览器，见 `normal-session.json` 的 service-ready / browser_open_invoked=true。用户入口为交付目录 `启动训练器.cmd`；`开始使用.md` 和 `训练示例使用说明.md` 给出页面导入、确认、等待、查看产物与停止的操作。程序环境和 venv 保留新安装时的 u13 原路径，旧沙盒保留。

## 最终第5包实际结果

训练器源码固定为 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`，壳/清单保存基线 `dfc70369` 已普通push。包目录为 `F:/NextTrainerLauncherSandbox/build-r8/windows-candidate-5/`，EXE SHA256 `9fbac881f0de9678bb8dbf2a8865a13fe7fabcb968d51c84d407c995934b88fc`，便携ZIP `6929057695b2f3666ec3f9595beff5d9d1f589de0c0bf9cbcbf7f62b78bfa1f4`，NSIS安装器 `e03add1d83c9450da8aaa325373e18fbb85f14f6ba8036eab4076f2138a0fdaf`。同版回执位于 `native-install-5/`，不能用先前包或外置diagnostic_only结果代替。

新空根 `F:/NextTrainerLauncherSandbox/r12` 已完成实际下载/安装与GUI启动、真实版本API和页面资源、正常停止/重启。Kohya正式安装操作 `download-1793345316-152568-1` succeeded，实例 `t6d4d73c3e97e473`，受管Python为 `F:/NextTrainerLauncherSandbox/r12/e/t6d4d73c3e97e473/Scripts/python.exe`。实际收据SHA `eac40e3411b1da52edc6e1e7f5d1d47c349afc4f9552c209b7ce6a28eaed2d86`，与ready state、固定Kohya锁 `c0a7310d44e61a03f6b6a33b2f634edb68776012fec7845baa346af143c594b1` 和配方 `95621a5c5efa2cb18088f5339960f6d5e470015cd7fcee13e5ddbf5b855e3ec2` 相符。`kohya-install/report.json` 顶层passed=true；实际使用该解释器导入torch/accelerate/transformers5.5.3/tokenizers0.22.2/diffusers和CLIP/Qwen3.5符号，并执行CUDA4×4矩阵，sum3680。

正式安装事务已校验完整文件闭包，本轮不重复独立UI全扫描与产品imports probe，二者明确skip。报告layout注明从真实ready state与原始安装收据派生；真实imports/CUDA原始日志另存，没有将派生结果冒充原始IPC。最终API训练继续执行产品自身的绑定与源码校验。

正式 `/api/run` 任务 `12eb6aac-48ec-4dee-9dea-944095005c12` 已FINISHED/returncode0，命令确实使用上述r12受管Python与 `r12/s/t6d4d73c3e97e473/scripts/stable/train_network.py`。SD1.5、rank4、FP16、batch1、UNet-only完成2个真实优化步。实际产物 `F:/NextTrainerLauncherSandbox/training-r8/output/launcher-real-smoke.safetensors` 为3,476,984 B，SHA256 `aafd1c671196cb69202efd29617d082a56df98f5b2d024952765e8cb7fd372e5`；保存metadata记录ss_steps2/rank4，576个张量全部有限、192个LoRA up非零。`training/r12-real-training/train-result.json` 与 `artifact-verification.json` 均passed=true；权重由最终受管Python真实重新打开核验。

手测入口已部署为 `F:/NextTrainerLauncherSandbox/manual/启动手测.cmd`。`manual/verified-deployment.json` 为deployed，部署前已核验同EXE/安装器/便携包、安装收据、API任务和权重，并确认所有owned host正常退出、Job排空与CDP回收。旧manual子项按时间戳备份，r12的Python/venv保留原路径。主执行者使用正常CMD打开无CDP启动器窗口，PID155680、预选r12，实际自动完整性检查已完成，基础工具、源码、运行环境、网页资源均已就绪，右上显示“可以启动”，“启动训练器”按钮可用。`manual-normal-window.json` 记录ready-for-manual-test，最终截图为 `manual-normal-window.png`。

实际性能限制：启动时自动完整性检查及正式训练提交前的文件/绑定校验可能持续数分钟，期间相关控件禁用；本次API同步提交约225秒，实际GPU训练约42秒，不作秒启动承诺。

保留边界：本轮真实训练只覆盖Kohya SD1.5两步LoRA；另外三个引擎仅有原约定冒烟，MOSS只核Qwen3.5关键API/meta构造，均没有取得真实模型训练结论。沙盒是当前Windows上的独立目录，沿用本机驱动/WebView2；干净Windows与缺WebView2首装仍blocked/not-run。当前开发候选未转为生产签名或公共发布。test/r8/r9/r10/r11和下方原始失败记录全部保留。

## 返修实现与重跑

- `b9b10d8e` 删除前端预算设置/状态/轮询、后端额度/累计账本/收据、相关CLI/IPC；旧预算文件不再读写和阻止下载。保留资产长度/SHA256、严格Range/ETag续传、取消及正常网络超时。19项下载、1项操作终态、严格Clippy、前端构建及4项工具测试通过。
- 第一新包在空根 `r8` 真实下载至GUI依赖23/81（grpcio）时遇到 `tls handshake eof`，操作已正确写成failed。证据 `native-install-1/`，原现场保留，不能记为安装通过。
- `d2970f68` 增加明确瞬时网络错误的最多两次重试，使用250/500ms可取消退避、共享600秒时限；每次重进原有checkpoint/强ETag/Range验证。取消、普通4xx、元数据/路径/范围/摘要错误不重试。19项下载回归、严格Clippy、fmt通过，见 `network-retry-checks/`。
- `9b7d9960` 删除打包清单静态 `network_budget_bytes`；构建时引擎/GPU结果改为 `not-run-at-build`，实际结果由本报告和外部实测回执说明。`031da595` 同步现有锁摘要到依赖清单；没有升级依赖包版本。
- 最终第3包位于 `F:/NextTrainerLauncherSandbox/build-r8/windows-candidate-3/`，EXE SHA256 `d852d568af098352717195bbfdbbcd491c87b5be40a00bf3f25905bbdbcc4378`，便携ZIP `6622145d8b5287549a69d64d4b85995874ead13849508634c8710e2bf10789fb`，NSIS `7fdc7acaac6efea2847de508d0238f65f47ca6f812fc3c25312a60f26323f991`。构建输入 `031da595c3677693243daa275ed647361035da80`，真实训练器源码 `0d095dc8cb185b4c9e4d6f4971eba26ea3a1b47e`，其余配方/前端身份见包内清单。
- 第2包 `r9` 是中间验证；完整安装成功后运行harness的60秒等待超时，原始总回执为失败，不改写。原生窗口正常关闭、Job排空、CDP回收；外置harness的后续等待已延长。GUI完整性静态扫描约165秒，期间持续读取与CPU增长，不是死锁。
- 第3包虽只清理打包元信息，其EXE哈希仍发生变化，最终验证另从未存在的空根 `r10` 重新真实下载安装，不拿r9缓存代替。`native-install-3/ui-report.json` 已整体 `passed:true`，原生按钮完成冷下载/安装、工具/Python/源码/GUI环境/前端检查、确认无预算文件、实际服务健康、版本API、HTML/JS/CSS、正常停止和再次健康启动；原控制器保留同一窗口，继续正式Kohya安装及训练。未使用备用runtime续验。
- 第3包Kohya真实下载失败：操作 `download-1793338229-155344-1` 在Torch wheel已下载255,995,269 B后终止，报“状态原子替换失败，原状态已保留: 拒绝访问。(os error 5)”。证据 `native-install-3/kohya-install/report.json` 及原始状态/sidecar/截图。该包只证明GUI冷装与服务链，不能称训练可用；正在修复Windows检查点原子替换可靠性，旧现场保留，不手改state或绕过守护。
- `ea79396341cbcc54fd826af2ebcd777173a8cce7` 修复上述问题并已普通push/远端核对：Windows错误5/32/33最多8次、总退避850ms；每次重试重新检查路径及原目标/同一临时文件字节，保持原子替换，不删旧目标。检查点首块立即提交，其后按4MiB/1秒提交；缓冲留内存，同步数据至sidecar提交之间不await，网络断流提交合法缓冲，取消丢弃未落盘缓冲。25项下载回归与3项真实Windows共享句柄回归、fmt/严格Clippy通过，证据 `atomic-checkpoint-checks/`。无法确定现场具体锁持有者，不将杀毒或其他进程当作已证实原因。
- `r10` 失败后控制器已正常关窗，退出码0、Job排空、CDP回收。第4包已构建，并开始用新的 `r11` 空根执行最终同包下载安装/运行/Kohya/训练全链，旧根及失败证据继续保留。第4包EXE `68c5ff5fcfc14dc70d4689e53f8ceb5f085ba7a2461929e5e0f75ed50c19d1d4`，便携ZIP `5c3513f634f33eaa920897b5c841fe4c60c5be9809b4914e8bd8dd8f22469016`，NSIS `fb83fe42bc291073330da035d73ca1c4a017763646ceb7be500e73bf2121dd1b`；构建输入为上述 `ea793963`，配方/训练器源码/前端身份未变。
- 第4包 `native-install-4/ui-report.json` 已整体 `passed:true`：r11空根实际下载并安装、五项核心组件、无预算文件、真实GUI健康、版本API/HTML/JS/CSS、正常停止和再次启动全部通过。同一原生会话继续执行Kohya安装，控制器等待训练结束，暂未交付用户。
- 同第4包 `r11` 的Kohya完整下载安装成功，Torch实际下载3,338,322,003 B并校验后发布；实例 `t6e6958eb2202491`、操作 `download-1793339797-164680-1` succeeded、完整实例收据落盘。受管解释器 `F:/NextTrainerLauncherSandbox/r11/e/t6e6958eb2202491/Scripts/python.exe`。
- 安装结束自动GUI刷新与独立检查共享Engine锁，期间UI曾提示busy；已有请求完成后真实UI独立检查成功。外置harness600秒等待先截止，原 `kohya-install/report.json` 顶层失败保留；不重装、不反复扫描，通过 `kohya-probe-continuation/report.json` 明确继承实际操作/收据及真实UI结果，并继续产品imports和CUDA。续验报告 `passed:true`：torch/transformers/diffusers/accelerate全部ready；该独立Python在RTX4060Ti真实执行4×4 CUDA矩阵，sum3680，Torch2.7.0+cu128/CUDA12.8。没有发现永久锁泄漏或中毒，超时不会取消后端扫描的事实如实保留；检查耗时较长为当前体验限制。
- `gui-ready-for-training.json` passed：同窗口再次启动GUI，running/healthy均true、port5057、实际版本API/网页200。训练代理确认任务列表为空、旧目标权重不存在后，已正式向 `http://127.0.0.1:5057/api/run` 提交两步训练；结果待 `training/r11-real-training/` 原始回执，不以提交成功代替训练成功。
- 第4包真实训练任务 `eac343bc-a11b-4508-b4ab-afcc699783a7` FAILED、returncode1。命令确实使用受管Kohya解释器；训练代码 `scripts/stable/library/lpw_stable_diffusion.py:12` 导入当前固定Transformers5.17.0已移除的 `CLIPFeatureExtractor`，在优化器开始前失败，无新合格权重。原始 `training/r11-real-training/train-result.json` 为 `passed:false`、日志保留。`/api/run` 两轮同步检查耗时约201秒；下载/安装/导入/CUDA通过不能证明训练兼容。正在核对源码要求并修复Kohya固定依赖闭包，先用外置独立环境验证同类兼容问题，再重建正式配方/包及从零实际训练。
- 直接使用vendor入口的独立诊断还复现了Transformers5.17移除CLIP `text_model` 包装引起的checkpoint键不匹配，记录 `training/r11-vendor-probe/`。最终最小修复保留原stable入口：Transformers固定5.5.3、tokenizers固定0.22.2，stable/SDXL两处导入使用CLIPImageProcessor别名；其余120wheel和MOSS新栈保持。122wheel/214条活跃依赖闭包、pip check、CLIP真实前向及旧层级、Qwen3.5固定配置meta构造、32项既有回归均通过，不声称MOSS已实训。
- 外置独立候选 `training/kohya-553-stable-probe/` 已真正完成同等2步GPU训练及读权重：rc0、loss0.00355→0.0125、ss_steps2、576张量有限、192个LoRA up非零；权重3,476,992 B，SHA256 `171b135b1788ced1de258af5c7fad7e8a32b6b97bba2cbd5c36d8fa284a19646`，峰值4047MiB/75%、退出后无残留训练进程。该回执明确diagnostic_only，不能替代正式新包/API验收。
- 上述5文件最小修复已保存并push为新正式源码 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`，远端完整SHA核对通过。此后完成GUI/Kohya source闭包、两wheel固定锁、父身份/签名冻结并保存到 `dfc70369`，生成第5包，在新空根r12完成上列正式安装和API训练。r11控制器已正常关闭、Job排空/CDP回收，原失败保留。
