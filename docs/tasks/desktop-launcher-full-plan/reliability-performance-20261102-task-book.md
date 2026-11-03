# 启动器可靠性修复快速任务书

## 计划元数据

- Plan ID：`desktop-launcher-reliability-20261102`；版本：`0.32-quick`；更新：2026-11-04。
- 用户授权：简要快速任务书，测试与验收只做针对性测试，整理后继续执行。
- 当前阶段：Q1–Q3已完成；执行状态：`completed`。
- 总进度：[总控目标索引](00_总控目标索引.md)；本文件为现行任务书；结果见[快速实测报告](reliability-quick-20261104-report.md)。
- 分支：`feat/desktop-launcher`；仓库：`E:/OpenSourceTeamWork/workspace/branches/dev`。
- 旧任务书保留于[历史归档](archive/reliability-performance-20261102-task-book-v030-history.md)，仅供追溯。

## 目标与范围

解决修复预览失败、检查缺少进度与取消、重装准备反馈和服务启停按钮刷新问题，交付可运行候选包、关键截图与简明报告。

不开启真实训练，不下载或加载训练模型，不修改驱动，不恢复下载预算，不改动用户原有资料。
四个训练引擎按用户要求仅做入口、进度、取消与回收冒烟。完整Rust、42 CASE、四引擎完整扫描/重建矩阵及历史全量验收均不作为本次交付前置。
每次修复只补受影响验证；保留原失败结果。candidate12的预览/实际修复/续办证据复用，candidate13补服务启停、版本切换与四引擎冒烟。

## 三个执行阶段

| 阶段 | 工作与完成标准 | 针对性验证 | 状态 |
| --- | --- | --- | --- |
| Q1 修复收口与出包 | 修复Windows路径、计划版本兼容和停止后版本按钮误禁；形成可运行便携包 | 定向Rust 10项、fmt、严格Clippy；前端类型检查、正式离线构建、源码/程序/便携包校验 | done |
| Q2 针对性沙盒验收 | 复验预览、实际修复/取消/续办、启停与版本切换；四引擎入口/取消冒烟 | 真实打包WebView点击；HTML/API、按钮时延、任务终态、进程回收及用户资料保护 | done |
| Q3 基线保存与交付 | 更新简明报告，精准commit/push，交付包与证据入口 | diff检查、远端SHA核对；保留无关dirty/untracked | done |

## 事实与决策

- Windows路径逐分量构造后，原误拒已解除；前端接受现有schema1/2，原身份和摘要校验保留。
- 停止后异步读取轻量安装信息，清除只验证当前版本的旧启动报告；不触发完整环境扫描，不延迟首页按钮。
- candidate13实际服务启动约9.69秒，ready后5ms启用打开网页按钮；停止后21ms恢复启动按钮，随后正常切回dev。
- 四引擎均响应检查入口并取消至`cancelled`，回收标志通过且无残留；AI Toolkit在运行中取消，其余三个在排队阶段取消。完整扫描按快速范围停止。
- 退出后120个资料文件逐字节保持；除实际版本选择/健康记录所在的registry外，控制文件均保持。启动器自然退出、Job排空、服务和调试端口回收通过。
- 旧套件长扫描超过工具1024条进度记录上限，且完整扫描已按快速范围取消；其原`fail`保留；本次快速范围结论以独立`quick-scope-review.json`和四引擎冒烟原件为准。
- 两次完整Rust超时、旧文案断言失败和旧取消阶段归因缺口保留。未测项见报告；不将快速结果外推为全量通过。

## 关键制品与环境

- `<run>`：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`。
- `<sandbox>`：`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z`。
- 当前包：`<sandbox>/build-R2-13/NextTrainerLauncher-0.2.0-windows-x64-portable.zip`。
- EXE SHA256：`5c0e6015e335c0f27092acb0b660da9ac67674132c23510e15bfe0eda417abfe`。
- 构建/冻结：`<run>/R2/build-13/execution.json`、`candidate-freeze-13/admission.json`；175个源码输入与便携包程序一致。
- 最终定向证据：`<run>/R2/legacy-v9-targeted-candidate13-01/`；工具续接：`R2/execution-resume-20261103-08/`。
- Git保存回执：`<run>/R2/quick-final-git.json`；网络Git逐命令使用代理`127.0.0.1:11809`。

## 进度与后续

Q1、Q2、Q3已完成。当前快速范围没有待修复的已知阻塞；完整扫描、破坏性恢复矩阵、外部浏览器按钮实际点击和真实训练保留为未测。

下一动作：使用已交付candidate13；后续新问题按具体复现单独修复与回归，不自动恢复历史全量测试任务。
