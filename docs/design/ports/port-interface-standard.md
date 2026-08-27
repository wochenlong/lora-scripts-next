# 标准端口与接口规范

## 目的

本文档是 lora-scripts-next 的长期技术规范，用于约束当前功能、未来新功能、插件、内置工具和第三方集成的端口、路径、服务发现、接口输出、健康检查和自动化验收方式。

本文档只定义标准，不描述当前仓库如何改造。当前项目的落地步骤见 [`port-routing-migration-plan.md`](port-routing-migration-plan.md)。

## 基本原则

1. 用户默认只访问一个公共入口。
2. 所有用户可见服务都必须通过路径路由暴露。
3. 子服务可以有内部端口，但内部端口不得作为普通用户入口。
4. 前端、文档、插件和日志不得硬编码子服务端口。
5. 所有服务都必须有服务 ID、正式路径、内部上游、健康检查和注册表记录。
6. 服务是否可用不能只靠端口连通判断，必须校验服务身份。
7. 公共 URL 和内部 URL 必须分离，不能混用。
8. 源码启动、整合包启动、AutoDL / 云端启动必须遵守同一套端口契约。

## 架构模型

标准架构如下：

```text
用户 / 浏览器 / AutoDL / 反向代理
        |
        | public_base_url，默认 http://127.0.0.1:28000
        v
公共入口 / 主应用 / 网关
        |
        | 按路径转发
        v
127.0.0.1 内部服务端口池
```

默认公共入口：

```text
http://127.0.0.1:28000/
```

默认路径：

```text
/              WebUI
/api/          API
/tensorboard/  TensorBoard
/monitor/      训练监控页
/tagger/       Dataset Tag Editor
```

## 术语

| 术语 | 定义 |
|---|---|
| 公共入口端口 | 用户、浏览器、AutoDL、反向代理访问的入口端口。默认 `28000`。 |
| 公共基础 URL | 对用户和前端展示的基础地址，例如 `http://127.0.0.1:28000` 或 AutoDL 平台外部地址。 |
| 正式路径 | 某个服务对外暴露的标准路径，例如 `/monitor/`。 |
| 内部端口 | 子服务实际监听的本机端口，例如 `28120`。 |
| 内部上游 | 网关代理到的真实地址，例如 `http://127.0.0.1:28120`。 |
| 服务 ID | 服务的稳定机器标识，例如 `train-monitor`。 |
| 服务注册表 | 运行时生成的服务清单，记录 public URL、internal URL、端口、状态、诊断信息。 |
| 服务身份健康检查 | 用于确认某端口上运行的是目标服务，而不是另一个误占端口的服务。 |

## 路径优先标准

本项目只采用路径路由作为标准服务暴露方式。

不再把子域名作为规范路径。未来功能、新插件、新服务不得要求用户配置 DNS、hosts、通配证书或子域名才能完成基本使用。

路径路由的理由：

- 本地、便携包和 AutoDL 使用成本最低。
- 只需要映射一个公共入口端口。
- 与当前 `/proxy/tensorboard/`、`/proxy/tageditor/`、`/train-log` 的迁移方向一致。
- 更适合训练工具、整合包和受限云端环境。

## 服务路径规范

### 标准路径表

| 正式路径 | 服务 ID | 类型 | 说明 |
|---|---|---|---|
| `/` | `webui` | 页面 | WebUI 和前端静态资源 |
| `/api/` | `api` | HTTP API | REST API、训练任务、配置、服务发现 |
| `/train-log` | `train-log` | 页面 | WebUI 内嵌训练日志页 |
| `/api/train/log/stream/` | `train-log-stream` | SSE | 训练日志流 |
| `/tensorboard/` | `tensorboard` | 页面 / 代理 | TensorBoard |
| `/monitor/` | `train-monitor` | 页面 / API | 训练监控页 |
| `/tagger/` | `tag-editor` | 页面 / WebSocket | Dataset Tag Editor |
| `/daemon/` | `anima-daemon` | RPC | 默认不面向普通用户开放 |

