# 云端 slim 部署（start_cloud.sh）

> 面向带 PyTorch 的云镜像（AutoDL 等）。与 [autodl-deploy.md](./autodl-deploy.md)
> 的手工仪式（选镜像 → conda → pip torch → pip requirements）不同，
> `start_cloud.sh` 依托镜像里**已有的 torch** 一键装机：检测宿主环境 →
> 匹配引擎 → slim 安装（复用宿主 torch，不建独立 venv）→ 直启 WebUI。

## 用法

```bash
bash start_cloud.sh                      # 交互式：列出兼容引擎，问装哪个
bash start_cloud.sh --engine musubi --yes  # 非交互（打镜像用）
bash start_cloud.sh --port 6006          # 默认 6006
```

## 工作流程

1. **直启**：根目录存在 `.cloud_install_done`（装机 flag）→ 校验指纹
   （python 版本 / torch 版本含 cu 构建号 / 架构，硬比对）→ 一致直接拉起
   WebUI；**不一致直接报错退出**（不自动重装，请换用对应镜像）。
2. **装机**（无 flag）：扫描候选解释器（conda base/envs、PATH、系统 python）
   → 探测 python/torch/CUDA 事实 → 选最优解释器 → 按各引擎 pack manifest 的
   `REQUIRES` 过滤兼容引擎 → 交互选择（或 `--engine` 指定）→
   装 `requirements.txt` + 引擎 slim 依赖 → 自检 → 写 flag → 拉起 WebUI。
3. 无匹配引擎时报错退出，列出探测事实与各引擎要求——换镜像，不碰运气。

## slim 安装是什么

引擎依赖直接装进镜像宿主环境，**不带 cuda extra**，因此不会动宿主 torch
（musubi-tuner 的 torch 依赖只存在于 cu12x extras）。引擎 pack 预期的
`.venv/bin/python` 用一个指向宿主解释器的符号链接满足，状态机 / 审计 /
训练拉起路径零改动。slim 与 isolated 不混装：已 slim 的引擎在 UI 里走
隔离安装会被拒绝（反之亦然），卸载后两者皆可重新选择。

## cloud 模式行为

start_cloud 拉起 WebUI 时注入 `NEXT_TRAINER_CLOUD=1` + 锁定引擎 id：

- 引擎设置页显示云端横幅，**所有引擎的安装 / 重装 / 卸载按钮禁用**；
- 未锁定引擎的训练门页不再显示安装引导，改为说明文案；
- 后端 `/api/engines/<id>/{install,repair,uninstall}` 同步拒绝
  （前端门控只是体验，后端才是边界）；
- `GET /api/cloud/status` 返回 `{cloud_mode, engine}`。

只有经 start_cloud 启动才算 cloud 模式；其他入口启动不带环境变量，行为不变。

## 引擎兼容性（REQUIRES）

各 pack 在 `mikazuki/engines/<id>/manifest.py` 声明：

| 引擎 | SLIM_SUPPORTED | REQUIRES |
|------|----------------|----------|
| musubi | ✅ | python `>=3.10,<3.13`，torch `>=2.5.1`，cuda `>=12.4` |
| kohya / anima-fast / ai-toolkit / diffsynth | ❌ | — |

REQUIRES 只填**真机训练冒烟验证过**的版本区间；新引擎开 slim 时按
`mikazuki/engines/manifest.py` 的契约说明逐个开启。

## 端口

| 服务 | 端口 |
|------|------|
| WebUI | 6006（`--port` 可覆盖） |
| 训练监控 | 6008（gui.py 自动拉起） |

TensorBoard 在 cloud 模式禁用（与 6006 冲突）。

## 契约注意

`start_cloud.sh` 一旦被云镜像「开机启动」绑定，与 `start_autodl.sh` 一样
**不可移动 / 重命名 / 删除**，只能改内容。实现逻辑在 `scripts/cloud/`。
