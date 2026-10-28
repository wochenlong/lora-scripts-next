# User Data

Implementation tracking: issue #405. This delivery includes settings persistence,
preset CRUD and new task configuration archives, not the entire preference migration.

The project-root `user_data/` directory holds server-owned settings. It is ignored
by Git and excluded from portable copy/update operations. Relative paths are
resolved against the project directory.

## 桌面启动器的独立用户目录

源码安装和原便携包在没有设置下列环境变量时，继续使用原有目录。
桌面启动器可以在启动 Python **之前** 指定绝对目录，使切换源码版本时保留设置，
并让各版本拥有自己的任务队列与运行状态：

```powershell
$env:NEXT_TRAINER_DATA_ROOT = 'D:\NextTrainer\profiles\default'
$env:NEXT_TRAINER_STATE_ROOT = 'D:\NextTrainer\profiles\default\compat\dev-<release-id>'
```

`NEXT_TRAINER_DATA_ROOT` 是用户 profile（配置空间）的根目录；
`NEXT_TRAINER_STATE_ROOT` 是当前版本状态的根目录。
两个变量都只接受绝对路径；相对路径会报错，避免启动目录改变后写入错误位置。
空值等同未设置。修改变量后必须重新启动 Python 进程。
路径解析本身不会创建目录、导入、迁移或删除已有文件。

| 数据 | 设置变量后的路径 | 目的 |
| --- | --- | --- |
| 设置、凭据、预设、任务配置归档 | `<DATA_ROOT>/user_data/` | 同一 profile 内跨版本保留 |
| 旧 GUI 的 `assets/config.json` | `<STATE_ROOT>/assets/config.json` | 保存旧界面设置，隔离不同版本格式 |
| 任务生命周期队列 | `<STATE_ROOT>/logs/task_queue.json` | 回退版本时读取本版本队列 |
| 相对 `logs/...` 的任务日志、TensorBoard 日志目录 | `<STATE_ROOT>/logs/` | 让日志与所属版本的任务状态对应 |
| 网络策略、下载源、更新检查缓存 | `<STATE_ROOT>/config/` | 隔离运行设置与缓存 |
| 启动准备时创建的自动保存目录 | `<STATE_ROOT>/config/autosave/` | 配合启动器兼容工作视图 |

如果未设置 `STATE_ROOT`，上表的版本状态路径回退到 `DATA_ROOT`；两个变量都未设置时，
每个调用点保持旧路径。单独设置 `STATE_ROOT` 不会改变默认 `user_data/` 位置。
启动器管理多个版本时应同时设置两个变量，并为每个版本指定独立的 `STATE_ROOT`。
`UserDataStore(root=...)`、`MIKAZUKI_TASK_QUEUE_FILE`、`NEXT_TRAINER_NETWORK_CONFIG`、
`NEXT_TRAINER_DOWNLOAD_SOURCES_CONFIG` 等已有显式路径参数或环境变量仍优先。
任务的绝对日志路径也保持原样。

启用 profile 后，`user_data` 中模型路径设置的相对值按 `<DATA_ROOT>` 解析；
未启用时仍按项目目录解析。已有外部模型、数据集和输出建议记录绝对路径。
此接口不扫描或搬运它们，也不重写训练配置里的路径。

### 与旧版本及训练引擎的兼容边界

这组变量覆盖上表所列的 Python 持久化入口，尚未替换所有历史相对路径。
主程序必须继续从源码所在目录启动，以读取前端、schema（配置结构定义）、
预设、脚本和 vendor（随包分发的上游源码）；不能把当前工作目录直接改为 profile。
尚未逐个接入新接口的包括：训练提交/API 与 Agent 的部分自动保存路径、
`.runtime` 下的插件市场和 Agent 工作区、训练引擎安装器与状态文件、
翻译数据库、模型/数据集/输出的默认相对路径及监视器读取路径。

对这些入口，以及完全不认识新环境变量的已发布主程序，桌面启动器需要建立
`run/<release-id>` 兼容工作视图：源码副本来自不可变的 `releases/<release-id>/app`，
共享 `user_data` 指向 profile；`logs`、`.runtime`、`extensions`、`assets`、`toml`、
`config` 等可写目录按兼容需求指向 `profile/compat/<release-id>/`，
`datasets`、`output`、`sd-models`、`tagger-models` 指向 `profile/library/` 的对应目录。
Windows 可使用目录 junction（目录联接）。由启动器负责校验、初始化和维护这些映射，
并在初始化版本专用目录时保留该版本所需的随包静态文件。
单独设置环境变量并不代表兼容工作视图已经建立。

训练引擎的 Python 环境、安装状态、插件运行时按版本保存在 `compat`，
当前不承诺跨版本复用，也不能把新版本队列或插件状态直接覆盖到旧版本。
修复或删除某个主程序版本时，应保留 profile、共享资源库与该版本的状态备份。
迁移旧数据必须显式执行并先备份，当前 Python 路径接口不会自动接管旧目录。

## Startup

