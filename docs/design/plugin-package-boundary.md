# 插件源码、核心包与运行时目录边界

## 状态

本文件定义 Next Trainer 通用插件宿主与独立插件交付物之间的目录和打包边界。首个使用该边界的独立包是 `next-trainer-pi-agent`，但这里的规则不包含任何 Agent 专属实现。

## 三类目录

| 类型 | 规范路径 | 所有者 | 是否进入核心便携包 |
| --- | --- | --- | --- |
| 通用宿主源码 | `mikazuki/plugin_host/`、`frontend/src/plugins/` | Next Trainer core | 是 |
| 独立插件源码 | `plugin-packages/<plugin-id>/` | 插件交付物 | 否 |
| 用户运行时安装 | `extensions/<plugin-id>/` | 插件宿主与用户数据 | 否；更新时保留 |

核心可以提供市场、包校验、生命周期、通用 UI extension 和 capability gateway，但不得从独立插件源码目录导入实现。独立插件自行锁定、构建和测试依赖，并生成单独的安装包。运行时安装目录只接收已通过信任、兼容性和完整性验证的产物，不作为源码目录使用。

## 核心便携包规则

`build-scripts/03-copy-project.ps1` 的实际 robocopy 排除列表由一个可查询的策略对象提供。以下命令只输出策略 JSON，不运行前端构建、子模块初始化或复制：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File build-scripts/03-copy-project.ps1 -DescribeCopyPolicy
```

策略必须同时排除：

- `plugin-packages`：防止 Agent UI、Pi SDK、Skills、Prompt、构建输入或插件专属 Provider 代码进入核心归档。
- `extensions`：防止本机已安装插件、Provider 配置、会话、缓存、工作区或其他用户数据进入发布归档。

`extensions` 的排除不代表卸载。便携包更新流程继续保留目标安装中的 `extensions`，插件自己的 disable、uninstall 和“删除用户数据”流程分别管理运行时与用户数据。

主要便携构建脚本 `build-scripts/build_portable.ps1` 使用核心目录白名单，本身也不会复制 `plugin-packages`。任何新增或遗留的整仓复制入口都必须复用或等价执行本边界，不能仅依靠开发者记忆排除插件目录。

## 依赖边界

核心依赖清单保持通用：

- `frontend/package.json` 不包含 React、Next.js 或 Pi SDK；Vue 只负责通用 iframe/extension host。
- `requirements.txt` 不包含 Agent/Pi、React、Node 或 Bun 插件运行时依赖。
- 独立插件在 `plugin-packages/<plugin-id>/` 内维护自己的 manifest、lockfile、SBOM、licenses 和构建运行时。

“同一仓库开发”不等于“同一个发布包”。Zero-Short 和发布检查应分别检查核心归档文件清单、核心依赖清单与独立插件包清单。

## 验证

边界行为测试位于 `tests/test_plugin_package_boundary.py`。它会：

1. 实际调用 PowerShell 策略查询入口，并确认 `plugin-packages` 与 `extensions` 都进入 robocopy 的排除集合。
2. 结构化解析 `frontend/package.json`，确认核心没有 React、Next.js 或 Pi 依赖。
3. 解析 `requirements.txt` 的包名，确认核心 Python 环境没有插件运行时依赖。

Windows 验证命令：

```powershell
.\.venv-dev\Scripts\python.exe -m pytest tests/test_plugin_package_boundary.py -q
```

该测试验证可执行策略和结构化清单，不依赖 PowerShell 源码的固定空白、行号或字符串切片。
