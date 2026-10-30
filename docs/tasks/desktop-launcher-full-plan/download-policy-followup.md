# CR-007 下载设置简化与补丁交付

2026-10-30，用户明确要求“立即修改”。原首次联网前设置有限累计额度是实施中增加的产品前置，现取消；新工作区默认允许下载，累计上限默认关闭，环境页默认收起“高级：下载用量与限制”。当前状态：done；实现、定向验证、新包构建与原生冒烟完成。

| 本次要求 | 实现与验证 | 状态 |
| --- | --- | --- |
| 无需设置额度即可下载 | 首次远程制品请求自动创建 null 上限账本；回环 HTTP 和新 EXE 原生预取 | 通过；新根实际下载 57,257,800 B |
| 可主动开启/关闭累计上限 | IPC 接受数字或 null，CLI 接受数字或 off；保留累计用量与 receipt，旧策略按原值读取 | 后端定向回归通过 |
| 普通安装界面去掉设置前置 | 删除启动/版本页强制提示，高级默认折叠，关闭状态不要求填写数字 | 前端构建及现有工具测试 4/4 通过 |
| 新安装器与便携包可供实测 | 使用同一源码生成 NSIS/ZIP，记录 EXE、helper 和制品摘要 | 构建通过，新 EXE 原生 13 项通过 |
| 保存开发基线 | 精确提交本功能文件，普通 push 后核远端 SHA | 实现提交 3d892c86；最终保存回执见下方 |

本次为既有功能的有界修正。沿用 CR-004/006 的精简测试口径；不重跑四引擎、GPU、干净 Windows 或旧 M6 全矩阵。原资料/签名/长度摘要/单操作限制和账本损坏拒绝继续有效，开发资源预算单独适用。旧包和历史结果保留，新包的验证范围在下方单列。

证据目录：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/changes/CR-007/`。

已完成快速检查：`download_budget` 18 passed / 1 ignored helper / 0 failed，`artifact_downloads::tests` 2 passed / 0 failed；前端 `npm run build` 和现有下载设置工具测试 4/4 通过；严格 `cargo clippy --locked --offline --all-targets -- -D warnings` 通过，`git diff --check` 通过。单个忽略项为父故障测试按精确参数另行启动的 helper，父测试已通过。

新 EXE 的 CLI 4 项通过：只读查询不创建目录、off new、开启数字上限、off revision。原生普通会话在独立新根 `F:/NextTrainerLauncherSandbox/o2` 完成 13 项检查：无强制设置提示、高级区默认折叠、未设置额度即可实际预取 dev 源码、按清单核长度/摘要；上限 null→1 GiB→null，策略 revision 1→2→3，非零计数与原收据保持；正常关闭退出 0，Job、CDP、计量线程/socket 全回收。外部 CONNECT/TLS socket 实测 58,208,192 B，正文计数 57,257,800 B、1 请求、0 重试，两个口径不重复相加。

首轮原生脚本因“安装目录”同时匹配 region/input 而失败，发生在下载前、网络 0 B。原失败保留 `followup/optional-default-20261030/run-20261030-002731Z/`；仅修正仓库外定位器后，同一新 EXE 换独立根通过，不回写首次失败。成功证据由 `changes/CR-007/native-result.json` 索引到 `run-20261030-002801Z/`，CLI 为 `cli-result.json`，构建为 `build-result.json`。

新包输出：`F:/NextTrainerLauncherSandbox/desktop-launcher-full-20261028-155831Z-f6c00a/followup/optional-default-20261030/windows-candidate-1/`。启动器以已提交 `3d892c86d2041662786184bca4370613ed50732e`、受控范围无脏文件构建；训练器固定源码仍为 `0d095dc8cb185b4c9e4d6f4971eba26ea3a1b47e`。构建无新增网络下载。

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| `NextTrainerLauncher-0.2.0-windows-x64-portable.zip` | 17,569,737 | `bb673f53a68542e9c6a82989ba031d3613a390d87b85fed776a48d4f31af6522` |
| `installers/Next Trainer Launcher_0.2.0_x64-setup.exe` | 14,192,464 | `f15c2f5b0109159446623df27dc64e81bcce1cd931b1d6a4516b80104f513c3d` |
| `NextTrainerLauncher-0.2.0-windows-x64/next-trainer-launcher.exe` | 35,830,784 | `1adedc7605a48399545e8ea93caf23266b5ad78afd99eb5044aeef30b1ffe770` |

独立 helper SHA256 为 `d71390cea30cc16e8d17f749aea16241431119bcc5bbf42a5b0c9f5adfa16054`，外层 delivery manifest SHA256 为 `7bfdb28002573e63121172cf56ccff3be1b05ad7ec41cdab4aacf6f958c89a45`。本次未重跑完整主环境安装、NSIS 安装/卸载、四引擎、干净 Windows/WebView2、GPU 或旧 M6 全矩阵；旧结果仅按原包边界引用，开发候选不作为生产公开发布。

普通 push 与远端完整 SHA 保存于本 run 的 `changes/CR-007/git-baseline.json`；无关未跟踪文件保留，不进入本功能提交。