### 路径命名空间

项目保留以下顶层路径命名空间：

| 命名空间 | 用途 | 新功能是否可占用 |
|---|---|---|
| `/` | WebUI 前端和静态资源 | 否，除前端路由外不得新增后端服务 |
| `/api/` | 项目公共 HTTP API | 可以，但必须遵守 API 版本和命名规则 |
| `/assets/` | 静态资源 | 否，除静态资源服务外不得占用 |
| `/tensorboard/` | TensorBoard | 否 |
| `/monitor/` | 训练监控页 | 否 |
| `/tagger/` | Dataset Tag Editor | 否 |
| `/daemon/` | 本地 daemon RPC | 受限，需要安全评审 |
| `/plugins/` | 插件页面入口 | 可以，插件页面优先使用 |
| `/api/engines/` | 训练引擎 API 入口 | 训练引擎 API 必须使用（#302 起，统一为 `/api/engines/<engine-id>/*`） |
| `/api/plugins/` | 插件 API 入口 | 可以，非训练引擎的插件 API 使用 |
| `/diagnostics/` | 人类可读诊断页面 | 可以，但不得暴露敏感信息 |
| `/api/diagnostics/` | 机器可读诊断 API | 可以，需要权限控制 |

未来新页面服务优先使用：

```text
/plugins/<plugin-id>/
```

未来新插件 API 优先使用：

```text
/api/plugins/<plugin-id>/
```

核心功能 API 优先使用：

```text
/api/<resource>
```

需要版本化的新公共 API 应使用：

```text
/api/v1/<resource>
```

### 命名规则

新增服务路径必须满足：

- 使用小写英文。
- 使用短横线连接多个单词，例如 `/model-browser/`。
- 页面入口使用名词路径。
- HTTP API 放在 `/api/` 下。
- 流式接口、WebSocket、RPC 必须登记接口类型。
- 不允许把端口号写入路径，例如 `/tensorboard-6006/`。
- 不允许使用 `/proxy/<name>/` 作为新服务的正式路径。
- 不允许同一服务存在多个正式路径；兼容路径必须标注 deprecation。
- 路径中的动态参数必须使用资源名，不得暴露本机路径、端口或进程 ID。
- 路径应表达资源和能力，不表达实现细节，例如用 `/api/services`，不用 `/api/read-services-json`。

### API 版本规则

现有 API 可以保持当前路径。新增稳定公共 API 应优先使用 `/api/v1/`。

规则：

- `/api/` 下现有接口保持兼容，不强制立即迁移。
- 新增跨版本会被外部插件依赖的接口，应放在 `/api/v1/`。
- 实验性接口必须放在 `/api/experimental/`，并在文档中标注不保证兼容。
- 内部调试接口必须放在 `/api/diagnostics/`，生产或公网环境需要权限保护。
- API 返回 JSON 字段使用 snake_case。
- API 不得返回让调用方自行拼接的裸端口。
- API 如果返回 URL，必须同时说明 `public_url` 或 `internal_url` 的用途。

推荐路径：

| 类型 | 示例 |
|---|---|
| 服务发现 | `/api/services` |
| 诊断 | `/api/diagnostics/ports` |
| 插件列表 | `/api/v1/plugins` |
| 插件 API | `/api/plugins/model-browser/indexes` |
| 实验接口 | `/api/experimental/<feature>` |

### 尾斜杠规则

页面型服务必须使用尾斜杠：

```text
/tensorboard/
/monitor/
/tagger/
```

无尾斜杠访问必须 `302` 到尾斜杠版本：

```text
/tensorboard -> /tensorboard/
/monitor -> /monitor/
/tagger -> /tagger/
```

API 路径不强制尾斜杠，遵守 FastAPI 当前行为。

## 端口分配规范

### 端口分层

