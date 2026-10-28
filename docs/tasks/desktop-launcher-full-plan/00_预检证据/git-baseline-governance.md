# 每阶段开发基线保存协议

适用 `EXIT-M0`–`EXIT-M6`。用户要求每阶段push保存基线，并已于2026-10-28在审计稿交付后指令建立Goal开始执行。当前M0进行中；阶段内常规提交与本功能分支push不再重复询问许可。阶段内WIP提交不代表完成门通过。

## 1. 唯一目标与保护

- 工作副本：`E:/OpenSourceTeamWork/workspace/branches/dev`；分支：`feat/desktop-launcher`。
- 远端应为 `origin=https://github.com/wochenlong/lora-scripts-next.git`。每次写操作前重新核对，不能凭目录名判断分支。
- 只向 `refs/heads/feat/desktop-launcher` 普通push；不向dev/main写入，不force push，不改写已推送历史，不自动合并/发布/发issue消息。
- 保留不相关的dirty/untracked文件和用户原有暂存内容。不可`git reset --hard`、`git clean`或为干净状态覆盖工作树；在M0保存范围/哈希快照。旧底座计划保持历史完成状态。
- M0按精确文件清单接纳`desktop-launcher/`、Python资料接口、9个已接入入口及相关测试/说明/本次计划等。先逐文件检查源码/密钥/许可/大文件，再形成`M0/source-allowlist.txt`；不能用`git add -A`或`git add .`把其他功能设计文档混入。
- 构建目录、node_modules、venv、真实profile、缓存/权重/数据集、VM磁盘、原始带凭据日志不进Git；普通Git只保存代码、锁文件、脱敏必要报告和证据摘要。合法需要分发的大制品保存在独立制品目录，commit中记录SHA/大小/相对清单，不引入Git LFS外部写入。

## 2. 阶段完成到远端确认

1. 先完成阶段所有规定验证、失败修复、独立复审和完成/清理报告；必测not-run或未关闭P0/P1不能提交成“完成基线”。可保存明确标注WIP的恢复提交，但它不解锁下一阶段。
2. 核对branch/remote/status/暂存区与上一阶段哈希快照。按阶段allowlist精确暂存，审查`git diff --cached --stat`与完整diff，运行`git diff --cached --check`。检查原有无关内容没有混入或丢失。
3. 总控表先写“阶段验证已过，远端确认待执行”，状态`in progress`；完成报告区分产品验证与baseline状态。提交阶段代码、必要说明、锁文件、脱敏报告索引，得到完整阶段提交`C`。提交建议`feat(launcher): complete M1 reliable install and repair`，实际信息与阶段匹配。
4. 通过代理查询远端分支完整SHA。首次分支允许查询为空；已有分支若与上次确认不同，先fetch并判断关系。不能跳过未知远端更新，也不能force覆盖。
5. 普通push阶段提交`C`；退出码0之后再用`ls-remote`核对远端SHA等于当前本地HEAD。任何一个不满足都不叫push通过。
6. 保存脱敏回执`<run-id>/M<n>/baseline-code.json`：阶段、repo/branch、UTC及本地时区时间、C、push退出码、前后远端完整SHA、ls-remote退出码、相关报告摘要。回执不含凭据。
7. 确认`C`在远端后，把本阶段验证与C的远端确认结果写回唯一总控进度、完成报告和manifest索引；以独立小型文档提交`S`保存这些状态，再普通push并核对S。全部确认后阶段才是`done`，下一阶段才能开始。
8. `S`自己的完整SHA及最后远端原始结果保存在仓库外`baseline-final.json`，避免在同一提交内嵌自身SHA的循环。后续阶段可将前一回执脱敏摘要镜像入库；最终交付报告引用仓库外回执。无需为写入S自身哈希无限生成状态提交。

S推送失败时立即将本地总控/完成门改回`in progress`或`blocked`，说明“代码C已在远端，状态S未确认”；修复后重试普通push并重新核对。不能在最终报告引用S为已远端保存。任何时点都保留可续接的本地事实。

## 3. 已核对的Git命令形式

以下在项目工作副本执行；阶段ID和allowlist由实际阶段提供。网络流量遵循本环境 `git-proxy-push` 技能，每条命令显式代理，不写全局配置。

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

精确暂存优先使用明确路径列表；需要读取清单时使用Git支持的NUL分隔pathspec文件，避免中文/空格或通配符误匹配。不可将上面命令表当成一次性串联脚本，每步应检查结果再继续。

## 4. 异常与恢复

| 异常 | 处理 | 阶段状态 |
| --- | --- | --- |
| 代理/网络短暂失败 | 最多2次有原因的重试，保存退出码与诊断；确认11809监听，必要时再调查 | in progress；不能直接越阶段 |
| 认证/权限缺失 | 只诊断，不导出token，不改其他身份；报告需要的最小登录/权限 | blocked；保留本地提交 |
| 非快进/其他人更新 | 代理fetch，仅按明确归属整合；冲突保留本地C与原有改动，禁止改写已推送历史 | 整合复验前不能退出 |
| 提交钩子失败 | 排查真实原因，不用`--no-verify`绕过需要的检查 | 修复后重试 |
| 用户工作树/暂存区不属于本任务 | 只处理本任务allowlist，必要时以隔离分支/副本处理依赖；不得删除用户内容 | 不借此批量提交 |

每个阶段报告必须有`local_commit / remote_commit / remote_verified_at / receipt_path / baseline_status`。M6最终交付必须同时给出最终S完整SHA与对应包SHA，两者不是同一个身份。

## 5. 阶段内候选源码提交

后续Python worker/引擎/资料逻辑必须进入实际安装的训练器源码归档。阶段尚未退出时允许先对已检查的小批代码做明确标WIP的正常commit/push，作为可下载、可复现候选输入；这些提交不代表本阶段已完成，也不解锁下一阶段。记录完整feature提交、归档/编译前端/配方摘要与实际安装receipt，不能用开发工作树overlay冒充发布源码。

候选训练器源码提交与启动器嵌入catalog的构建提交可不同：先固定前者的归档SHA，再构建后者，避免在同一提交内要求写入自身源码归档摘要的循环。最终交付另记录`trainer_source_commit / launcher_build_commit / package_sha256`；S仅更新状态时无需重建产品，最终远端S不冒充产品构建提交。普通用户main推荐仍须经过发布验证，不因候选来自feature分支就静默默认它。
