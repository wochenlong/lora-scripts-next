# AC-U0 完成门

结论：pass，2026-10-11。合并提交a1de47e57e8add745d8e3afc4c062a56f39cede5已安全快进feat/NL-Captioning；父提交9c059cce与冻结dev2bdccd1b均为祖先，index无未合并项。

完整前端check 418/67通过，typecheck/lint/build exit0；后端六组契约冒烟98 passed、零失败/跳过。原始日志、JUnit、基线锁与冲突决策同目录。首败与并发失败在workspace/tools/nl-caption-u0-20261011保留。限制4个Vitest worker后通过，未放宽断言/超时。

独立审计未发现新增U0 P0/P1。正式根16项本任务文档已zip+hash备份，确认目标commit包含同一成果才清理这些owned工作树内容；第一次FF因Windows换行/stat出现无内容差异的dirty拒绝，核对HEAD/工作树blob一致后仅刷新这16项index，第二次FF通过，未强制重置。

用户tests/test_diffsynth_review.py SHA256仍为8620db361c56816fe938c2b41f81b462a41233d39205dba5cee0a0b39dd2ed3d，未进入提交。临时根生成dist未stage；旧沙盒/用户数据未启动或改写。Agent等无主动改造，训练引擎差异仅冻结dev带入。

U2/U3欠项见baseline.json；本门只冻结可构建开发基线，不能代替后续完整验收。解锁U1，两款模型实际探针尚未运行，goal保持active。