Create `user_data/settings.json` with the sections you need. Omitted values use
application defaults; an explicit CLI option overrides the corresponding file
setting. Restart the GUI after changing startup options.

Example for a cloud deployment exposing port 6006:

```json
{
  "schema_version": 1,
  "revision": 0,
  "startup": {
    "gui": {
      "host": "0.0.0.0",
      "port": 6006,
      "open_browser": false,
      "port_conflict": "error"
    },
    "monitor": {
      "enabled": true,
      "mode": "integrated",
      "port": 6008,
      "port_conflict": "next_available"
    },
    "tensorboard": {
      "enabled": false,
      "host": "127.0.0.1",
      "port": 6007,
      "port_conflict": "disable"
    }
  },
  "paths": {
    "tagger_models": {
      "wd-eva02-large-tagger-v3": "./tagger-models/wd14/wd-eva02-large-tagger-v3"
    }
  }
}
```

GUI defaults to `127.0.0.1:28000`, conflict policy `error`.
TensorBoard is optional and disabled by default; enable it in the file or with
`--enable-tensorboard`. Monitor runs on an internal loopback endpoint behind the
GUI integration. Exposing the GUI does not require exposing its monitor port.

`error` stops startup on a conflict. `next_available` checks at most 20 ports and
reports the actual selected port; it skips reserved service ports. `disable`
skips an auxiliary service and emits a warning; it cannot disable the main GUI.
The GUI owns its selected port before any auxiliary service is allocated. No
unrelated listener is terminated.

Do not expose this service directly to an untrusted network. Use an authenticated
reverse proxy or equivalent deployment protection. File-backed settings do not
introduce a multi-user account or authentication system.

## Local Tagging Model Paths

`paths.tagger_models` maps the existing tagging model ID to a local asset
directory, not to one weight file. The directory must contain the files expected
by that model (for example `model.onnx` and `selected_tags.csv` for WD models).
Weights are not copied into user_data.

The explicit `MIKAZUKI_TAGGER_MODELS_DIR` environment override retains priority.
Restart or unload an already loaded tagger after changing its directory.

## Durable File Contract

Settings writes validate a bounded schema, check the revision, serialize writers,
and atomically replace the file. `settings.json.bak` retains the preceding valid
settings. A corrupt configuration is reported and not overwritten with defaults.
Keep the application stopped while manually editing files; API writes use
revision checks and should be used for concurrent clients.

`auth.json` is reserved for API credentials. The API returns only configured
provider flags, never secret values. Ordinary exports must not include this file.
POSIX temporary-file permissions restrict access; Windows protection also depends
on the directory ACL. This file is not encrypted. Do not share a full user_data
backup without first considering its credentials.

The initial API exposes `/api/user-data/settings` (GET/PATCH) and
`/api/user-data/auth` (GET metadata) plus `PUT /api/user-data/auth/{provider}`.
Writes require JSON and an expected revision. Errors never echo secret values.
The credential store is infrastructure only until existing provider adapters are
explicitly migrated; do not assume all old API-key settings already use it.

## Rollout Boundary

Default engine, per-model remembered engine and engine list ordering now use the
settings API. The frontend loads them before initial routing. Failed saves remain
visible; concurrent edits refresh server settings and require another user action,
rather than silently overwriting the other client.

The engine settings page offers an explicit, confirmed import of old browser
engine preferences when the corresponding server fields do not exist. Import does
not delete browser data or overwrite existing server fields. Other browser
preferences remain subsequent tracked steps in #405.
No old task history is copied or deleted by this delivery.

## Presets and Task Configuration Archives

User presets are JSON files in `user_data/presets/`. The task detail page can save
task parameters as a preset and edit or delete saved presets. The API provides
GET/POST `/api/user-data/presets` and GET/PATCH/DELETE
`/api/user-data/presets/{id}`. A preset referenced by `default_presets` cannot be
deleted. Applying that default automatically in training is not yet connected.

New configuration snapshots are stored in
`user_data/tasks/<engine>/<YYYY-MM-DD>/<HHMMSS>_<task-id>/`, using UTC timestamps.
Each contains `task.json` and a sanitized configuration snapshot. When supplied,
`engine_config_path` is also captured as `engine-config.yaml` or JSON alongside
the UI configuration. Credential fields are removed recursively before writing
snapshots; original training files are not modified. A missing or invalid source
blocks task registration. Snapshots are reserialized, so comments are not retained.
The task-page header offers archive browsing even after queue history is cleared;
task details additionally offer filtered selection and parameter import into the matching training page.
GET `/api/user-data/task-archives` returns `data.archives`; preset lists return
`data.presets`. Archive detail is available at `/api/user-data/task-archives/{id}`.

These are configuration snapshots, not a replacement for the existing task
lifecycle store or a backup of output models and preview images. Existing task
history is left untouched. Back up `user_data/` separately before upgrades.

Runtime model/Python/default-preset path fields are reserved typed settings until
the owning consumer is explicitly connected.
Do not treat a settings field's presence as proof that its consumer is migrated.
