# Agent 原生接入（设计说明 · 开发任务）

> 状态：设计草案（公开）  
> 说明：本文不含密钥、本机路径或内部排期承诺；实现细节以后续 PR 为准。  
> **排期：等 `dev` 转正后再启动实现，当前不急；本稿仅定方向与开发任务边界。**  
> 关联：前端信息架构 [#215](https://github.com/wochenlong/lora-scripts-next/issues/215)、Vue3 前端 [#209](https://github.com/wochenlong/lora-scripts-next/pull/209)

本文说明 **目标、约束、以及开发需要交付的工作包**。未列入 P0 的项默认后置。

---

## 1. 背景与目标

### 1.1 背景

Next Trainer 已具备 WebUI、训练提交、任务与打标等能力。常见训练工具往往是「给人操作的界面」与「给脚本调用的上游」两套心智。

本项目将 **外部 Agent（编码助手等）视为第二用户**：与人类共用同一套数据集、打标、训练计划与任务系统，而不是给页面加遥控，或把任意 shell 当作官方能力。

### 1.2 产品目标

1. Agent 能稳定完成：校验数据集 →（可选）打标 → 训练计划 / dry-run → 开训 → 查询或停止任务。
2. Agent 发起的作业出现在「任务」页；人类可接管或停止。
3. 侧栏提供独立 **Agent** 入口（接入说明与凭证），不占用「训练 / 数据集 / 任务 / 设置」主路径。
4. 官方提供机器可读契约（以 HTTP API 为主；MCP 为后续薄封装），不以操作 DOM 为官方通道。

### 1.3 非目标（首版不做）

- 完全无人值守、自动修复一切训练失败
- 将任意 shell 或上游启动命令裸露为一等工具
- 为 Agent 再造第二套训练配置页
- 将 MCP 作为唯一或前置交付（先 HTTP API，再 MCP）
- 要求每个训练引擎各自维护一套数据集或打标流程

### 1.4 对外表述（仅在 P0 验收后使用）

> Next Trainer 原生支持 Agent：人和 Agent 共用同一套工作台与任务系统；从数据集到出模，Agent 可代跑，人随时能接手。

未完成下方 P0 时，对外仅可写「规划中」，不可写「已原生支持」。

---

## 2. UI 要求（前端）

### 2.1 导航

| 入口 | 要求 |
|------|------|
| 训练 / 数据集 / 任务 / 设置 | 保持现有顺序与职责（见 #215），不因 Agent 改动主路径 |
| **Agent** | 侧栏**底部**独立项（可靠近帮助入口）；可标 `Beta` |
| 设置 | 可放引擎或高级细节；**不得**作为 Agent 的唯一入口 |

### 2.2 Agent 页（轻量接入台）

只做接入与说明，**不**承载完整训练配置表单：

- 能力说明（人机共用任务系统）
- 本机访问凭证的生成 / 轮换 / 权限级别展示
- 可用工具列表（来自 capabilities API）与调用顺序说明
- Skill / MCP 连接说明与示例（MCP 可先占位）
- 跳转到「任务」查看 Agent 发起的作业

### 2.3 任务页

- 任务列表需能区分来源：`human` / `agent`（字段名实现自定，需稳定）
- 人类停止 Agent 任务后，Agent 侧轮询须能读到终态

---

## 3. 架构原则（全栈必须遵守）

### 3.1 分层

```text
人类 UI（四栏） ──┐
                  ├──► 同一套领域服务 / Job / 数据集标准
Agent HTTP/MCP ──┘
```

| 层 | 职责 | 首版 |
|----|------|------|
| L0 契约 | 工具名、入参/出参 JSON Schema、错误码、API 版本 | 必须 |
| L1 Agent HTTP API | 外部 Agent 通过 HTTP 调用 | 必须 |
| L2 MCP / Skill | 同一后端的薄封装 | P1 |
| L3 Agent 页 | 凭证与说明 | P0 需有页；MCP 文案可后补 |

### 3.2 统一 Job（硬约束）

长操作（至少：**打标**、**训练**）必须走同一状态机：

`create → poll → events → result`，支持 `cancel`。

建议字段（名称可微调，语义要稳定）：

| 字段 | 说明 |
|------|------|
| `job_id` | 稳定 ID |
| `kind` | 如 `tagging` / `training` |
| `status` | 如 `queued` / `running` / `succeeded` / `failed` / `cancelled` |
| `progress` | 可选，0–1 或结构化进度 |
| `message` | 人类可读摘要 |
| `artifacts` | 产物路径列表等 |
| `error` | 稳定错误码 + 可选 detail |
| `actor` | `human` \| `agent` |

禁止：打标与训练使用互不相通的两套状态模型。  
现有任务、打标、开训接口应 **收敛或适配** 到此模型，而不是再平行增加第三套。

### 3.3 数据集与打标单轨（硬约束）

> 数据集与打标是公共层；训练引擎只通过 adapter 消费同一份源数据。不得要求用户为每个引擎复制一套数据或打标流程。

```text
源数据（图/视频 + caption；编辑类另含 control）
  → 打标 / 数据集工具（与 engine 无关）
  → plan_training(model, engine, …)
  → 引擎 adapter（私有 cache 允许不同）
```

逻辑子集模型（解析常见 `N_name` 目录名）：

- 目录名匹配 `^(\d+)_(.+)$` → `repeats` + `name`
- 内部统一为 `subsets: [{ path, repeats, name }]`
- 各引擎 adapter 再序列化为该引擎配置（如 `num_repeats`、多数据目录项）

Agent 工具顺序：

1. `dataset.*` / `tagger.*` — **禁止**按 engine 分叉 API
2. `plan_training` / `dry_run` / `start_training` — 此处才出现 engine

### 3.4 安全默认

- 本机访问凭证（Token）；权限至少区分：只读 / 可打标 / 可开训
- 路径限制在项目允许的数据与输出根之下（防止目录穿越）
- 写操作与开训记录审计（操作者、时间、动作）
- 禁止将「任意命令执行」暴露为官方工具
- 凭证与密钥不得写入仓库；示例文档只使用占位符

---

## 4. 开发要做什么（按工作包）

下列路径为建议落点，实现时可调整，但 **交付物语义** 不变。

### 4.1 后端 · 契约与鉴权

| 任务 | 说明 | 建议落点 |
|------|------|----------|
| API 版本 | 例如在 capabilities 响应中返回 `agent_api_version` | 新模块，如 `mikazuki/agent/` |
| Token | 生成、校验、权限；默认面向本机可信场景 | 本地配置或密钥存储（**勿提交仓库**） |
| Capabilities | 列出工具 id、标题、入参 Schema、副作用等级（read/write/train） | `GET /api/agent/capabilities` |
| 鉴权中间件 | Agent 路由与敏感写操作校验 Token | FastAPI 依赖注入 |
| 错误码表 | 稳定字符串码（见 §5），附可选 `hint` | 共享错误类型 |

### 4.2 后端 · 统一 Job

| 任务 | 说明 | 建议落点 |
|------|------|----------|
| Job 存储/查询 | 创建、更新状态、列表、按 id 查询 | 扩展现有 task 体系或薄封装层 |
| 训练 Job | 包装现有开训与进程管理，写入统一 Job + `actor` | `mikazuki/app/api.py`、`mikazuki/process.py` 等 |
| 打标 Job | 包装现有打标接口为同一 poll 形状 | 现有 tagger 相关 API |
| Cancel | 训练终止与打标取消映射到统一 cancel | 现有 terminate / cancel |
| 日志 | P0：可 `tail` 文本；P1：可选结构化 events | 现有训练日志接口 |

### 4.3 后端 · 最小工具实现（P0）

每个工具对应 HTTP 端点（或统一 `POST /api/agent/tools/{name}`），入参出参有 Schema。

| 工具 | 行为 | 可复用现状 |
|------|------|------------|
| `validate_dataset` | 扫描目录：图片、caption、子集与 repeats；返回逻辑 `subsets` 与问题列表 | 部分文件/数据集逻辑；需收口 |
| `start_tagging` | 创建打标 Job，返回 `job_id` | 现有 interrogate / tagger API |
| `get_job` | 查询任意 kind 的 Job | 现有 tasks 等，需统一 |
| `plan_training` | 输入 model/engine/target/数据集等 → 合法配置草案与警告 | schemas、presets；可选引擎的 preflight 可作参考 |
| `dry_run_training` | 不做完整长训；校验路径、引擎就绪、配置 | 现有 dry-run / preflight 能力需补齐到内置引擎 |
| `start_training` | 创建训练 Job；写 `actor=agent` | 现有 `/api/run` |
| `tail_logs` | 返回日志尾部 | 现有 train log API |
| `stop_training` / `cancel_job` | 停止 | 现有 terminate |

P0 路径：先打通 **内置训练引擎**，以及当前已可选安装的加速引擎（若环境可用）。不阻塞于尚未接入的其他引擎。

### 4.4 后端 · 数据集公共解析（P0 最小）

| 任务 | 说明 |
|------|------|
| 目录扫描 | 支持常见图片扩展名 + 同名 `.txt`；识别 `N_name` 子集 |
| 校验报告 | 缺 caption、空目录、非法路径等 → 稳定错误码或 warning |
| 输出逻辑模型 | `subsets[{path,repeats,name}]` 供 plan 与人类 UI 共用 |

编辑（control 配对）、视频（抽帧参数）可在后续 kind 扩展；P0 以 **文生图数据集** 为准。

### 4.5 前端 · 侧栏与页面

| 任务 | 说明 | 建议落点 |
|------|------|----------|
| 侧栏 Agent 项 | 底部入口 + 路由 | `frontend/` 导航与路由（Vue3 / `dev` 线） |
| Agent 页 UI | §2.2 内容；调用 capabilities / token API | 新页面或视图 |
| 任务来源展示 | 列表/详情显示 human/agent | 任务相关视图 |
| i18n | 中英文案 | 现有 i18n 流程 |

若预编译前端线仍并存：至少保证 **Vue3 / `dev` 线** 落地；是否双线同步在实现 PR 中写明。

### 4.6 文档与接入包（P0）

| 任务 | 说明 | 建议落点 |
|------|------|----------|
| Agent 调用说明 | 工具顺序、鉴权头、示例请求（Token 用占位符） | `docs/` 短文（可后续 PR） |
| Skill 草稿 | 给外部 Agent 的步骤说明（**无真实密钥**） | `docs/` 或仓库内约定目录 |
| 契约测试 | 尽量无 GPU：validate → plan → dry-run；有环境再测 start | `tests/` |

### 4.7 P1 工作包（P0 完成后）

- 目录沙箱强化与审计日志持久化
- 结构化错误分类（如显存不足、缺模型、路径错误等；规则即可）
- 官方 MCP server（仅包装 L1，不复制业务逻辑）
- 与训练引擎安装/就绪状态打通：引擎未就绪时 `plan` / `start` 返回明确错误码
- `agent_api_version` 兼容策略说明

### 4.8 P2 工作包

- 失败解释类增强工具
- 数据集写入类工具（导入、批量改 caption）
- `kind=edit` / `video` 的校验与工具扩展
- 多引擎 `plan_training` 规则维护

---

## 5. 错误码（初版约定）

实现时可增补，但 **已发布码勿随意改义**。

| 码 | 含义 |
|----|------|
| `UNAUTHORIZED` | 凭证无效或缺失 |
| `FORBIDDEN` | 权限不足（如只读 Token 尝试开训） |
| `DATASET_INVALID` | 数据集校验失败 |
| `DATASET_NOT_FOUND` | 路径不存在 |
| `ENGINE_NOT_READY` | 可选引擎未安装或不可用 |
| `CONFIG_INVALID` | 配置未通过 schema 或计划校验 |
| `TRAINING_REJECTED` | 拒绝开训（策略或预检失败） |
| `JOB_NOT_FOUND` | Job 不存在 |
| `JOB_NOT_CANCELLABLE` | 当前状态不可取消 |
| `INTERNAL_ERROR` | 未分类内部错误 |

响应建议同时包含：`code`、`message`、可选 `hint`（给 Agent 的下一步建议，短句即可）。

---

## 6. 阶段与验收

### 6.1 阶段

| 阶段 | 交付 |
|------|------|
| A | Job 收口 + Agent HTTP 最小工具 + 契约测试 |
| B | Token + 侧栏 Agent 页 + 任务来源展示 |
| C | 调用说明 + 真机一条龙演示（校验→打标→开训→任务） |
| D | MCP + 沙箱/审计（P1） |
| E | edit/video 等扩展（P2） |

### 6.2 P0 验收（全部满足才可称「原生雏形」）

1. 持有效 Token 可拉取 capabilities（含 JSON Schema）。
2. `validate_dataset` 对标准「图 + caption / `N_name` 子集」给出逻辑 subsets 与问题列表。
3. 打标与训练均可通过统一 Job 查询状态，并在支持取消的阶段可取消。
4. `plan_training` + `dry_run_training` 能拒绝明显非法配置；引擎未就绪有明确错误码。
5. `start_training` 产生的任务在任务 UI 可见且标记为 agent。
6. 侧栏底部有 Agent 页，可管理 Token（或展示安全的一次性复制流程）。
7. 仓库内有无密钥的调用说明 + 至少一条自动化契约测试。

### 6.3 明确不验收（P0）

- MCP 必达
- 自动修复训练失败
- 全模型全引擎 plan 完备
- 编辑/视频数据集完备

---

## 7. 与多引擎的关系

- Agent API 挂在主服务；训练执行仍进入各引擎运行时（如有独立环境）。
- 数据集 API **不**按引擎分叉；仅 `plan` / `start` 使用 engine。
- 新引擎接入不阻塞 Agent P0；落地时扩展 `plan_training` 规则与 dry-run 即可。
- 可选引擎的安装与就绪状态，应能被 `ENGINE_NOT_READY` 等错误码表达（具体管理 UI 另文）。

---

## 8. 建议 Issue 拆分

实现时可拆为独立 Issue 或 PR：

1. `agent`: 统一 Job 模型与训练/打标适配  
2. `agent`: Token + capabilities + 错误码  
3. `agent`: P0 工具 endpoints（validate/plan/dry-run/start/job/logs/cancel）  
4. `agent`: 数据集目录解析（subsets + repeats）  
5. `agent`: 侧栏 Agent 页 + 任务来源展示  
6. `agent`: 调用说明 + 契约测试  
7. （P1）MCP 与沙箱审计  

---

## 9. 相关代码入口（现状）

| 区域 | 说明 |
|------|------|
| `mikazuki/app/api.py` | 开训、tasks、tagger、schemas 等 |
| `mikazuki/process.py` | 训练进程与任务 |
| `mikazuki/anima_fast_backend/` | 可选引擎 preflight / dry-run 参考 |
| `frontend/`（Vue3 / `dev`） | 侧栏与任务 UI 主落地线 |

新增实现优先集中在可测试模块（如 `mikazuki/agent/`），避免把契约逻辑散落在页面脚本中。