| 范围 | 用途 | 规则 |
|---:|---|---|
| `28000-28020` | 公共入口端口和本地 fallback | 只允许公共入口 / 网关使用。 |
| `28100-28199` | 项目内部 HTTP / WebSocket / RPC 上游 | 只绑定回环地址，必须注册。 |
| `28200-28299` | 临时开发和自动化测试端口 | 只用于测试、Playwright、临时 dev server。 |
| `6000-6999` | 历史兼容端口 | 不再新增长期服务。 |
| `8000-8999` | 外部第三方工具端口 | 仅记录，不纳入默认托管。 |

端口范围之外的长期服务必须经过规范更新。不得在代码中临时选择一个“看起来没人用”的端口并合入。

### 内部端口池

| 服务 ID | 推荐内部端口 | fallback 范围 | 历史端口 |
|---|---:|---|---:|
| `webui` / `api` | `28100` | `28100-28109` | `28000` |
| `tensorboard` | `28110` | `28110-28119` | `6006` |
| `train-monitor` | `28120` | `28120-28129` | `6008` |
| `tag-editor` | `28130` | `28130-28139` | `28001` |
| `anima-daemon` | `28140` | `28140-28149` | `8765` |
| 新插件 / 新服务 | 需登记 | 需登记独立范围 | 无 |

规则：

- 内部服务端口被占用时，只能在本服务 fallback 范围内查找。
- 不允许 TensorBoard fallback 到训练监控端口池。
- 不允许训练监控 fallback 到 TensorBoard 端口池。
- 不允许任何子服务占用公共入口端口池。
- 新插件需要长期后台服务时，必须先申请服务 ID 和内部端口范围。
- 端口分配结果必须记录来源，例如 `default`、`default-fallback`、`explicit`、`explicit-auto-fallback`。
- 当端口由用户显式指定时，启动日志必须展示“显式配置来源”。

## 公共入口端口策略

公共入口端口采用“双模式”。

### 默认本地模式

当用户没有显式指定公共入口端口时：

- 默认尝试 `28000`。
- 如果 `28000` 被占用，自动 fallback 到 `28000-28020`。
- fallback 后必须更新公共基础 URL、服务注册表、启动日志和浏览器打开地址。
- 不允许前端、日志或文档继续展示旧端口。

### 显式端口严格模式

当用户通过命令行、环境变量或配置文件显式指定公共入口端口时：

- 端口被占用时默认启动失败。
- 不允许静默 fallback。
- 必须输出明确诊断。
- 如需自动选择，用户必须显式开启 `--auto-public-port` 或 `LORA_AUTO_PUBLIC_PORT=1`。

该模式适用于 AutoDL、云端、反向代理和固定端口映射场景。

## 配置命名规范

### 标准配置

| 配置项 | 环境变量 | 命令行参数 | 默认值 |
|---|---|---|---|
| 公共入口 Host | `LORA_GATEWAY_HOST` | `--gateway-host` | `127.0.0.1` |
| 公共入口端口 | `LORA_GATEWAY_PORT` | `--gateway-port` | `28000` |
| 是否允许公共入口 fallback | `LORA_AUTO_PUBLIC_PORT` | `--auto-public-port` | 本地默认隐式开启，显式端口默认关闭 |
| 公共基础 URL | `LORA_PUBLIC_BASE_URL` | `--public-base-url` | 根据实际公共入口生成 |
| WebUI 内部端口 | `LORA_WEBUI_PORT` | `--webui-port` | `28100` |
| TensorBoard 内部端口 | `LORA_TENSORBOARD_PORT` | `--tensorboard-port` | `28110` |
| 训练监控内部端口 | `LORA_TRAIN_MONITOR_PORT` | `--train-monitor-port` | `28120` |
| Dataset Editor 内部端口 | `LORA_TAG_EDITOR_PORT` | `--tag-editor-port` | `28130` |
| Anima daemon 内部端口 | `LORA_ANIMA_DAEMON_PORT` | `--anima-daemon-port` | `28140` |

