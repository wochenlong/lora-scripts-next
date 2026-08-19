# 任务调度器双通道改造：调查 + 实施记录

> 调研日期：2026-08-16；基于 dev 分支 `657e57c`。
> 现象：训练进行中可以装插件，但插件安装进行中训练起不来。怀疑任务 schedule 设计问题，经查证属实。
> **修复状态（2026-08-16）**：已在 `feat/task-scheduler-lanes` 分支实施完成并真实环境冒烟通过——算力/维护双通道、训练排队与持久化（重启后手动确认恢复）、失败任务重新排队、任务页配套 UI；另修复 insights 数据串台（窗口限定为 `[started_at, finished_at]`）。详见 CHANGELOG「未发布」节。

## 现象（用户可感知）

1. **装插件（Anima Fast / musubi-tuner）或下载模型资产时，提交训练任务直接失败**，报错"无法创建训练任务 / Failed to create task"，必须等安装/下载结束才能训。
2. **反过来却通**：训练进行中可以正常发起插件安装，安装不会等训练结束。
3. 第二个训练任务也无法提交——没有排队等待的概念，只能人肉盯梢重试。

## 根因：全局单例 `TaskManager`，`max_concurrent=1`，无队列、无任务线（lane）

### 1. 唯一的调度设施，全局共用一把锁

`mikazuki/tasks.py:205-248`：

```python
class TaskManager:
    def __init__(self, max_concurrent=1) -> None:   # 全局只允许 1 个 RUNNING
        ...

    def create_task(self, command, environ, metadata=None, cwd=None, task_id=None):
        running_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]
        if len(running_tasks) >= self.max_concurrent:
            log.error("Unable to create a task ... 已达到最大并发限制。")
            return None                              # 直接拒绝，没有排队
        ...

tm = TaskManager()   # 全局单例，所有任务类型共用
```

- **无队列**：`create_task` 超限即返回 `None`，训练入口（`mikazuki/process.py:253`）收到 `None` 直接返回 error，任务不会被挂起等待。全仓库无 queue 实现（grep `queue` 仅命中无关的 websocket 路径）。
- **无任务线**：算力型任务（训练子进程）与维护型任务（装插件、下模型）混在同一个池子，共享 `max_concurrent=1` 的限制。

### 2. 两类任务入口不对称 —— 正好解释"单向阻塞"

| | 训练任务 | 插件安装 / 模型下载 |
| --- | --- | --- |
| 入口 | `tm.create_task()`（`process.py:253/348/420`） | `tm.add_task()` + `task.start_log_only()` |
| 检查并发限制？ | ✅ 超限返回 `None` | ❌ **完全绕过** `max_concurrent` 检查 |
| 执行方式 | `subprocess.Popen` 子进程，占 GPU | 主进程 daemon 线程跑 pip/下载，仅登记状态 |

安装/下载三处均为同一模式（`add_task` 后门 + 线程执行）：

- `mikazuki/anima_fast_backend/environment.py:784` — Anima Fast 安装（`kind: anima_fast_install`）
- `mikazuki/musubi_backend/environment.py:501` — musubi-tuner 安装（`kind: musubi_install`）
- `mikazuki/model_assets.py:277` — 模型资产下载（`kind: assets_download`）

于是现象完全对得上：

- **训练时可装插件**：安装走 `add_task`，不看 RUNNING 计数，直接插队，`start_log_only()` 把自己置为 RUNNING。
- **装插件时训练起不来**：安装任务已占住全局唯一的 RUNNING 名额，训练走 `create_task` 一数 `>= 1`，拒绝。

### 3. 旁证：维护型任务本就不该被全局锁卡住

- 打标/prefetch（`app/api.py:1321/1331` 的 `run_interrogate_job`/`run_prefetch_job`）走 FastAPI `BackgroundTasks`，**不走 `tm`**，所以打标和训练可以真正并行——说明"维护任务与算力任务分离"在架构上已被部分实践，只是 `tm` 管的那部分没做。
- 安装/下载本身是主进程内线程（不占 GPU），却因为共享了 `tm` 的 RUNNING 计数而把 GPU 任务挡在门外，属于误伤。

### 4. 隐患：musubi 三阶段训练的创建顺序

`process.py:343-348` 一次提交串行执行 cache_latents → cache_te → train 三个 stage，但三个 `Task` 是**循环里先全部 `create_task` 再逐个 execute**。目前能过是因为创建瞬间尚无 RUNNING 任务；一旦未来引入队列或提高并发度，"先全创建再跑"的模式会与并发检查逻辑冲突。

## 期望行为（建议）

1. **训练任务支持排队**：提交时若有训练在跑，进入 `QUEUED` 状态等待，前序训练结束自动启动下一个；`TaskStatus` 枚举与 `/api/tasks` 的 `dump()` 天然可扩展，前端 TasksPage 加一个状态展示即可。
2. **任务线分离**：
   - 算力线（compute）：训练类任务，`max_concurrent=1`（GPU 独占），内部串行 + 排队。
   - 维护线（maintenance）：插件安装/模型下载，可与训练并行；同引擎安装之间用 per-engine 锁防并发（避免两个安装同时写同一 `.venv`）。
3. **收敛 `add_task` 后门**：安装/下载统一改走带 lane 参数的创建入口，不再绕过并发检查，只是查的是各自 lane 的计数。

## 影响范围（改动涉及文件预估）

- `mikazuki/tasks.py` — TaskManager 增加 lane 概念与队列（核心）
- `mikazuki/process.py` — 训练三个入口（standard / musubi 三阶段 / 其他）指定 compute lane + 排队语义
- `mikazuki/anima_fast_backend/environment.py` / `musubi_backend/environment.py` / `model_assets.py` — 安装/下载改走 maintenance lane
- `frontend/src/api/tasks.ts` / `pages/TasksPage.vue` — `QUEUED` 状态与 lane/kind 展示（可结合 #226 §2 kind 标签一起做）

## 备注

- 与 #226（任务页体验）有交集：安装任务 metadata 已带 `kind` 字段， lane 落地后前端分栏/标签的素材完全现成。
- 历史背景待确认：`TaskManager.__init__` 的 `max_concurrent=1` 从上游 lora-scripts 继承而来，原本只服务训练单一场景；插件体系（anima/musubi 可插拔引擎）引入后复用了 `tm` 做状态登记，但没有同步演进调度模型。
