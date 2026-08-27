# 冒烟清单 — <engine id>

每个变体至少跑通一条，证据回填 FIELD_NOTES.md「冒烟证据」表。

- [ ] 安装：`POST /api/engines/<id>/install`（dry_run:false）→ state=ready，audit 全绿
- [ ] 预检：`POST /api/engines/<id>/preflight` 缺资产时错误清单正确
- [ ] 提交：`POST /api/run` 返回 task_id，任务出现在任务列表
- [ ] 产物：训练跑完产出 LoRA/权重文件，日志无异常报错
- [ ] 重启后：状态仍 ready（audit 无漂移误报）
