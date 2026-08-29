# AI 适配指南：接入一个新训练引擎

> 读者：AI agent（也适用于人）。按任务表顺序执行，每步带完成判据，判据不过不进下一步。
> 结构约定见 `_template/`（复制它起步）；字段契约见 `manifest.py`（`mikazuki/engines/manifest.py`）。
> 原则：照样板把结构做进去、套件做进去、扫被打过的已知坑、确定的直接 patch——让适配从开荒变巡检。

## 任务表

| # | 步骤 | 动作 | 完成判据 |
| --- | --- | --- | --- |
| 1 | 读上游 | 训练入口脚本、配置格式、依赖清单、Python/torch 要求 → 填 manifest 草稿 | CAPABILITIES 与 UPSTREAM 能过 `load_manifest` 不报错 |
| 2 | 复制模板 | `cp -r _template <id>`，填 settings/installer | 钉版 commit 能抽出源码快照（git archive 或 zip） |
| 3 | environment | uv 独立解释器 + venv + 依赖安装 + audit | audit 全绿，state=ready |
| 4 | adapter | 按 #300 glossary 表映射字段（白名单模式） | UI 配置能 dumps 出引擎原生配置 |
| 5 | preflight | 按 variant 列资产清单 | 缺资产时报错明确列出缺什么 |
| 6 | run/routes | handle_run 串五段式；routes 暴露 status/install | `POST /api/run` 能分发到本 pack；`/api/engines/<id>/status` 200 |
| 7 | 观测面 | 进度/loss/sample 三通道接入（见「观测面接入」节）；task metadata 带齐 `output_dir`/`output_name`/`logging_dir` | 任务详情页有进度与 loss 曲线、sample 预览出图（合成数据单测先行，真跑冒烟收口） |
| 8 | 已知坑扫描 | 逐条比对 `KNOWN_PITFALLS.md` | 命中且判定确定的直接打现成补丁；不确定的记 FIELD_NOTES 待人工 |
| 9 | smoke + FIELD_NOTES | 按 `smoke/README.md` 清单跑通 | 能装 → 能提交 → 能出 LoRA，证据进 FIELD_NOTES |

## 观测面接入（任务第 7 步）

任务详情页（TasksPage + `/train-log`）的进度、loss 曲线、sample 预览不是自动复用的，每个引擎要核对四件事：

1. **TB/日志开关**：上游配置里要不要显式开。ai-toolkit 不设 `log_dir` 就根本不产 tensorboard event——adapter 必须主动写 `log_dir`（+ 按需 `logging.log_every`，上游默认 100 会让短冒烟跑 0 个点）。
2. **进度条格式**：tqdm 的 desc 是什么。kohya 是 `steps:`，ai-toolkit 是 job 名——共享正则锚 `steps:` 匹配不到后者；解析要按引擎锚定（通用 tqdm 正则会被 latent 缓存/采样条抢匹配）。
3. **TB tag 名**：kohya 写 `loss/average`，ai-toolkit 写裸 `loss`/`lr`。`task_insights.LOSS_TAGS` 不是普适常量，按 `metadata.backend` 选 tag 列表。
4. **sample 落盘约定**：目录层级 + 文件名格式决定发现逻辑和 step/epoch 解析。kohya：`output_dir/sample/`、output_name 前缀、6 位 step；ai-toolkit：`<training_folder>/<name>/samples/`、毫秒时间戳开头、9 位 step。

结构化解析可以按上游源码静态推导先写 + 合成行单测，但必须标注「未实采」；GPU 冒烟第一件事留完整 stdout + 产物目录树，回填校正后再收口。

## 纪律

- `api.py` 零改动。发现必须改 `api.py` 才能挂上时，停下来——那是框架缺口，先报而不是绕。观测面进度解析走 pack 可选模块 `progress.py`（暴露 `read_progress(lines, metadata)`），由 registry 按 `metadata.backend` 分发，不算 api.py 改动。
- 引擎一律 `uv python install` 自己的解释器，不要复用 GUI/主环境解释器当 venv 底座（#251 已否决）。
- 补丁：unified diff + 头部四要素（见 `_template/patches/README.md`），`git apply --check` 响亮失败。
- 语义不等价的参数（epoch vs steps 等）禁止在 adapter 里硬并，标注后放行。
- 每个坑修完回填：FIELD_NOTES「踩坑流水」→ 有通用性的提炼进 `KNOWN_PITFALLS.md`。
