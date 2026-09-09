---
name: next-trainer
description: 操控 Next Trainer（lora-scripts-next）训练管理器——查询参数 schema、校验与提交训练、监控任务、看图验收、管理数据集与打标。当用户要求提交/监控/复现训练任务或操作 Next Trainer 时使用。
---

# Next Trainer 操控技能

通过 `scripts/nt.py`（stdlib-only CLI）访问 Next Trainer HTTP API。**无常驻进程、
无会话状态**：app 重启、agent 重启都不影响通道。

## 连接

- 默认打 `http://127.0.0.1:28000`；远程用 `--base-url` 或环境变量 `NT_BASE_URL`
  （远程机器走 ssh 端口转发或直接 LAN URL）。
- 主 app API 无鉴权，只在本机/可信网络使用。

## 应用生命周期（本机操作，不走 API）

```bash
python3 $NT health                 # 探活：alive=false 时退出码 1（可直接进脚本逻辑）
python3 $NT start                  # 后台拉起 run_gui.sh（Windows 用 run_gui.bat），
                                   # 日志写到 <repo>/logs/gui-agent.log；已活着则直接返回
python3 $NT start --repo /path/to/lora-scripts-next   # skill 装在全局位置时指定仓库根
python3 $NT stop                   # ⚠️ SIGTERM 停止应用，会中断训练，先获得用户确认
```

- `start` 首次运行可能装依赖要数分钟，用 `health` 轮询直到 `alive=true`。
- `stop` 以"端口释放"为停止判据，应用会自清理 TensorBoard 等子进程；
  超时未退出会提示人工处理，不要自动强杀。

## 标准训练流程

```bash
NT=.opencode/skills/next-trainer/scripts/nt.py   # 路径以实际 skill 安装位置为准
python3 $NT --help                               # 全部子命令+一句话说明（自描述，不用翻脚本）
python3 $NT schemas                              # 1. 查目标训练页的参数字段/默认值
python3 $NT params sd3-lora                      #    或：单页字段紧凑表（name/default/description）
python3 $NT search learning_rate                 #    或：跨全部 schema + 文档聚合检索关键字
python3 $NT validate anima-lora config.json      # 2. 校验配置，有错改了再验
python3 $NT dataset-validate /path/dataset.toml  # 3. 配了 dataset_config 时校验数据集 toml
python3 $NT gpu-status                           # 4. 看各卡实时显存，决定 gpu_ids
python3 $NT submit config.json                   # 5. ⚠️ 先获得用户明确确认
```

监控与验收（轮询间隔 >= 30 秒，不要高频刷）：

```bash
python3 $NT tasks                                # 任务列表（紧凑版）
python3 $NT overview <task_id>                   # 状态+最新loss+进度+日志尾+预览数 一次拿全
python3 $NT metrics <task_id> --max-points 50    # loss 曲线
python3 $NT log-tail <task_id> --limit 500       # 日志尾部（排错加大 limit）
python3 $NT grep-log <task_id> Traceback         # 关键词搜日志
python3 $NT preview <task_id>                    # 下载最新预览图，打印本地路径
# 然后用 Read 工具查看打印出的图片路径，直接验收采样质量
python3 $NT outputs <task_id>                    # 产出的 safetensors 清单
```

配置来源：`config <task_id>` 取历史任务的完整 autosave 配置（复现/对照用）；
`submit-preset <name> --overrides '{"max_train_epochs":1}'` 以预设为底提交。

其他：`dataset-scan <目录>`（图片+caption 清单）、`tag <路径>`（WD14 打标）、
`tagger-status`、`browse`（服务器文件浏览）、`list-files model-file`、
`terminate/resume/retry <task_id>`。参考文档在 `reference/` 目录，用 Read 直接读。

## 红线

- **submit / submit-preset / terminate / resume / retry / stop 必须先获得用户明确确认**
  （会占用 GPU、杀死训练进程或停止整个应用）。
- 已有任务在跑时 submit 会被闸门拦下；用户确认排队后加 `--confirm-queue` 重试。
- 数据集大文件投递走 ssh/rsync，本技能只操作已在服务器上的路径。
- **schemas 原文很大**：优先用 `params <page>`（紧凑字段表，公共字段在 `shared` 页）
  和 `search <关键字>`（跨 schema + SKILL.md + reference/ 聚合检索，一次定位参数含义与文档出处）。
- 参数含义不清时先读 `reference/` 文档（`search` 命中后按行号 Read），再向用户提问。

## 实战坑位（复现 issue 踩出，别再踩）

- **Anima LoKr 专项经验（CFG 几何 / 触发词 / dropout / TE 冻结 / 容量）必读
  `reference/anima-lokr-sd-scripts.md`**——配置 LoKr 训练前先读它。
- `learning_rate` 传 JSON 数值（如 1e-6），**不要传字符串**——Automagic 对字符串 lr 直接 TypeError。
- Anima 的 `sample_prompts` 必须传**prompt 文件路径**（每行一条 `--n/--w/--h` 格式），
  传内联文本会被当文件路径解析，采样静默失败（日志报 `No prompt file`，preview_count 恒 0）。
  WebUI 是先把文本框内容落成 `config/autosave/*-promopt.txt` 再传路径；API 提交要自己写文件。
- `gpu_ids` 字段可能触发后端 500（非 JSON 响应）；单卡环境建议不传该字段，让后端默认分配。
- 数据集 toml 各引擎**不通用**：kohya 系（anima-lora 等）不收 `validation_split_num`、
  `subsets[].recursive`、`cache_dir`（这些是 anima-fast 字段）——`dataset-validate` 会点名。
- kohya 数据集 subset 的 `image_dir` 必须直指含图片的目录（每目录一个 subset），不支持递归父目录。
- Anima 训练选 Automagic/CAME 时，后端会把 mixed_precision 从 fp16 静默翻转为 bf16
  （防 nan 护栏），任务 metadata 里以翻转后的值为准。

## 权限配置建议（opencode.json）

```json
{
  "permission": {
    "bash": {
      "*nt.py submit*": "ask",
      "*nt.py terminate*": "ask",
      "*nt.py resume*": "ask",
      "*nt.py retry*": "ask",
      "*nt.py stop*": "ask"
    }
  }
}
```
