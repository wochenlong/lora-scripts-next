# 前端缓存生命周期治理设计书（待审核）

## 1. 目的与范围

本设计把“切换页面或数据后前端缓存被清空”作为全局状态生命周期问题处理。它覆盖 Dataset Editor、标签翻译、Schema 缓存、训练草稿与历史、UI 偏好、插件状态和任务状态的缓存边界，不把修复限制在 tag 翻译组件。

本轮目标是建立统一的状态分类、缓存键、失效入口和测试规则，再据此分批迁移现有代码。设计审核通过前不改变运行代码。

数据集编辑器的详细恢复契约见[数据集模块状态保持与编辑器恢复设计](dataset-module-state-retention-design.md)。当前施工范围以数据集模块为主，标签翻译作为其中一个资源缓存域。

约束如下：

- 原始 caption、训练输入和用户已保存配置不能因为页面切换而丢失。
- 页面视图状态可以在离开页面时清理，但必须与资源缓存、持久数据分开。
- 取消旧请求只影响请求和展示订阅，不删除已经成功的缓存结果。
- 不允许在生产代码中使用 `localStorage.clear()`、`sessionStorage.clear()` 或无范围的全局缓存清空。
- 现有 storage key 和后端接口保持兼容，迁移需要显式版本和幂等处理。

## 2. 已确认的根因

### 2.1 当前代码证据

- `frontend/src/pages/DatasetEditorPage.vue` 的 `choose()` 同时设置 `showTranslations=false` 和调用 `clearTranslations()`。切图时“隐藏释义”和“删除全部译文”没有分开。
- `frontend/src/composables/useTagTranslations.ts` 在每次调用 composable 时创建独立 `entries`，缓存只存在组件实例内；`clear()` 会直接替换为空对象。
- `DatasetPage.vue` 使用 `KeepAlive` 只保留数据集三个页签。其他路由切换通常会卸载页面，页面私有 `ref` 会自然丢失。
- 生产前端未发现无范围的 `localStorage.clear()` 或 `sessionStorage.clear()`；测试文件中的清空调用只用于隔离测试。
- Schema loader、主题、路径选择、下载源、训练草稿和训练历史采用不同的 storage key，没有统一的命名空间、版本和失效接口。
- 任务、Tagger、插件等 Pinia store 具有跨组件生命周期，但页面级状态与 store 状态的保留规则没有统一文档和测试。

### 2.2 需要避免的错误修复

- 只删除 `clearTranslations()` 会留下其他 composable 继续混用 `clear`、`reset` 和 `cancel` 的问题。
- 把所有状态提升到 Pinia 会让临时表单、弹窗和筛选条件变成难以清理的全局状态。
- 把全部状态写入 localStorage 会造成敏感数据、过期数据和大对象膨胀，也会把临时 UI 状态错误地持久化。

## 3. 统一状态分类

| 类别 | 例子 | 默认生命周期 | 允许的清理方式 |
| --- | --- | --- | --- |
| 视图临时状态 | 弹窗、当前 tab、hover、loading、当前选中项、筛选输入 | 组件卸载或显式离开上下文 | `resetView()`，只清当前实例 |
| 资源缓存 | 标签译文、Schema source、插件目录、可复用 API 结果 | 模块/应用生命周期，可按键复用 | `invalidate(key)`、TTL/版本失效、用户明确清理 |
| 用户持久数据 | 训练草稿、训练历史、主题、UI 偏好、最近选择 | 跨路由和浏览器重启 | `remove(key)` 或针对单项的迁移/删除 |
| 请求控制状态 | AbortController、请求代次、in-flight map | 当前请求或当前资源键 | `cancelRequest(key)`；不得清缓存 |
| 后端持久结果 | Danbooru 词库、翻译 SQLite、任务记录 | 后端数据生命周期 | 后端明确 API 或维护操作 |

`clear` 只允许用于“用户明确要求删除数据”的动作；代码中用于切图的函数应改成 `cancelRequest`、`resetView` 或 `invalidateResource`，名称必须表达作用域。

## 4. 建议的前端缓存边界

### 4.1 应用级资源缓存注册表

新增轻量的前端缓存工具（建议位置 `frontend/src/state/resourceCache.ts`），不引入新的状态管理框架。每个资源通过以下信息建立键：

```text
domain + scope + identity + locale/provider/profile + schemaVersion
```

工具提供四类操作：

- `get/set`：读取和写入成功结果；
- `invalidate(key|domain)`：标记结果过期但不影响其他域；
- `clearDomain(domain)`：仅供设置页的明确清理操作；
- `cancelRequest(key)`：取消当前请求并递增请求代次。

缓存值和请求状态分开保存。失败、超时、未配置和取消不会覆盖最后一次成功结果；错误只在当前请求上下文中显示。

内存缓存有容量上限和可选 TTL。淘汰只删除浏览器内存条目，不删除后端 SQLite 或用户持久数据。

### 4.2 持久化存储包装器

新增 `frontend/src/state/persistedState.ts`，集中处理 JSON 编码、版本、损坏值回退和单 key 删除。现有 key 保留兼容读取，新的写入增加版本字段或独立版本 key。

包装器禁止暴露全局 `clear()`，只暴露：

- `read(key, decoder)`；
- `write(key, value)`；
- `remove(key)`；
- `migrate(key, version, callback)`。

