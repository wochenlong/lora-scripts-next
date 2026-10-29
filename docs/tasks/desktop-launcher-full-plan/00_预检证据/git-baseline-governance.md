# 每阶段开发基线保存协议

版本 v0.6 / 2026-10-29 / [CR-006](change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)。用户已要求每阶段 push 保存基线并连续施工。一次阶段提交、普通 push 和远端核对即可，不强制代码 C/状态 S 双重推送，不为写入自身 SHA 循环制造提交；原 C/S 历史回执仍有效。

本次侧聊仅修订文档，不实际暂存、commit、push 或修改 Git 配置。

## 1. 唯一目标与保护

- 工作副本：`E:/OpenSourceTeamWork/workspace/branches/dev`；分支：`feat/desktop-launcher`；远端应为 `origin=https://github.com/wochenlong/lora-scripts-next.git`。写前重新核实实际路径/branch/remote/status/index。
- 只向 `refs/heads/feat/desktop-launcher` 普通 push，不向 dev/main 写入、不 force、不改写已推送历史、不自动合并/公共发布/向他人发消息。
- 按精确 allowlist 暂存本功能代码、锁文件和必要脱敏文档；不 `git add -A` 或 `git add .`。保护无关 dirty/untracked 和原有 index，不 reset/clean/覆盖工作树。
- 构建产物、node_modules、venv、真实 profile、模型/缓存/数据集、VM 磁盘、凭据和大日志不入 Git；制品在独立目录保存，记录哈希/大小/来源。

## 2. 一次阶段保存后自动继续

1. M1–M5 完成本阶段功能和必要快速检查，更新总控及简短阶段记录：施工完成、`final_validation=pending M6`、baseline 待远端核对。综合实测不作为中间保存前置。
2. 核分支、远端、工作树及 index 归属，精确暂存并检查 cached diff 与 `git diff --cached --check`；源码/凭据/许可/大文件检查合并到本次审查，不额外多轮停工。
3. 一次提交保存代码及必要状态，得到完整提交 SHA。只在确有代码/文档变化时提交；已有提交可复用，不生成空提交凑阶段数。
4. 查询远端分支，普通 push 后再 `ls-remote`，确认远端 SHA 等于待保存 HEAD。存在未知远端更新先 fetch 并判断关系，禁止 force 覆盖。
5. 外部保存 `M<n>/baseline-final.json`：阶段、分支、完整本地/远端 SHA、时间、push/核验退出码和必要报告位置。仓库内先存提交前可知状态，回执存外部；后续阶段可顺带写回上一阶段摘要，无须再做一次状态提交。
6. 保存成功自动进入下一阶段，中间只给简短进度；全部施工后统一做 M6 验证和最终报告。最终回执确认可记录于外部报告，不为最后 SHA 反复提交。

WIP/候选源码提交允许按需存在，但不要求每 Phase 保存或冻结独立候选；不能把 WIP 标为施工完成。普通网络/预检失败自主排查，不因自设两次尝试就请求审批。网络暂时不可用时保留本地提交与 baseline 待补状态，继续独立施工；最终交付前补推/核验，仍失败则如实列出未保存项，不声称阶段远端完成。

## 3. 网络命令

GitHub 网络操作逐命令使用本环境代理，不改全局配置。以下为未来执行示例，本次文档修订不执行：

```text
git status --short --untracked-files=all
git branch --show-current
git remote -v
git diff --cached --check
git rev-parse HEAD
git -c http.proxy=http://127.0.0.1:11809 -c https.proxy=http://127.0.0.1:11809 ls-remote origin refs/heads/feat/desktop-launcher
git -c http.proxy=http://127.0.0.1:11809 -c https.proxy=http://127.0.0.1:11809 push -u origin HEAD:refs/heads/feat/desktop-launcher
git -c http.proxy=http://127.0.0.1:11809 -c https.proxy=http://127.0.0.1:11809 ls-remote origin refs/heads/feat/desktop-launcher
```

每条命令检查实际结果后再继续，不串成忽略失败的脚本。认证不足时只诊断最小缺失权限，不导出 token/换身份；非快进保留本地及他人成果，正常整合并做最少受影响检查；钩子失败修真实原因，不绕过必要检查。无关原有暂存内容不能夹带；必要时隔离本功能保存，不清除他人 index。

## 4. 源码、构建和最终包身份

worker/引擎/资料逻辑必须进入实际安装的训练器归档。按需先保存源码提交，锁定归档和编译前端摘要，再生成启动器 catalog/recipe；不能安装旧 main/dev 后用开发工作树 overlay 证明新功能。

`trainer_source_commit / launcher_build_commit / package_sha256 / final_remote_commit` 分别记录，可有不同身份；最终文档提交不代表重建了包。只因状态文档变化无需重建产品。M6 修复确实改包时才生成新 SHA，复验受影响链，最终统一交付真实远端回执与包摘要。
