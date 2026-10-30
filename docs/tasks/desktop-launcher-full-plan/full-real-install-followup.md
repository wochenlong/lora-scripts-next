# CR-008 实际安装失败返修与真实训练冒烟

当前状态：in progress。用户手测失败，要求执行者先完成完整下载安装与训练冒烟，并彻底删除下载预算。工作副本 `E:/OpenSourceTeamWork/workspace/branches/dev`，分支 `feat/desktop-launcher`，返修前HEAD `b2340e65f61b0426d5474852ec8c9f4861157df3`。

证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/full-real-20261030/`。既有手测根 `F:/NextTrainerLauncherSandbox/test` 失败现场保留，新的真实验证使用独立短根，不用旧缓存冒充从零下载安装。

| 要求 | 执行/验证 | 状态 |
| --- | --- | --- |
| 定位用户实际失败 | 原生窗口截图、state/operation/partial元数据；下载账本写入不确定错误 | 已定位并留证 |
| 删除下载预算 | 前端UI/状态/类型、后端账本/限额/CLI/IPC移除，旧账本不再读取 | 实现完成；19项下载+1项终态回归、严格Clippy、前端构建和4项工具测试通过 |
| 完整下载安装 | 新EXE，空工作区，真实下载源码/工具/Python/wheel并完成环境检查 | pending |
| 真实服务可用 | 主程序启动、版本API、前端HTML/JS/CSS、正常停止/重启 | pending |
| 真实训练冒烟 | Kohya SD1.5 LoRA，公开许可固定4.26GB底模、两张合成512图、2步真实梯度更新，权重落盘与读取 | 模型实际下载与数据准备中 |
| 同版交付 | 新安装器/便携包、已安装可操作沙盒、精确提交/push/远端SHA | pending |

已有记录：用户窗口报“下载计账写入结果不确定，停止读取；释放session后持租约重新核对”；源码partial 12,845,837 B，磁盘operation仍running。上次仅完成源码预取和界面就绪，不能证明本次完整安装或训练可用。

方法采用实际故障回归与用户流程验收，沿用既有任务书，不创建重复规划体系；结果逐项区分pass/fail/not-run/资源限制，不以静态构建或夹具代替真实训练。