### 兼容配置

| 旧变量 / 参数 | 新配置 | 策略 |
|---|---|---|
| `MIKAZUKI_PORT` / `--port` | `LORA_GATEWAY_PORT` | 迁移期继续支持，作为公共入口端口 |
| `MIKAZUKI_HOST` / `--host` | `LORA_GATEWAY_HOST` | 迁移期继续支持 |
| `MIKAZUKI_TENSORBOARD_PORT` / `--tensorboard-port` | `LORA_TENSORBOARD_PORT` | 迁移期继续支持 |
| `TRAIN_MONITOR_PORT` / `--train-monitor-port` | `LORA_TRAIN_MONITOR_PORT` | 迁移期继续支持 |
| `MIKAZUKI_TAGEDITOR_PORT` | `LORA_TAG_EDITOR_PORT` | 迁移期继续支持 |
| `ANIMA_DAEMON_PORT` | `LORA_ANIMA_DAEMON_PORT` | 迁移期继续支持 |

新代码应优先读标准配置。兼容配置只用于迁移，不应在新功能中扩散。

## 服务注册表规范

运行时必须生成服务注册表：

```text
.runtime/services.json
```

### Schema

```json
{
  "schema_version": 1,
  "mode": "local-default",
  "generated_at": "2026-05-26T12:00:00+08:00",
  "gateway": {
    "host": "127.0.0.1",
    "port": 28002,
    "public_base_url": "http://127.0.0.1:28002",
    "port_source": "default-fallback"
  },
  "services": {
    "service-id": {
      "public_path": "/service/",
      "public_url": "http://127.0.0.1:28002/service/",
      "internal_url": "http://127.0.0.1:28150",
      "port": 28150,
      "status": "ok",
      "kind": "page",
      "requires_auth": false,
      "capabilities": ["http"],
      "health": {
        "checked": true,
        "service": "service-id",
        "checked_at": "2026-05-26T12:00:01+08:00"
      }
    }
  }
}
```

### 状态值

| 状态 | 含义 |
|---|---|
| `ok` | 服务启动且身份健康检查通过。 |
| `starting` | 服务启动中，尚未可用。 |
| `failed` | 服务启动失败或健康检查失败。 |
| `disabled` | 用户显式禁用服务。 |

### 要求

- 注册表是运行时唯一事实来源。
- 前端配置、启动日志、代理路由、自动打开浏览器、测试都必须读取同一份注册结果。
- 服务身份健康检查通过前，不得标记为 `ok`。
- 非核心服务失败时应登记为 `failed`，公共路径返回明确诊断。
- 注册表写入必须尽量原子化，避免前端读到半写入文件。
- 注册表 schema 变更必须增加 `schema_version`，并提供兼容读取。
- 注册表不得包含访问令牌、用户隐私、模型密钥或其他敏感信息。
- 注册表路径不得被前端作为静态文件直接读取，应由后端受控 API 暴露必要字段。

### 生命周期

注册表生命周期：

```text
starting -> ok
starting -> failed
ok -> failed
failed -> starting -> ok
disabled
```

要求：

- 子服务重启后必须刷新注册表。
- 子服务端口 fallback 后必须刷新注册表。
- 公共入口 fallback 后必须刷新所有 public URL。
- 停止服务时应清理或标记注册表，避免下次启动读取陈旧状态。
- 如果检测到注册表进程信息和当前进程不匹配，必须重新生成。

### 对外服务发现 API

推荐提供：

```text
GET /api/services
```

返回给前端的内容应过滤内部敏感字段：

```json
{
  "public_base_url": "http://127.0.0.1:28002",
  "services": {
    "tensorboard": {
      "public_path": "/tensorboard/",
      "public_url": "http://127.0.0.1:28002/tensorboard/",
      "status": "ok"
    }
  }
}
```

调试接口可提供内部 URL，但应放在 `/api/diagnostics/` 并受权限保护。

