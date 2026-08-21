# 备份项目施工规则

当前项目位于独立备份区 `E:\OpenSourceTeamWork\Kimi_Agent_lora-scripts-next-agent-dev\project`。这是平行开发副本，不是正式开发工作区。

- 只允许修改当前备份项目及其同级 `development-docs`；禁止访问并写入源项目和源文档目录。
- 所有输出、缓存、测试报告和临时脚本使用当前项目内的相对路径。
- 只允许本地 `git commit`，禁止 `git push`、PR、release 和远程分支操作。
- 提交前执行 `git status --short --branch`，并确认路径仍为本备份项目。
- 不要把 `.venv-dev`、`node_modules`、模型、密钥或大型运行时产物加入新的 Git 提交。

