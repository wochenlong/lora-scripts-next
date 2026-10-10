# U0 合并冲突与语义决策

本轮接续 9c059cce 与冻结 dev 2bdccd1b 的既有 merge，不重新 fetch/merge。原用户 test_diffsynth_review.py 保留正式工作树原字节，SHA256与原备份一致。

| 文件 / 区域 | 决策与验证 |
|---|---|
| .gitignore、README中英、settings.css | 保留双方独立增加项 |
| API client | 保留detail.message解析与实际httpStatus，包括非JSON HTTP失败 |
| tagger API | 保留完整catalog、jobs预览/批量/取消/重试/历史/报告/回滚；Tag请求接全局下载源 |
| i18n中英 | 同时保留llm与engineSettings模块，修复融合括号 |
| caption helpers | 保留natural/unknown/mixed保守守卫；仅已知Tag来源使用新版分隔符，自然句子不拆Tag |
| 翻译设置Dialog | 保留dev全局设置链接与词典管理；LLM走共享配置，移除旧local-only旁路 |
| DatasetEditor/CSS | 保留新版图库/多选/ManagedDatasetPicker，融合natural raw与只读译文、中文短路、草稿/hash/扫描generation |
| Tagger/CSS | 保留新版全宽/参数侧栏/分组ElSelect和完整旧jobs链路；预设总控语言/格式，vision过滤与remote-first |
| proxy | 使用dev请求时动态endpoint、enabled fail-closed、trust_env=False与新httpx兼容，移除旧未定义外层client |
| 无文本冲突 /api/tagger/models | 真实问题为两个重复GET路由：早注册llm目录完整，后注册dev路由仅id/downloaded。移除重复简版，正式app新增唯一完整目录契约测试，避免OpenAPI/运行路由语义分裂 |
| 页面测试 | 适配新版DOM/ElSelect，保留行为断言；首次失败与修复后结果分别保存，不删除失败用例 |
| frontend/dist | 中间构建生成文件保留本根用于验证，不主动stage进源码merge；源代码验收与生成产物分开记录 |

## 已知后续缺口

U2：共享Profile/settings适配、实际能力验证状态与remote候选链、统一安装默认模型；user_data预设同目录但schema/锁/revision/默认设置不一致，须领域事务统一，不能假称已同库即安全。

U3：编辑保存请求期间继续输入不得被晚到响应覆盖；同原文选择恢复后重新加载译文；共享readiness完全替代legacy；新版UI自然语言只原文/只读译文/中文零请求，前后端Tag守卫均保持。

U1模型候选仍未下载探测，U4完整回归/真实链路、U5从零与U6新沙盒尚未执行。98项后端冒烟只是U0当前范围，不代替后续验收。

## 范围

dev带入的Ideogram4/Musubi/其它引擎等均来自冻结dev，未主动改造。Agent/sidecar/plugin不新增改动；不修改用户测试，不启动/覆盖旧沙盒。

## 全量检查追加发现

完整前端首次416通过/2旧DOM失败；适配后417通过/1全量并发5000ms超时（定向5/5通过）。保持原超时与全部业务断言，将Vitest worker上限设为4，避免宿主机默认大量进程争抢导致假失败；不更改依赖锁、代码行为或断言。首败与并发失败日志保留。