## 服务身份健康检查规范

仅检查端口可连接不合格。必须确认端口上运行的是目标服务。

### 标准端点

本项目自有服务必须提供：

```text
GET /__lora_service_health
```

返回：

```json
{
  "service": "train-monitor",
  "status": "ok",
  "version": "optional",
  "pid": 12345,
  "capabilities": ["http"],
  "started_at": "2026-05-26T12:00:00+08:00"
}
```

`service` 必须等于服务注册表中的服务 ID。

### 第三方服务适配

无法实现标准健康端点的第三方服务，必须由启动器提供身份适配检查：

| 服务 | 身份检查要求 |
|---|---|
| TensorBoard | 能识别 TensorBoard 页面或接口特征，且不得误识别训练监控页。 |
| Gradio Tag Editor | 能识别 Gradio / Tag Editor 页面或队列接口特征。 |
| Anima daemon | 必须提供或适配轻量状态接口，返回 daemon 服务 ID。 |

### 失败处理

| 失败类型 | 标准行为 |
|---|---|
| 端口无法连接 | 标记服务 `failed`，公共路径返回明确 502。 |
| 服务 ID 不匹配 | 不得注册该端口为目标服务。 |
| 响应为另一个已知服务 | 明确报错，例如 `28120 is tensorboard, expected train-monitor`。 |
| 超时 | 重试有限次数，仍失败则标记 `failed`。 |

### 能力声明

健康检查可以声明能力：

| 能力 | 含义 |
|---|---|
| `http` | 普通 HTTP 请求 |
| `websocket` | WebSocket |
| `sse` | Server-Sent Events |
| `static` | 静态资源 |
| `rpc` | RPC / daemon 调用 |
| `filesystem` | 涉及文件系统访问 |
| `training-control` | 能启动、停止或修改训练任务 |

带有 `filesystem`、`training-control`、`rpc` 的服务在公网环境必须受权限保护。

## 接口输出规范

所有返回服务地址的 API 必须返回结构化字段：

```json
{
  "service": "train-monitor",
  "public_path": "/monitor/",
  "public_url": "http://127.0.0.1:28002/monitor/",
  "internal_url": "http://127.0.0.1:28120",
  "status": "ok"
}
```

规则：

- 前端只能使用 `public_path` 或 `public_url`。
- 内部服务调用只能使用 `internal_url`。
- 普通用户界面不得展示 `internal_url` 作为入口。
- 不允许 API 只返回裸端口再让调用方拼 URL。
- JSON 字段命名使用 snake_case。

### 错误响应

端口、代理、健康检查相关错误推荐使用统一格式：

```json
{
  "error": {
    "code": "service_unavailable",
    "message": "Train monitor is not available",
    "service": "train-monitor",
    "public_path": "/monitor/",
    "internal_url": "http://127.0.0.1:28120",
    "diagnostic": "expected train-monitor, got tensorboard"
  }
}
```

规则：

- `message` 面向用户，可本地化。
- `diagnostic` 面向排障，不应包含密钥或隐私信息。
- `code` 使用小写 snake_case。
- 代理失败不得只返回纯文本 “Service not started”。

## 前端集成规范

前端不得硬编码子服务端口。

推荐前端配置对象：

```json
{
  "publicBaseUrl": "http://127.0.0.1:28002",
  "services": {
    "webui": "/",
    "api": "/api/",
    "tensorboard": "/tensorboard/",
    "trainMonitor": "/monitor/",
    "tagEditor": "/tagger/"
  }
}
```

前端拼接 URL 必须使用 `new URL(path, publicBaseUrl)` 或等价方式。

禁止硬编码：

```text
http://127.0.0.1:6008
http://127.0.0.1:6006
http://127.0.0.1:28001
ws://127.0.0.1:28001/queue/join
```

### 前端降级

当某个非核心服务状态为 `failed` 或 `disabled`：

