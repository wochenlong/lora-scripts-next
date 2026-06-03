# 插件平台 v0.1 规范（草案）

> 状态：v0.1（可落地）  
> 目标：统一 SD Trainer Next 的插件边界、生命周期、API、权限与安全策略，避免每个插件重复造轮子。  
> 适用范围：`/plugins/*` 页面、`/api/plugins/*` 接口、`extensions/*` 目录下的可选能力。

---

## 1. 设计目标

1. 不安装插件时，用户仍可完成基础训练闭环。
2. 插件安装/修复/卸载/审计流程统一，不依赖页面私有逻辑。
3. 插件日志、状态、错误对用户可见，可排障。
4. 新插件接入只需实现标准接口，不需要复制 Fast 的整套实现。

---

## 2. 插件边界（核心定义）

### 2.1 必须内建（Core）

以下能力必须随主程序提供，不能依赖插件：

- 基础训练流程（参数配置、启动、停止、保存）
- 任务管理与基础日志链路
- 模型/数据路径选择与基本校验
- 基础可用性与安全相关能力（主服务启动、最小依赖）

### 2.2 可插件化（Extension）

以下能力可做成可选插件：

- 性能增强（如 Anima Fast）
- 进阶工具（高级标签编辑器、图库浏览器）
- 新模型家族训练支持（如 Qwen、视频模型训练）
- 第三方服务集成（实验追踪、云端同步）

### 2.3 判定规则

满足全部条件才允许插件化：

1. 不影响主训练闭环。
2. 有额外依赖/环境成本（例如独立 venv、大体积下载）。
3. 对用户群体为「进阶增益」而非「基础必需」。

### 2.4 管理入口 vs 使用入口

| 维度 | 放哪里 | 例子 |
|------|--------|------|
| 安装 / 修复 / 卸载 / 状态 / 审计 | **插件** 一级目录 | Anima Fast、标签编辑器 |
| 实际使用（选参数、开训、编辑） | **仍挂在训练/工具链路** | Anima LoRA → 标准 / Fast |

插件栏管「有没有、健不健康」；训练页管「怎么用」。不要把使用场景整页搬进插件中心。

### 2.5 分层建议（避免一刀切边缘化）

| 层级 | 说明 | 例子 |
|------|------|------|
| Core | 永不插件化 | 基础训练、任务调度、最小打标 |
| Recommended | 生命周期走插件，入口可保留明显曝光 | TensorBoard（用的人多） |
| Extension | 可选 + 可弱曝光 | 标签编辑、LoRA 脚本工具、Anima Fast |
| Community（Phase C） | 默认关闭，需显式启用 | 用户自定义扩展 |

---

## 3. 插件目录与命名

### 3.1 路由与 API

- 插件页面：`/plugins/<plugin-id>/`
- 插件 API：`/api/plugins/<plugin-id>/*`
- 插件状态总览：`/api/v1/plugins`（建议 v0.2 补齐）

### 3.2 本地目录

```text
extensions/
  <plugin-id>/
    install_state.json
    audit_result.json
    source/
    .venv/
```

约定：

- `plugin-id` 使用 kebab-case（例：`anima-lora-fast`、`tag-editor-pro`）
- 插件私有配置写到 `extensions/<plugin-id>/` 或 `config/plugins/<plugin-id>.toml`
- 禁止污染根级 `config/*.toml` 的主训练关键字段

---

## 4. 插件清单（Manifest）规范

每个插件必须提供清单（可放在源码根 `plugin.json`）：

```json
{
  "id": "anima-lora-fast",
  "name": "Anima Fast",
  "version": "1.0.0",
  "description": "Anima LoRA accelerated backend",
  "author": "SD Trainer Team",
  "min_core_version": "2.7.0",
  "capabilities": ["train.accelerated", "optimizer.extra"],
  "entry": {
    "ui": "/plugins/anima-lora-fast/",
    "health_api": "/api/plugins/anima-lora-fast/status"
  },
  "permissions": {
    "filesystem": ["extensions/anima_lora/**", "output/**", "logs/**"],
    "network": true,
    "subprocess": true,
    "gpu": true
  }
}
```

---

