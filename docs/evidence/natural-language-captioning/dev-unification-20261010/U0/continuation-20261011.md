# 执行续接摘要（2026-10-11，U0未签署）

## 当前目标

goal DATASET-NL-DEV-UNIFICATION-20261010 active。用户明确恢复全面实施U0–U6；全部门pass及最终新沙盒就绪才关闭，人工手验pending_followup。唯一进度docs/tasks/natural-language-captioning-task-book.md。

## 当前现场与已完成

正式feature根workspace/branches/feat-NL-Captioning，临时集成根workspace/branches/nl-caption-dev-merge-20261011。两HEAD均9c059ccec000d26b3d0da50e26071f1ab84d9b7d，MERGE_HEAD冻结2bdccd1b1252db9ba3158c30d56df0e292206c67。15项index UU，文本无markers，尚未stage/commit/FF。不能重新fetch替换冻结或重复merge。

此前15处融合保留dev新UI/全局下载源/用户数据与feature完整Caption jobs/安全。当前主会话发现模型接口并非完全丢catalog，而是llm完整路由与app简版GET重复；已移除app简版，新增test_tagger_model_catalog.py正式app唯一目录与text-only过滤/脱敏HTTP测试。98项后端冒烟全部pass，无skip，日志与JUnit在workspace/tools/nl-caption-u0-20261011/u0-resume-smoke.*。

merge_tagger独占TaggerPage.caption.test.ts与TaggerPage.test.ts，完成旧DOM/ElSelect/完整预设契约适配，35项pass、type/lint pass，保留全部原32意图和3新增边界。日志/摘要在同tools根tagger-tests-*。

主会话npm runcheck首轮416pass/2fail，仅DatasetPage.test.ts旧scan/default-selection契约。已派merge_editor仅改该测试，不改业务；需要最终定向通过后完整check重跑。first-failure日志已保留。Agent/引擎工作树差异无主动修改。

## 关键约束、路径与落位办法

用户tests/test_diffsynth_review.py正式根原字节SHA256=8620db361c56816fe938c2b41f81b462a41233d39205dba5cee0a0b39dd2ed3d；HEAD和dev该文件blob同9adacc4fc067d8180138f2b6773508519e371454。不纳入本次提交，不覆盖。原字节/patch已备份同tools根。

正式根16项本任务计划dirty与临时根相同；已另存formal-plan-preservation-20261011.zip/json（仅文档）。merge提交成功后先验证目标commit内这些文档等于已保存副本，再只将正式根这些owned文档恢复HEAD工作树，不动用户test，再git merge --ff-only tmp/nl-caption-dev-unification-merge；文档将随FF恢复。不得全量stash/reset。

frontend/dist为本任务构建dirty，依规则不stage入源码merge；保留临时根真实生成产物供检查。stage冲突和本任务源/测试/计划/evidence必须显式路径，不git add .。

Python3.11=workspace/sandboxes/nl-caption-manual-20261009/.venv/Scripts/python.exe。Node22=该旧sandbox/npm-cache/_npx/7d1965ce44b6fdcf/node_modules/node/bin/node.exe；只读复用U0允许，U5禁止。系统npm.ps1可能锁Node24，使用Node22调用I:/NdoeJS/node_modules/npm/bin/npm-cli.js，PATH前置tools/nl-caption-u0-20261011/node22-bin/npm.cmd wrapper（nested npm仍Node22）。环境state指向同tools/state，旧sandbox不修改/重启。

## 后续欠项与探针资料

AC-U0通过才下载/运行U1。比较Qwen3-VL-2B Q4_K_M+Q8 mmproj与Qwen3.5-2B Unsloth Q4_K_M+F16 mmproj；精确asset metadata在workspace/tools/nl-caption-dev-analysis-20261010/{Qwen--Qwen3-VL-2B-Instruct-GGUF,unsloth--Qwen3.5-2B-GGUF}--metadata.json（keys id/revision/assets，不是HF siblings）。runtime b11327锁见docs/evidence/natural-language-captioning/phase-4-real-evaluation/phase5-frozen-inputs.json，仅继承资产锁来源，不继承旧验收。6图×3预设、12翻译、3启动、中文零调用、取消/共享/RSS≤6GiB等门在probe plan，不能削弱。

merge_editor只读U2审计已完成：预设双方默认已同user_data/presets但锁/schema/settings不兼容，统一领域事务而非复制两目录；UserDataStore忽略MIKAZUKI_USER_DATA_ROOT需修以防污染。配置与Key现共享translation.json/secrets已掩码，保持llm权威，不接user_data/auth明文存储。增加config revision、按revision能力实测状态、remote A失败再尝试其它remote然后显式local。U1后再分域实施U2。

真实remote是后续硬门，Key只后端运行时输入，不复制文件/参数/日志；历史评分与豁免不得继承。U3保存期间继续编辑/恢复译文等仍待做。U1–U6全部pending。

## 唯一下一步

读取merge_editor DatasetPage测试修复结果；重跑全前端check。然后完成U0证据与安全stage/merge commit/feature FF、双祖先/hash检查，签署AC-U0后进入模型探针。
