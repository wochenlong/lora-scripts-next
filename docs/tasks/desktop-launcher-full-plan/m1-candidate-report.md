# M1-CANDIDATE：GUI 候选包与实测报告

**候选未通过。** 按 v0.5 / CR-004 + CR-003 已用完两轮候选：当前同包 C1 安装、C2 启停、C3 精准修复通过，C4 登记恢复在只读预览被产品拒绝。未确认恢复、未执行登记探针。保留失败与原件，停止修包和续验，提交成本审核后暂停。M1 `in progress`、M2–M6 `pending`，不签 EXIT-M1，不代表完整 #516 完成。唯一进度见[总控目标索引](00_总控目标索引.md)。

四引擎功能仍待后续实现；用户已要求独立检查/修复仅轻量冒烟，实际引擎安装/损坏修复、GPU/模型/训练/权重项 `skip + CR-004`。本包只验 GUI 核心链，其他验证按影响面精简，不扩展完整故障矩阵。

## 当前冻结包

- EXE：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/M1/operations/candidate-round2-20261029/next-trainer-launcher.exe`。
- SHA256：`663faa6f690418ae5faeda8327e6419cab7831049a4e7d333ddefb129cc7f895`；23,153,152 B。
- 启动器构建源码：`e7d26bac9c2f2f2961d5d0f05b094f32fd9c5c0a`，已普通 push 到 `origin/feat/desktop-launcher` 并以 `ls-remote` 核同一完整 SHA。后续仅报告/状态提交不改变本包。
- 训练器源码：`196ff12c16083d59c8be6711476c6fdb70c7112a`，dev `3.3.1-dev`；GUI recipe `gui-cp310-win-x64-v1`。
- 完整身份及构建/推送回执：本 run 的 `M1/operations/candidate-round2-20261029/freeze.json` 与 `freeze-push-receipt.json`。

| 固定资产 | SHA256 |
| --- | --- |
| Catalog | `87d6901dd755d4fdd7b87d318f9d48b4cd1a60fc3f45cd516319036255a1586f` |
| GUI recipe | `8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090` |
| 安装文件索引 v2 | `6ef8a9b844b1dd7e9294be5ae30b70420e703127fc0d999a7eb8096c114ffd90` |
| 受管解释器模板 v1 | `066edf2fc67450fcb57dfaecf7ca34b379ef610d33a26ad50f20997eb7b7967a` |
| 固定训练器前端 ZIP | `3c97a03bc4554248936ee4cbba6bb3f12bc413aecbbac9633400986da6801da1` |

## K1–K2：修复、来源与检查

固定 uv 0.11.16、原归档验证的 CPython 3.10.19/build 20260211 和 81 wheels 在独立目录复现正式命令。alias/patch 两输入均生成 minor alias 输出；16 控制文件、27 入口、12,738 原文件、81 RECORD 和完整闭包匹配，无未知或缺失，base 前后不变。环境根只允许可选 0 B 普通 `.lock`；pyvenv 精确五键与已验证同根 alias 绑定；两个 Python 包装程序按固定来源模板整文件重建，旧 patch 模式只保留原 v2 复制 EXE 合同。来源不取自待恢复树。

第一轮定位到 Windows 路径片段内正斜杠保留，使配置与两 Python PE 各有一个字节不等。第二轮仅按组件拼接同一受管路径；独立原始 cfg/PE 回归先复现拒绝、修复后通过，未扩大信任或未知模式。

验证复用：第一轮全量 Rust 184 passed/0 failed/3 ignored、fmt、严格 all-targets Clippy、前端类型检查/构建及 locked/offline release 通过。第二轮仅 Rust 登记路径变化，登记模块 10 项、fmt、严格 Clippy、locked/offline release 通过；未改动的全量/前端检查复用原结果，不重复运行。3 个 ignored 为两项仅父测试调用的子进程 helper 和显式大于 1 GiB 文件案，不计新增能力通过。文档静态检查 44 产物/350 本地链接通过，仅证明结构。

来源摘要入口 `M1/recipe/gui-registration-working/k1-final-control-comparison.json`（SHA256 `c481c27478c2cc0683dcb1e87930b25da147f16b200f939554c35116af5a0cb3`）；K1 与路径最小修复均已定向独审，无许可范围扩大。

## K3：当前同包结果

| ID | 场景 | 第二轮结果 | 证据与边界 |
| --- | --- | --- | --- |
| C1 | 中文空格新根，从原资产实际创建工具/源码/Python/GUI 环境 | pass | 初段因测试监控枚举临时文件中断，原 false 保留；同 EXE 由正式 UI 补全，新实例 `g2bda43203d5cba83` generation/validated=1、dirty=false，原取消实例保留 |
| C2 | 原生启动、版本 API、首页与 JS/CSS、停止退出 | pass | 实际版本语义与当前发布一致，首页及引用 JS/CSS 逐字节相等，所属进程/监听回收，资料哨兵和非目标树保持 |
| C3 | 精确单包损坏、原生预览确认、精准修复与复启 | pass | 独立 toml wheel 闭包与 UI 清单一致，确认后仅目标包修复，损坏快照/代次同步/资料与非目标保护及复启均过 |
| C4 | 无缓存/缺登记的独立验证与恢复 | fail，产品只读阻断 | 显式选中本次实例后返回 `uv控制或入口内容不符：Scripts\\cffi-gen-src.exe`、plan=null；未确认恢复，隐藏原记录/cache 保留 |
| C5 | 包身份、中文步骤、WIP 与远端回执 | 材料已齐，最终保存回执见下文 | 构建源码已远端确认；审核材料保存后由外部回执核最终提交。C5 保存不改变 C4 fail |

实际安装根：`F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/M1/候选 二`。初始根不存在；原生 UI 保存额度后由产品建立 marker，仅复制经 size/SHA 校验的 84 个原归档，473,373,643 B；禁止复制成品源码、venv、profile。全程拒绝上游，不能称新联网安装；宿主已有 WebView2，不能称干净 OS。

第二轮证据由 `candidate-round2-20261029/` 与同 EXE 正式补全续段 `candidate-round2-resume-20261029/` 共同构成。续段 1032.821 秒、累计约 1082.646 秒，上游计量 0 B，最后监控 F 约 3.40 GB/E 约 99.1 MB，均在 1800 秒/5 GiB/256 MiB 上限内。重复 verified 大字典按 SHA 引用，内存完整保护断言不减。UI 28 条检查中 27 条通过，不能用数量覆盖 C4 的失败。

最终续段原回执 `receipt.json` SHA256 `c83fa79388ac1f661581dc3e339de8daf79f0c84dda4d2a928247570637f94d7`；UI 报告 SHA256 `43504399e3c2b8ac16a8c4a958df2a06de20f1c7400dbb891391601e11a2087c`；只读登记预览 SHA256 `aba1e9728493bb455a99fe0a96cb52a99a6af71772c514c8cf66cc56fd661ca1`。WM_CLOSE 主进程退出 0、CDP 关闭；两个延迟 WebView 子进程按 PID+创建时间核验后回收，最终无所属残留，不将强制回收算正常退出全通过。计量器线程/socket/request/保留均为 0；4 次请求本地拒绝、上游 0 B。

失败后只读补证 `failure-readonly-postverification-receipt.json` SHA256 `62213f3a69e818fad3d802ae247ef2b8b600f8eaf442a9df06df39297380c578`，20 项核对全部通过，覆盖 9 组保护树、隐藏三登记与完整缓存、非目标 state、旧取消实例、marker/EXE、原失败回执和进程/监听/计量器。只读补证通过不改变原候选失败。隐藏原件仍在 `F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/M1/candidate-round2-resume-20261029/hidden-originals`，未恢复覆盖。唯一账本累计仍为 1,013,413,437 B，SHA256 `8b4f412b374beacdff507ccf602a3657381dec822f463911ef33aee136551e21`；同目录 `ledger-append-receipt.json` 保存先备份后去重追加 0 B 的回执。

明确阻塞：命令入口 PE 重建的字节合同仍需关闭，首次拒绝项为 `cffi-gen-src.exe`。代码仍以 `environment.join("Scripts/python.exe")` 构造入口解释器路径，存在与已修基础路径相同的分隔符风险；这是静态线索，尚未继续做原始入口字节归因或修改。下批应一次核全 27 入口后作最小修复，不逐文件试包。本轮停止于 2/2，不继续第三轮。

## 中文操作步骤与能力边界

以下是本候选的操作流程；实际通过状态只以 C1–C5 表及收据为准。

1. 在已有 WebView2 的 Windows x64 上打开冻结 EXE。试用时选新的短绝对路径，例如 `F:\Next Trainer 试用`，点击“检查”；不要使用开发仓库或测试证据目录。
2. 在“环境管理 → 下载额度与计账”保存自己接受的有限额度。联网新装可按本 GUI 配方预留额度；网络设置可选择自动、系统、手动代理或直连，设置只影响当前安装目录。验收采用 1,000 B 产品额度和拒绝上游的测试代理，所有 84 份固定原资产缓存均单独校验后预置；该缓存安排是明确的测试边界。
3. 到“版本管理”，找到 dev `3.3.1-dev / 196ff12c`，点击“下载安装”，等待操作完成，再点顶部“检查”刷新当前安装状态。操作终态后的后台状态刷新可能较慢，忙碌标识结束不代表页面已刷新；本轮保留该时序限制。运行环境由正式安装命令在最终路径创建；模型、Torch 和四训练引擎不包含在此步骤。
4. 到“启动”点击“启动训练器”，显示服务就绪后打开本机网页。使用完点击“停止”，再关闭启动器。
5. 依赖异常时，在“环境管理”点击“只读诊断依赖”；对报告的固定包点击“查看修复清单”，审查路径后依次点击“审查并确认修复此包”和确认对话框中的“确认修复此包”。本轮验收只对合成安装实际损坏一个 toml 原文件，不要求试用者手工破坏安装。
6. 当前包的登记恢复未通过，登记意外丢失时仅使用“恢复安装登记 → 只读检查登记”查看状态并保留现场，不把本包当作已验证的登记恢复工具。存在多个实例时应明确选择目标；不要为了试用自行删除登记或缓存。本轮失败现场须原样保留，不能作为正常试用目录。

显式重建/同发布实例回退/旧 pending 扩展保持草稿，`deferred by CR-003`。旧基线已有的普通版本选择/回退不能代表这些待开发能力通过。


本包未重新验证新联网下载、main 发布线、源码/基础 Python 修复、完整中断/磁盘故障矩阵或干净系统；这些旧包结果只能作历史。四引擎适配、可信远端更新、真实资料迁移、独立壳升级与正式分发尚待实施/审核。正常服务可合法写合成 profile，修复/恢复的资料原字节比较在服务启动前完成，独立哨兵始终核对。

## 历史失败保留与审核停止点

- CR-003 前两案分别因空 `.lock` 与旧 pyvenv/PE 规则拒绝，原 false、隐藏原登记/cache 与日志保留，不倒填成功。
- 第一冻结轮 `ac862fe5…671d6b`：C1/C2/C3 通过、C4 只读因分隔符阻断；1165.333 秒/0 B。初段 UI 等待失败及续段回执均保留。集中诊断全部 43 项在原生分隔符规则下匹配，原保护树及隐藏原件未变。
- 第二轮初段 `receipt.json` SHA256 `ca41bba319a67658128cf8c5d9292252ed2de81a78037eba1fdb2279972ac199`：49.825 秒，预算监控 lstat 遇 uv 正常移走的临时文件，正式 WM_CLOSE 取消安装，未作产品失败结论。两延迟 WebView 子进程按身份回收，最终无残留；该回执仍 false。只读 helper 的 266 UTF-16 路径单项检查也保留 false，以完整 long-path 树及原件摘要另行补证，不篡改历史。

当前结论固定为“候选未通过”，可供审核的包已保存，验证通过的能力限定为 C1–C3；登记恢复尚不可交付。按 CR-003 提交[剩余工作与成本审核表](remaining-work-cost-review.md)后暂停；M1 不退出，不进入 M2，不把整体 Goal 标 complete。最终文档保存回执将写入 `M1/operations/candidate-round2-resume-20261029/delivery-save-receipt.json`，以其中的普通 push/远端完整 SHA 为准。