## 5. 生命周期与状态机

### 5.1 标准状态

- `not_installed`
- `installing`
- `auditing`
- `ready`
- `broken`
- `update_available`

### 5.2 状态转换规则

1. `installing`/`auditing` 必须是短暂态，任务结束必须收敛到 `ready` 或 `broken`。
2. 发现状态漂移（依赖缺失/版本不符、后台任务已结束但 `install_state.json` 未更新）必须自动落到 `broken` 或协调为 `ready`（见 `read_extension_status` reconcile）。
3. `broken` 状态必须允许用户点击「修复」。

---

## 6. 标准 API（v0.1 最小集）

每个插件必须实现以下接口：

- `GET /api/plugins/<id>/status`
- `POST /api/plugins/<id>/install`
- `POST /api/plugins/<id>/repair`
- `POST /api/plugins/<id>/uninstall`
- `POST /api/plugins/<id>/dry-run`
- `POST /api/plugins/<id>/preflight`
- `GET /api/plugins/<id>/install/log/stream/{task_id}`

返回格式统一沿用当前 `APIResponse`：

```json
{
  "status": "success",
  "message": "plugin install task started",
  "data": {
    "task_id": "xxx",
    "state": "installing",
    "log_stream": "/api/plugins/<id>/install/log/stream/xxx"
  }
}
```

---

## 7. 任务与日志规范

### 7.1 任务元数据

插件安装任务必须写入统一 `Task.metadata` 字段：

- `kind`: `plugin_install`
- `plugin_id`
- `phase`
- `plan`（可选）

### 7.2 日志要求

- 必须进入 `train_log_hub`，支持 SSE 实时查看
- 必须支持 tail 回读（供控制台页面恢复历史）
- 关键阶段必须有 `[phase]`/`[ready]`/`[error]` 标记

---

## 8. 安全与隔离

### 8.1 执行隔离

- 插件依赖优先独立 venv
- 默认 `PYTHONNOUSERSITE=1`
- 插件子进程不得继承不必要的敏感环境变量

### 8.2 权限声明与提示

- 安装前显示插件权限摘要（网络、子进程、GPU、磁盘路径）
- 对社区插件（未来阶段）默认标记「未受信任」

### 8.3 故障熔断

- 连续安装失败达到阈值（例如 3 次）自动标记 `broken` 并提示人工介入
- 插件故障不得阻断主训练功能

---

## 9. 前端交互规范

1. 左侧一级目录提供 `插件` 分组。
2. 插件卡片至少展示：名称、版本、状态、最后审计时间。
3. 统一按钮语义：`安装` / `修复` / `卸载` / `查看日志`。
4. 训练页若依赖插件，只做「状态提示 + 跳转插件管理」，不重复安装逻辑。
5. 侧栏可标「插件 / 进阶 · 可选」；未就绪时训练按钮禁用并链到插件页。

---

## 10. 版本策略

### 10.1 Core 与插件兼容

- 插件声明 `min_core_version`
- Core 可声明不兼容插件版本范围并阻止启动

### 10.2 升级策略

- Core 升级后，首次进入插件页触发一次 `audit`
- 审计失败自动转 `broken`，引导修复

---

## 11. 落地阶段（建议）

### Phase A（当前）

- 新增「插件」一级菜单
- 将 Anima Fast 迁入统一插件管理页（训练页仅保留入口）
- 统一状态机与日志入口

### Phase B

- 抽象 `PluginManager`（后端统一注册、安装、审计）
- 接入标签编辑器插件化（同生命周期；先软边缘化导航，再可选安装）

### Phase C

- 支持社区插件（默认关闭）
- 引入签名/白名单/风险提示机制

---

## 12. 非目标（v0.1 不做）

- 不做插件脚本任意执行沙箱
- 不做插件市场/在线商店
- 不做跨机器插件同步

---

## 13. 与现有文档关系

- 路由与端口标准：`docs/design/ports/port-interface-standard.md`
- Fast 插件现状：`docs/anima-fast.md`
- 仓库路径契约：`docs/repo-layout.md`

本规范优先定义「插件平台共性」；具体插件实现细节可在各插件文档补充。
