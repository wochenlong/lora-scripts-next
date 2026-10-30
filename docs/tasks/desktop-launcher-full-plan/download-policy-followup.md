# CR-007 下载设置简化与补丁交付

2026-10-30，用户明确要求“立即修改”。原首次联网前设置有限累计额度是实施中增加的产品前置，现取消；新工作区默认允许下载，累计上限默认关闭，环境页默认收起“高级：下载用量与限制”。当前状态：in progress。

| 本次要求 | 实现与验证 | 状态 |
| --- | --- | --- |
| 无需设置额度即可下载 | 首次远程制品请求自动创建 null 上限账本；回环 HTTP 和新 EXE 原生预取 | 回环 HTTP 通过，原生待新包 |
| 可主动开启/关闭累计上限 | IPC 接受数字或 null，CLI 接受数字或 off；保留累计用量与 receipt，旧策略按原值读取 | 后端定向回归通过 |
| 普通安装界面去掉设置前置 | 删除启动/版本页强制提示，高级默认折叠，关闭状态不要求填写数字 | 前端构建及现有工具测试 4/4 通过 |
| 新安装器与便携包可供实测 | 使用同一源码生成 NSIS/ZIP，记录 EXE、helper 和制品摘要 | 待构建及原生冒烟 |
| 保存开发基线 | 精确提交本功能文件，普通 push 后核远端 SHA | 待验证后保存 |

本次为既有功能的有界修正。沿用 CR-004/006 的精简测试口径；不重跑四引擎、GPU、干净 Windows 或旧 M6 全矩阵。原资料/签名/长度摘要/单操作限制和账本损坏拒绝继续有效，开发资源预算单独适用。旧包和历史结果保留，新包的验证范围在下方单列。

证据目录：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/desktop-launcher-full-20261028-155831Z-f6c00a/changes/CR-007/`。

已完成快速检查：`download_budget` 18 passed / 1 ignored helper / 0 failed，`artifact_downloads::tests` 2 passed / 0 failed；前端 `npm run build` 和现有下载设置工具测试 4/4 通过；严格 `cargo clippy --locked --offline --all-targets -- -D warnings` 通过，`git diff --check` 通过。单个忽略项为父故障测试按精确参数另行启动的 helper，父测试已通过。