- 前端应禁用对应入口或显示明确错误。
- 前端不得自行猜测旧端口。
- 前端不得把用户引导到内部端口。
- 前端可以提供“查看诊断”入口，但应指向公共路径或诊断 API。

## 代理规范

### 必须支持

路径代理必须支持：

- HTTP `GET`
- HTTP `POST`
- 静态资源
- 流式响应
- SSE
- WebSocket upgrade
- 必要的路径前缀重写
- 明确的 502 诊断页面

### 代理行为

代理层必须：

- 从服务注册表读取上游。
- 不访问未注册上游。
- 不允许用户通过 query 参数指定任意上游。
- 在上游状态不是 `ok` 时返回明确诊断。
- 保留必要请求头，移除危险 hop-by-hop 头。
- 对 WebSocket 和 SSE 保持流式转发。
- 对大型响应避免一次性读入内存。

### 代理头

转发到内部服务时，应透传或注入：

```text
Host: <原始 Host>
X-Forwarded-Host: <原始 Host>
X-Forwarded-Port: <公共入口端口>
X-Forwarded-Proto: http 或 https
X-Forwarded-Prefix: <路径前缀>
X-Request-ID: <请求唯一 ID>
```

### TensorBoard

TensorBoard 必须通过 `/tensorboard/` 暴露。实现必须满足：

- 页面可打开。
- 静态资源不跳到 `/`。
- 重定向不跳到 `6006`。
- event 数据读取正常。
- 失败时公共路径返回明确诊断。

### Gradio / Dataset Tag Editor

Dataset Tag Editor 必须通过 `/tagger/` 暴露。Gradio 启动必须使用：

```text
--root-path /tagger
```

WebSocket 队列接口必须通过公共入口正常代理。

## 插件开发规范

新增插件如果需要后台服务，必须先登记：

| 项 | 要求 |
|---|---|
| 服务 ID | 全局唯一，使用小写短横线，例如 `model-browser`。 |
| 正式路径 | 页面服务使用 `/plugin-name/`；API 使用 `/api/plugin-name/`。 |
| 内部端口 | 使用登记的内部端口池，不得抢占已有服务范围。 |
| 健康检查 | 必须提供 `/__lora_service_health`。 |
| 前端入口 | 必须从服务注册表或前端配置读取。 |
| WebSocket / SSE | 必须在服务登记中声明。 |
| 安全边界 | 不得默认暴露文件系统、训练控制、daemon 能力。 |

插件不得要求用户手动记忆或访问插件内部端口。

### 插件服务声明

插件应提供服务声明，字段建议如下：

```json
{
  "service_id": "model-browser",
  "public_path": "/plugins/model-browser/",
  "api_path": "/api/plugins/model-browser/",
  "preferred_port": 28150,
  "port_range": [28150, 28159],
  "capabilities": ["http", "static"],
  "requires_auth": false,
  "health_path": "/__lora_service_health"
}
```

规则：

- `service_id` 全局唯一。
- `public_path` 不得和核心路径冲突。
- `port_range` 不得和已有服务冲突。
- `capabilities` 必须真实反映服务能力。
- 插件启用、禁用、失败状态必须写入服务注册表。

### 插件安全分级

| 分级 | 能力 | 要求 |
|---|---|---|
| Level 0 | 纯静态 UI，无后端 | 不需要内部端口 |
| Level 1 | HTTP 只读 API | 需要服务注册和健康检查 |
| Level 2 | WebSocket / SSE / 长任务 | 需要代理测试和资源释放测试 |
| Level 3 | 文件系统 / 训练控制 / daemon | 需要权限控制和安全评审 |

## AutoDL / 云端规范

AutoDL 和云端部署必须支持：

- 显式设置公共入口端口。
- 显式设置公共基础 URL。
- 显式设置每个子服务内部端口。
- 显式端口被占用时默认失败。
- 日志展示平台可访问 URL。

