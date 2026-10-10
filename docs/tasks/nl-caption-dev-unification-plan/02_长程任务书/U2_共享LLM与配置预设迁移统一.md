# U2 共享LLM与配置预设迁移统一

目标T3；依赖AC-U1和冻结基线。目的：把新dev通用管理与现有领域安全整合成唯一权威。

## 执行步骤

1. 在`mikazuki/llm`、`tag_translation`及dev user_data模块明确Profile/schema/错误码，锁定API类型后再让UI并行接入。
2. 将选定manifest接入共享安装器和runtime生命周期，下载/校验/启动/双能力检查后ready。安装取消、坏hash、断网、重试、端口冲突和重复点击逐项处理；不重复启动两个模型。
3. 统一旧翻译配置与`/api/llm/*`，远程优先、能力过滤、本地显式兜底、运行时Key与脱敏导出；修正manifest语言与Profile/目录声明不一致。
4. 在`user_data/presets`实现Caption完整schema、revision、通用/旧接口adapter、事务与训练隔离；旧文件/localStorage导入预览、冲突、失败恢复及幂等标记。
5. 统一SQLite执行与TaskManager/user_data投影，冻结快照；实现任务停止、隐藏、删历史、回滚的独立语义，更新cache身份。
6. 以旧0.8B、VL、已有远程Profile、旧预设和任务档案的脱敏fixture走升级；再次迁移应零重复/零丢失。禁止实际用户配置自动覆盖。

## 输出、验证与完成门 AC-U2

- 输出：安装器/adapter/迁移器、统一API契约、缓存与任务规则、迁移报告。
- 单元/contract/integration/gray覆盖路由顺序、text-only拒绝Caption、Key不落盘、中文短路、安装所有终态、两API同库、revision冲突、事务失败、任务仅执行一次。
- 用真实选定模型验证同一PID/asset完成text+vision并能取消再运行；旧模型未被自动删除；数据库/用户数据hash可核对。
- 证据：`docs/evidence/natural-language-captioning/dev-unification-20261010/U2/`；API schema与fixture请求脱敏留存。

## 失败退回

数据/密钥风险为P0，先阻断写入并恢复事务，保持旧源；不得通过删迁移测试或旁路统一服务解决。安装兼容问题退回U1，模型/runtime变化重新评测。完成后更新canonical，允许进入U3；已冻结契约下的无重叠UI实现可提前准备但不能越门签署。
