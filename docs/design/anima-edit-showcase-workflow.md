# Anima Edit 文档例图工作流（与训练集分离）

## 原则

| 阶段 | 数据来源 | 用途 |
|------|----------|------|
| **训练** | ImagePulse / HumanEdit 等成对数据 | 学「参考 + caption → 目标图」 |
| **文档例图** | **AI 生成参考图** + 手写 edit caption | 门面展示、训练监控说明、README |

官方训练集（如 ImagePulse 分片）**不适合直接当例图**：题材杂、merged 图质量参差、单图 showcase 只取了前 32 条里的 hero，观感一般。

## 推荐流程（单图参考）

```text
1. AI 出图（文生图）→ 得到一张干净的 reference.png（512 或 1024 方图）
2. 手写 edit_prompt_en（与训练同款：具体描述「要把参考变成什么样」）
3. LoRA sample-only：reference + 完整 caption + e12 权重 → out.png
4. 发布三联：ref | out |（可选：AI 再出一张「理想 target」仅作示意，非训练 GT）
```

**不要**把 ImagePulse 的 `target` 当文档里的「标准答案」，除非该条本身质量足够好。

## 目录约定

```text
data/anima-edit-showcase-curated/
  reference/           # AI 生成的参考图
    case01-ref.png
  prompts/
    case01.txt         # 与训练相同风格的完整英文 edit caption
  manifest.json        # stem、权重路径、说明

docs/assets/anima-edit-single-ref/
  case01-ref.png
  case01-out.png       # 模型推理
  case01-caption.md    # 展示用短说明（可选）
```

## 命令速查

### 1）登记一条 showcase（已有 ref 图）

```bash
python script/ops/register_anima_edit_showcase_case.py ^
  --id case01 ^
  --ref path/to/ref.png ^
  --caption-file path/to/caption.txt
```

### 2）用已训 LoRA 出编辑例图（sample-only）

```bash
# 先改 docs/examples/anima-edit-showcase-sample-prompts.toml（或由脚本生成）
python -m accelerate.commands.launch --num_cpu_threads_per_process 1 ^
  scripts/dev/anima_train_network.py ^
  --config_file docs/examples/anima-edit-showcase-sample-only.toml
```

权重默认：`output/anima-edit-single-showcase/anima-single-12e.safetensors`（单图 LoRA）。

### 3）AI 生成参考图（吉比特内网）

使用 `banana-pro` / `gemini-3-pro` 等于 **`POST /api/v1/image/generate`**，prompt 要求：

- 单人或单主体、背景简单
- 动漫 / 插画风格（与 Anima 用户一致）
- 方图，便于 512 训练与预览

详见 skill：`gbits-aiserviceproxy-api`（**勿在聊天中贴 Key**）。

批量下载参考图（Key 读 `~/.gbits/aiserviceproxy_api_key.txt` 或环境变量）：

```bash
# 先在 script/scratch/ 写好 aisp-caseNN-ref.json，再：
python script/ops/fetch_aisp_showcase_refs.py case02 case03 case04
```

## 双图参考·多人融合（推荐用于门面）

当需要 **两人同框、并肩/对话** 类例图时，用本流程（与单参考「Place 一人进场景」区分）：

```text
1. AI 各出一张单人立绘 → reference/<dualNN>/1.png, 2.png
2. 手写 Fuse A and B into a pair … 长 caption（与 ImagePulse 训练一致）
3. sample-only + imagepulse-30e-000020 + reference_dir + reference_count = 2
```

```bash
python script/ops/fetch_aisp_showcase_refs.py dual01-1 dual01-2
python script/ops/generate_anima_edit_showcase_dual_prompts.py ^
  --out docs/examples/anima-edit-showcase-dual-sample-prompts.toml
python -m accelerate.commands.launch --num_cpu_threads_per_process 1 ^
  scripts/dev/anima_train_network.py ^
  --config_file docs/examples/anima-edit-showcase-dual-sample-only.toml
```

文档资产：`docs/assets/anima-edit-showcase-dual-curated/`。

## 单图参考·表情编辑（推荐用于单人例图）

ImagePulseV2 **表情编辑**分片：参考 = `image`（原表情），目标 = `image_edited`，caption = `generated_edit_prompt`（中文，描述从原图到编辑图的变换）。

```bash
python script/ops/import_imagepulsev2_expression_local.py --src path/to/1770727528474713020.tar.gz
python -m accelerate.commands.launch --num_cpu_threads_per_process 1 ^
  scripts/dev/anima_train_network.py --config_file docs/examples/anima-edit-expression-20epoch.toml
```

权重输出（推荐 20 epoch）：`output/anima-edit-expression-20epoch/expression-20e-000020.safetensors`（及每 5 epoch 存档）。更长训练见 `anima-edit-expression-40epoch.toml`。  
若已在跑 40 epoch，在对应终端 **Ctrl+C** 停掉后改跑 20 epoch 配置即可（数据目录不变）。

门面 sample 请用 **与训练相同的 caption**（`target/<stem>.txt`），不要用泛化短 prompt。

## 当前 `docs/assets/anima-edit-single-ref/` 里 ImagePulse hero

保留作 **管线冒烟证据**（训练能跑、preview 对齐 caption）。**对外文档请改用 showcase-curated 案例。**