如果平台只能映射一个端口，只映射公共入口端口。TensorBoard、训练监控、Dataset Tag Editor 不要求单独映射。

云端部署不得依赖本机浏览器自动打开。启动日志必须清楚展示平台可访问 URL。

## 错误诊断规范

错误必须具体到服务、端口、路径和原因。

合格错误示例：

```text
Train monitor failed:
expected service: train-monitor
requested internal port: 28120
actual response: tensorboard
public path: /monitor/
suggestion: stop the process on 28120 or choose --train-monitor-port 28121
```

不合格错误示例：

```text
无法连接
HTTP Error 404
Service not started
连接 6006 GUI API 失败
```

## 观测与诊断规范

建议提供诊断接口：

```text
GET /api/diagnostics/ports
GET /api/diagnostics/services
```

诊断信息应包括：

- 公共入口端口及来源。
- 每个服务的请求端口、实际端口、fallback 情况。
- 服务状态。
- 健康检查结果。
- 最近一次错误原因。
- 进程 ID。

日志应包含：

- `request_id`
- `service_id`
- `public_path`
- `internal_url`
- `port_source`
- `health_status`

生产或公网环境下，诊断接口必须受权限保护，并避免泄露本机敏感路径。

## 兼容与废弃规范

旧路径、旧环境变量、旧端口入口不能无限期存在。

废弃流程：

```text
兼容引入 -> 日志提示 -> 文档标记 deprecated -> 发布说明提醒 -> 移除
```

每个 deprecated 项必须登记：

| 字段 | 说明 |
|---|---|
| 旧入口 | 例如 `/proxy/tageditor/` |
| 替代入口 | 例如 `/tagger/` |
| 兼容开始版本 | 首个标记 deprecated 的版本 |
| 计划移除版本 | 预计删除版本 |
| 风险 | 删除可能影响的用户 |

旧端口 `6006`、`6008`、`28001` 可作为诊断入口短期保留，但不得作为普通用户入口。

## 安全规范

- 子服务默认不得绑定 `0.0.0.0` 对外暴露。
- 远程访问只能经过公共入口。
- `/daemon/` 默认不面向普通用户开放。
- 生产或公网环境必须启用认证，至少保护 `/api/`、`/monitor/`、`/tagger/`、`/daemon/`。
- 代理必须限制可访问上游，禁止开放式 forward proxy。
- 文件预览、日志读取、模型下载等接口必须保持路径沙箱限制。

### 认证分级

| 路径 | 本地默认 | 公网 / 云端 |
|---|---|---|
| `/` | 可匿名 | 建议认证 |
| `/api/` | 可匿名 | 必须认证 |
| `/tensorboard/` | 可匿名 | 建议认证 |
| `/monitor/` | 可匿名 | 必须认证 |
| `/tagger/` | 可匿名 | 必须认证 |
| `/daemon/` | 默认关闭 | 必须认证且默认关闭 |
| `/api/diagnostics/` | 可本地访问 | 必须认证 |

任何能读写文件、启动训练、停止训练、访问模型路径、访问日志尾部的接口，在公网环境必须受权限保护。

## 新服务评审清单

新增任何 HTTP、WebSocket、SSE、RPC 或 daemon 服务前，必须回答：

1. 服务 ID 是什么？
2. 对外正式路径是什么？
3. 是否需要普通用户访问？
4. 内部端口和 fallback 范围是什么？
5. 是否需要公共入口端口之外的外部映射？如果需要，为什么？
6. 调用方如何通过服务注册表发现它？
7. 是否提供 `/__lora_service_health`？
8. 是否需要 WebSocket、SSE、大文件上传、长轮询或路径重写？
9. API 输出是否返回结构化 `public_path` / `public_url` / `internal_url`？
10. 文档是否避免展示内部端口作为普通用户入口？
11. 测试是否覆盖端口占用、路径代理、健康检查、WebSocket/SSE 和尾斜杠跳转？

未完成登记的服务不得合入主分支。