这样可以保证修改语言、主题或路径选择时不会覆盖同一 `ui-configs` 中的其他字段，也不会清理训练草稿和资源缓存。

## 5. 各模块迁移规则

### 5.1 Dataset Editor 与标签翻译

- `choose()` 只更新当前图片、caption 和视图状态；不再清空翻译资源缓存。
- 译文键至少包含 raw tag、locale、provider、profile revision 和 normalization version。
- 切图时先读本地内存/后端缓存；外部翻译只由明确的“翻译缺失项”动作触发。
- 当前图片切换产生新的展示代次，旧请求可以完成写入缓存，但不能更新新图片的展示状态。
- `showTranslations` 只保存开关偏好；关闭开关不删除成功译文。

### 5.2 Schema loader

- Schema source 属于资源缓存，不因进入训练页或切换训练模式而清空。
- 仅当后端 hash 变化、schema 版本变化或用户明确刷新时失效。
- 保留旧 `localStorage.schemas` 读取兼容；损坏值只删除该 key。

### 5.3 训练草稿与历史

- autosave 和 history 继续按 schema/model 独立 key 保存。
- 切换训练页面只停止当前页面轮询，不删除草稿或历史。
- 应用 preset 时只替换当前表单模型；是否覆盖 autosave 必须由已有明确保存语义决定。
- 导入的 sessionStorage 数据只在成功消费后删除对应 key，不能清空整个 sessionStorage。

### 5.4 UI 偏好、主题和路径选择

- 保持现有 `ui-configs`、主题、路径选择和下载源 key。
- 更新单字段时使用读-改-写并保留未知字段。
- “恢复默认设置”只删除该设置域，不能影响训练草稿、Schema 或资源缓存。

### 5.5 Pinia store、插件和任务

- Tasks、Tagger、Extensions store 的 `refresh()` 只替换服务端快照；请求失败时保留最后成功快照并显示错误。
- 页面离开时停止 timer/SSE 属于请求控制清理，不得把 store 数据重置为空。
- 插件窗口关闭只清理当前连接和面板几何偏好；插件目录和扩展清单按照资源缓存规则失效。

## 6. API 与命名约定

禁止新增语义模糊的 `clear()`。推荐使用：

| 旧式意图 | 新命名 | 影响范围 |
| --- | --- | --- |
| 清理当前显示 | `resetView()` | 当前组件实例 |
| 停止旧请求 | `cancelRequest(key)` | 当前请求 |
| 结果过期 | `invalidate(key)` | 指定资源键 |
| 用户删除缓存 | `clearDomain(domain)` | 一个明确资源域 |
| 删除设置 | `removePersisted(key)` | 一个 storage key |

API 返回的资源结果应带 revision/version。前端发现版本不一致时只失效对应域，不重置全局状态。

## 7. 测试与验收

### 7.1 单元与 composable 测试

- `cancelRequest` 不删除已有成功缓存。
- `invalidate(tag:blue_eyes)` 不影响 Schema、训练草稿和其他标签。
- 同一个资源键的并发请求只产生一个 in-flight 请求。
- 旧请求完成后不能覆盖新上下文的 loading/error/展示结果。
- 损坏的单个 storage key 被隔离处理，其他 key 保留。
- 删除某个设置域不会影响其他持久数据。

### 7.2 页面验收

- Dataset Editor：A→B→A，释义、caption 和筛选行为按设计恢复；关闭/开启释义不丢译文。
- 路由：Dataset、Training、Tasks、Settings 往返切换，训练草稿、主题、Schema 和任务快照不被无关页面清理。
- 刷新：浏览器刷新后恢复明确标记为持久化的数据；临时弹窗和 loading 不恢复。
- 请求竞态：延迟旧请求不会污染新页面或新图片。
- 原文保护：任何缓存操作不改写 caption 文件、训练配置和导出内容。

### 7.3 静态检查

- 生产 `frontend/src` 禁止 `localStorage.clear()`、`sessionStorage.clear()`。
- 资源 composable 不得导出无作用域的 `clear()`。
- 每个 `removeItem` 必须对应一个明确 storage key，并有测试说明删除原因。
- `npm run check`、相关 Vitest、后端翻译/数据集测试和真实浏览器往返验收全部通过。

## 8. 实施顺序

1. 建立缓存分类表、键清单和静态检查规则。
2. 实现 `resourceCache` 与 `persistedState` 的最小 API，并增加生命周期测试。
3. 迁移 `useTagTranslations` 和 Dataset Editor，验证 A→B→A、刷新和并发竞态。
4. 迁移 Schema、训练草稿/历史、UI 偏好、Tasks/Tagger/Extensions 中的缓存和刷新语义。
5. 清理模糊命名，补齐页面往返和单 key 删除测试。
6. 运行完整检查，更新原 tag 翻译设计书和发布审计。

## 9. 待审核决定

1. 接受“资源缓存跨路由保留，视图临时状态按上下文清理”的全局边界。
2. 接受新增两个轻量工具模块，不引入 Pinia 持久化插件或新的数据库。
3. 接受网络/LLM/词库结果按资源键失效，用户清理只作用于指定 domain。
4. 接受先迁移标签翻译作为示范，再批量迁移其余模块；迁移期间保持现有 storage key 和 API 兼容。
