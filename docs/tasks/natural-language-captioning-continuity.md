# 自然语言打标续接记录

更新 2026-10-07。canonical progress 为 natural-language-captioning-task-book.md；完整目标包括全部前后端、测试/真实/人工和 Phase 4 从零重建，不能缩水。

## 当前状态

- 工作树 E:/OpenSourceTeamWork/workspace/branches/feat-NL-Captioning；分支 feat/NL-Captioning。本批基线 eb93de4，提交号读 git log。
- 每次续接先读 C:/Users/25454/.codex/attachments/33329a36-8e01-4211-b79c-a080571cde4b/goal-objective.md。
- Phase 0/1 done（有 gate-review），Phase 2 in progress，Phase 3/4 pending。goal 保持 active。
- 最新相关后端 218 passed / 4 warnings / 19.05s；编辑器 35 passed / 3.05s；Node22 check 321 tests / 51 files、type/lint/build pass，2 个已有 lint warning。
- 宽范围仍 1139 passed / 11 failed / 21 skipped，另有31训练 collection errors，缺逐用例失败日志；不能当作完整矩阵通过，须恢复/复现并修复。

## 环境

- Python 3.11.15：workspace/sandboxes/nl-caption-runtime-20261006/.venv/Scripts/python.exe；不要用宿主3.14。requirements/pytest已安装。
- Node22.17.1：npm exec --yes --package=node@22.17.1 -- node 'I:/NdoeJS/node_modules/npm/bin/npm-cli.js' --prefix frontend run check。npm ci完成；不要用宿主24。
- GitHub git统一127.0.0.1:11809代理；没要求push，旧worktree保留。
- P1资产位于workspace/sandboxes/nl-caption-p1-20261006/.sandbox-data；仅中间开发可复用，Phase4禁止复用venv/node_modules/模型/缓存/配置/output。
- Qwen3-VL-2B Q4_K_M+Q8 mmproj，revision/SHA固定在local_vision.py；runtime b11327，共用translation models/runtime。
- 真实批量目录workspace/sandboxes/nl-caption-batch-20261007-r2：三公共样本14.803s，峰值3094904832B，实际冲突/取消0.026s/再次连接/停止通过。前次脚本误选text-only profile失败已记录，修正后freshroot通过。不是Phase4。模型进程已停止。
- 本轮浏览器dev服务端口5176/28761和两个自建进程已停止；无待等测试handle。空配置根nl-caption-browser-20261007，截图outsideGit；lifespan=off仅页面验证。

## 不可变决策和实现

- Tag由WD/CL，LLM仅natural；caption须vision，translation只需text；remote-first，只有显式启用才能local fallback，默认false。
- process-only真实Key、磁盘/响应掩码，重启需重新注入。真实Key不放源码/CLI/envfiles/log/report/截图。远程bounded JPEG dataURL，无文件名/绝对路径/EXIF。
- 配置v5+迁移/锁+secret epoch；精准profile连接测试；caption严格JSON拒绝重复键/NaN/截断，上限1–2000参与prompt revision/schema/cache。
- shared translations.sqlite3缓存+CaptionJobStore私有请求/冻结计划/backup/intent。重启不autoinference、afterhash恢复；retry创建parentjob，冻结提示词，读当前profiles/keys。
- 旧Tag及caption writer atomic/hash；image source也校验；自然/mixed不Tag合并清理；prompt预设增删改撤销已实现。
- 共享LlmSettingsDialog用于Tagger和translation，profiles/routes草稿cancel清空、精确测试；旧translation互斥tabs已改显式fallback，但旧文案和本地asset管理仍待统一。
- caption_formats path+hash+actualTags来源，短natural和caption-first mixed安全；编辑器scan/save带hash；原文CRLF保留。无来源历史短句仍启发式边界。
- 本批useTaggerJob/useLlmProfiles单飞+AbortController+generation，离页取消，旧poll不盖cancel，新report优先；CaptionPromptEditor/CaptionJobProgress抽取；历史恢复/报告接入。
- 编辑器批量snapshot/rawhash冻结，前端发扫描expected_hashes，先整批验证；undo/redo检查另一侧hash，外部修改/删除拒绝、预检不改stack；中途失败部分历史分拆。快照单次字节读、Tag/natural/mixed恢复精确保留字节。
- 浏览器桌面1440/narrow390无横向overflow、空profiles禁preview/batch、不自动下载、共享草稿Escape关闭不persist；窄屏actions与history已修正重叠。全业务浏览器/正式启动未验收。

## 待办/风险

1. 完成本地视觉资产管理共享UI、native text模型profile/readiness复用；兑现translation cache flag；任务安全rollback/clear。
2. 完整浏览器CRUD/preview/batch/cancel/retry/report/conflict/mixed、键盘/error/privacy、三模式ONNX真实路径。
3. Phase3 frozen public样本+rubric、真实远程中文（需进程注入原用户Key，不能写文件）、Qwen本地中文/远程优先显式fallback、EDD人工评分/失败baseline、正式Zero-Short/发布/扫描。
4. 完整回归失败闭环：缺torch/transformers/training依赖、README、symlink权限、trainingstub；未获豁免，不能跳过。
5. Phase4全部提交后freshcheckout/newPython/newNodeci/newmodeldownloads/newconfig/cache/output，从零复验全链路；失败回修后再建freshroot。
6. frontend/dist构建后恢复tracked基线，禁止手改/误提交删除；最终从源码build。图片/DB/GGUF不入Git。

## 单一 Next action

将本地视觉资产管理接入共享 LLM 设置，并兑现翻译 cache 开关。

证据：docs/evidence/natural-language-captioning/phase-2-frontend-editor/2026-10-07-history-polling-editor-conflicts.md。Confidence medium：增量已验，完整矩阵/实际浏览器/EDD/隔离重建仍未闭环。
