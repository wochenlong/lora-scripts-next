# 桌面启动器引擎控制核心

本包为四个训练引擎提供相同的检查、计划、执行和恢复合同。`worker.py` 通过受管基础 Python 的 `-I -S` 启动，只导入标准库；不会为修复 GUI 导入 Torch 或现有网页模块。训练适配器只有在存在父启动器注入的上下文时才选择正式独立实例。

## 工作目录与状态

| 内容 | 路径 |
| --- | --- |
| 虚拟环境 | `ROOT/e/t<15hex>` |
| 基础 Python | `ROOT/p/t<15hex>` |
| 引擎源码 | `ROOT/s/t<15hex>` |
| 引擎状态 | `ROOT/state/engines/<release>/<engine>/state.json` |
| 不覆盖的代次收据 | 同状态目录的 `instances/<instance>/<generation>.json` |
| 下载缓存 | `ROOT/cache/engine-assets/<sha256>/<filename>` |
| 变更日志和恢复快照 | 同状态目录的 `operations/op-<uuid>/` |
| 用户资料 | `ROOT/profiles/<profile>` |

`state.json` 成功状态必须同时满足 `status="ready"`、`dirty=false`、`pending=null`、`generation=validated_generation>0`。身份包含 `engine_id`、`release_id`、`instance_id`、`recipe_sha256`、`lock_sha256`、`receipt_relative` 和 `receipt_sha256`。收据记录环境、源码和基础 Python 的文件摘要；基础 Python 的派生字节码缓存不作为稳定文件身份。

源码、解释器和环境各实例独立。重建提交新实例后保留旧实例与旧代次收据。精准修复只安装明确损坏的包和明确损坏的源码文件，重核非目标文件；失败保留 dirty 和恢复现场。恢复验证事务前的字节，不把恢复前本来就损坏的环境误标为 ready。首装失败无旧环境可恢复时保留现场，允许显式新实例重建。

## 运行协议

worker 从 stdin 接收一行 JSON，从 stdout 返回一行 JSON。协议版本为 `schema_version=1`；基础参数为 `action`、`root`、`release_id`、`engine_id`，`profile_id` 默认 `default`。

- `capabilities`、`recipe`：读取适配范围和固定配方。
- `inspect_readonly`：零写入、零网络、零子进程，不导入引擎。安装完整性与 import、GPU、training 分开报告。
- `plan_install`、`plan_repair`：要求启动器内置信任的 `lock_path` 和 `lock_sha256`，返回资产、下载量、精确包范围、期望代次和 `plan_sha256`。重建另须 `rebuild=true`。
- `repair_apply`：要求此前返回的 `plan` 和 `plan_sha256`，取得同一个 `.launcher-lock`，重核绑定、文件事实和资产后执行。下载仅允许让缺失列表减少；不能改变锁、实例、代次或目标范围。
- `recover`：取得写 lease 后恢复待结束事务。
- `probe_execute`：显式启动已核验实例；`probe_scope` 可为 `metadata`、`imports`、`cuda`。不会启动训练或加载模型权重。

长命令使用离线 uv，禁用 Python 自动下载和索引，按固定摘要缓存安装。可通过受管 `state` 内的 `cancel_file` 协作取消，超时或取消会停止命令子树并保留 dirty；Rust 应继续监督整个 worker 子树。根目录必须存在内容精确为 `next-trainer-desktop-v1` 的 `.launcher-workspace`，物理受管路径拒绝 symlink/reparse point。

## 网页与已有训练入口

`routes.py` 挂载在 `/api/launcher/engines`。路径、发布版本和锁身份来自父进程注入的 `NEXT_TRAINER_LAUNCHER_CONTEXT` JSON，HTTP 客户端不能自行指定。格式为：

```json
{
  "schema_version": 1,
  "root": "E:/NextTrainer",
  "release_id": "release-id",
  "profile_id": "default",
  "engine_catalog": {
    "kohya": {"lock_path": "E:/NextTrainer/cache/catalog/kohya.json", "sha256": "固定发布摘要"}
  }
}
```

GUI 运行期间 Rust 持有工作区 lease，因此网页允许只读检查和预览计划；执行、主动探测和恢复立即返回 `desktop_action_required`，要求停止 GUI 后在桌面执行。网页与桌面仍共享同一个检查和计划核心。已有训练入口通过 `bindings.py` 选择登记的独立解释器、源码和当前资料档案；托管 Kohya 禁用 GUI Python fallback，旧安装/升级/删除入口拒绝修改正式实例。

## 发布资产锁

`desktop-launcher/catalog/engines/` 随包携带四个引擎的完整 Windows 平台资产锁。原有 `>=` 依赖在发布阶段解析成确切 wheel URL、字节数和 SHA256。AI Toolkit 的官方 CUDA 12.8 Torch 三件套另行固定，防止浮动索引选到 CPU wheel。少量没有上游 wheel 的纯 Python 包在发布阶段按固定 sdist/git 与固定 backend 预制，作为精确摘要的内嵌资产提供；用户机不进行源码构建。

`catalog.py resolve` 生成平台 pylock 和来源记录，`catalog.py finalize` 合并解释器和源码归档的全文件清单。缺少 wheel 的具体包必须完成预制或补齐来源后才可生成执行锁；缺 size/hash 的元数据可通过包 JSON、HEAD 或单字节 Range 补齐。配方文本指纹采用 `utf8-lf-v1`，避免 Windows 工作树 CRLF 与发布归档 LF 的无意漂移；归档本身仍按实际字节验证。

## 验证边界

`python -m unittest mikazuki.launcher.tests.test_control_smoke -v` 是四引擎两包小夹具、事务、HTTP 和已有 runtime 绑定的冒烟测试。uv 系统调用在该套件中由夹具替代。另在隔离目录完成过真实 uv、官方 Python 3.11 和 71KB `idna` 包的安装、metadata probe、损坏识别与精准重装。

按用户批准的 CR-004，四个真实训练引擎的安装、导入、损坏修复、GPU、模型、训练与权重验收均为 `skip + CR-004`；上述夹具和资产锁生成不代表这些真实验收通过。
