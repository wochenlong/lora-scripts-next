# DiffSynth-Studio / Qwen-Image-2.1 技术说明

本文面向维护者。第一次使用请先阅读[训练入门教程](../diffsynth.md)。

仅开放 Qwen-Image-2.1 **BF16 文生图 LoRA**，不包含 Edit、量化权重、全量微调或多卡。
完整 DiffSynth-Studio 固定在 `7686e54d41d25c0e8ed5f1318acc23b6bb832654`，不修改其源码。
模型、优化器和训练循环使用上游实现；适配层负责输入转换、Kohya 兼容分桶组批、调度器选择、任务管理和 logger 回调。

## 准备与使用

1. 在「设置 → 训练引擎」安装 DiffSynth。沿用已有下载源设置，需要 Git、uv、网络及支持 BF16 的 NVIDIA GPU。
2. 在训练页选择「Qwen-Image-2.1 → DiffSynth-Studio → LoRA」。
3. 模型输入选择 `components`，分别选择 Comfy-Org 的 BF16 文件：
   - `diffusion_models/qwen_image_2.1_bf16.safetensors`
   - `text_encoders/qwen3vl_8b_bf16.safetensors`
   - `vae/qwen_image_2.1_vae_bf16.safetensors`
4. 无需填写 Processor 路径。开始训练后自动检查项目根目录的
   `tokenizer-cache/Qwen_Qwen-Image-2.1/processor/`，缺失或格式损坏的文件自动下载，完整时直接复用。
   下载进度及失败原因显示在训练日志中；旧配置中的 `processor_path` 不再覆盖固定位置。
5. 选择数据集格式、保存目录、轮数及 Rank，提交训练。启动时检查本地模型、数据和运行环境。

模型也可用 `directory` 模式选择包含 `transformer/`、`text_encoder/`、`vae/` 的 BF16 目录。
组件路径支持单文件、分片索引，或只有一个模型候选的目录。选择分片时自动查找对应索引，
缺失分片、索引越界、多候选、错误模型结构和非 BF16 权重会报错。官方目录中的 F32 权重不在本版 BF16 输入范围内。

Processor 固定下载官方版本 `790c92633540aa0cb11d9abf19eb46d861714758` 的 9 个配置及词表文件，
下载源优先使用 `HF_ENDPOINT`（未设置时使用 hf-mirror.com），失败时尝试 Hugging Face 官方源。
下载逐文件原子写入；中断后重试保留已完成文件。随后由上游 AutoProcessor 完成实际加载。
该目录已加入 `.gitignore`；预检及 dry-run 不下载，准备工作在训练子进程中执行。

Windows 训练入口默认设置 `DIFFSYNTH_DISK_MAP_BUFFER_SIZE=1000000000000`，
避免上游 DiskMap 周期性重开权重映射导致 `torch_cpu.dll` 访问冲突（`0xC0000005`，
[上游问题 #1563](https://github.com/modelscope/DiffSynth-Studio/issues/1563)）。
此值是触发刷新的参数数量阈值，不会预分配对应大小的内存；显式设置的环境变量优先。

训练环境未安装 Triton 时，入口自动使用上游 Qwen-Image-2.1 的分段 PyTorch
注意力路径，避免 Flex Attention 在首个训练步才报 `No module named 'triton'`。

## ComfyUI 模型及输出

Comfy-Org BF16 文件与 DiffSynth 原生布局并非完全相同：

| 组件 | 转换 |
| --- | --- |
| DiT | `img_mlp.gate_up` 按行拆为 `gate_layer`、`proj` |
| 文本编码器 | 语言模型键名恢复 `model.language_model.*` 前缀 |
| VAE | Wan 风格层名映射；移除卷积权重中长度为 1 的时间轴 |

转换前检查完整键名及尺寸，转换结果必须匹配固定上游的模型签名。
转换文件只写入 `extensions/diffsynth/cache/models/`，按输入路径、大小、修改时间隔离缓存，
不覆盖原模型；首次运行需为转换副本预留磁盘空间。

输出为 safetensors LoRA，使用 ComfyUI 内置加载器支持的 `lora_A.weight` / `lora_B.weight`，
并保存各层 `.alpha`。Alpha 留空等于 Rank；继续训练时按照源文件 Alpha 和目标 Alpha
换算 B 权重，保持初始有效增量一致。MLP 两个子层分别导出，由 ComfyUI 原生映射作用于合并权重的两个区段。
使用**支持 Qwen-Image-2.1 的新版 ComfyUI**，放入 `models/loras`，接内置 Load LoRA / Load LoRA Model Only 节点；
本版只训练 DiT，CLIP 不产生 LoRA。

已通过未修改 ComfyUI 加载器的 CPU 合成张量映射与合并数值测试。
2026-09-22 已完成 RTX 4090 24GB、256×256 的短训、训练中预览和独立 ComfyUI API 回载出图。
这是功能烟测，不是收敛、画质或任意硬件开箱即训保证，具体范围见[验收记录](diffsynth-main-acceptance.md)。

## 数据与步数

- `image_text`：递归读取图片及同名 TXT。`重复次数_名称` 第一层子目录乘全局 `dataset_repeat`（默认 1）；
  普通目录和根目录图片也保留。空 TXT 表示空提示词；缺失 TXT 报错。RGBA 不丢失。
- `metadata`：指定 `dataset_base_path` 与原生 CSV / JSON / JSONL，必需 `image`、`prompt` 字符串。
  直接交给上游 UnifiedDataset，不按文件夹名重复；CSV 空提示词规范化为空字符串。
- 支持真实分桶 batch；梯度累积、保存间隔、按步数预览、Loss 和总步数使用**优化器更新次数**。
  总步数为 `ceil(每轮实际 batch 数 / 梯度累积步数) × 轮数`，包含每轮末尾不足一次累积的更新。

## 预览

复用作者 `feat/ai-toolkit-klein` 分支的 PreviewSampleField 交互，首版裁剪为文生图字段。
开启后默认一组，可增删；每组独立设置 prompt、width、height、seed、guidance_scale、sample_steps。
不暴露采样器切换、参考图或网络倍率等本适配未实现的选项。

预览在上游 logger 的优化器更新回调中调用现有 pipeline，不复制训练循环。
图片保存到本次输出目录的 `sample/`，复用任务页现有图片、缩略图与预览 API。
界面显示采样阶段，文件名关联 Step 与 Sample；预览失败会让任务明确失败。
回调恢复随机数状态、训练/评估状态及训练噪声调度器，不修改优化器。

模型 CPU 卸载与训练预览同时启用需要编码缓存。适配层捕获固定上游卸载管理器，
仅在无梯度预览期间增加临时前向回调，清除每轮推理的重计算标记；正常结束和异常时都移除
临时回调并恢复原标记，保留原训练钩子及参数对象。此兼容逻辑依赖当前固定上游版本。

## 环境、任务与配置

独立 Python 3.12 位于 `extensions/diffsynth/.python/`，虚拟环境位于 `.venv/`。
PyTorch 2.8.0/cu128、torchvision 0.23.0 与 DiffSynth 依赖均独立安装，不共用 GUI 或其他训练器的 Python 包。
不需要 DeepSpeed、FlashAttention 或 Bash。显卡驱动仍由操作系统提供。

安装由现有 Task 管理一个安装监督进程，停止任务会终止完整子进程树。
安装、修复、卸载与训练通过同一环境锁协调；中断安装变为 broken，源码或依赖变化使 ready 失效。
DiffSynth 训练任务继续使用现有队列；重跑重新检查配置并建立新输出目录。

每次提交保存 UI TOML 与引擎参数 JSON，实际加载参数还保存在输出目录的 `engine_config.json` / `training_args.json`。
输出路径为 `output_dir/output_name/本次运行编号/`。配置沿用原有导入、导出、历史和重新编辑接口。
检查点只含 LoRA，不含优化器状态；已有 LoRA 可作为新训练起点。

## 缓存、优化器与 Alpha

“显存设置”中的 `cache_embeddings` 开启后，先逐条编码训练及预览文本，再编码训练图片。
两阶段分别只把 TE 或 VAE 搬到 GPU，完成后释放编码器；正式训练仅加载 DiT。
缓存使用上游 Processor、提示词模板、图片处理和 VAE 编码，不缓存训练噪声或时间步，
每次训练仍由上游损失函数重新采样。数据集重复次数和梯度检查点设置保持有效。

缓存放在 `extensions/diffsynth/cache/encodings/`，以图片路径/大小/修改时间、标注内容、
编码模型路径/大小/修改时间、Processor 内容、Transformers 版本和尺寸设置识别有效性。
未完成或不可读的条目重新生成；相同图片和标注可复用。手动更换文件时不要保留原大小和修改时间。
输出目录的 `encoding_cache.json` 记录本次使用的缓存条目。

缓存模式下预览使用已缓存的正负文本特征，不重载 TE；轻量预览 pipeline 共享训练中的
同一个 DiT 和 LoRA，不额外加载 DiT，也不改变优化器参数引用。常驻 DiT 不被搬到 CPU；
CPU 卸载模式继续使用原训练卸载器，每次推理前向后释放对应权重。VAE 在解码时临时加载，
完成后释放；预览仍会产生 VAE、KV cache 和临时张量开销，不承诺显存零增长。
未开启缓存时，模型 CPU 卸载仍不能与训练预览同时开启。

预览可设置 `sample_every_n_epochs`：留空使用 `sample_every_n_steps`；填写正整数 N 后，
每 N 轮完成时出图并覆盖步数出图，不叠加触发。以实际 batch 数识别轮次结束，支持梯度累积、
不足整批的尾批，以及按步数保存权重；轮次从 1 开始。

“训练参数”提供 `optimizer_type=AdamW|AdamW8bit`；后者使用独立环境中的 bitsandbytes 0.48.2。
`lora_alpha` 位于 Rank 后方，必须为有限正数。优化器选择受白名单限制，不接受任意 Python 导入路径。

## 分辨率、分桶和 batch

前端使用 `resolution="1024,1024"`，支持非正方形，宽高为 64 的倍数；旧的 `max_pixels`
仅在没有 resolution 时由后端兼容读取。开启 `enable_bucket` 后，按仓库内 Kohya 的
BucketManager/make_bucket_resolutions 规则选桶：最接近宽高比、等比缩放、中心裁剪，
缩小使用 OpenCV AREA，放大使用 PIL LANCZOS，保留 RGBA。
可设置 `min_bucket_reso`、`max_bucket_reso`、`bucket_reso_steps`（32 的正整数倍）。
`bucket_no_upscale` 开启时按原尺寸生成桶，忽略最小/最大桶边长；可能产生更多小桶。

关闭分桶按用户要求回退原 DiffSynth 策略，而非 Kohya 的固定尺寸模式：以 resolution
宽×高为最大面积，超限等比缩小，宽高向下对齐 32，使用上游 BILINEAR 缩放和中心裁剪，
小图不放大。依然仅合并相同实际尺寸，不能把不同形状的 latent 直接堆叠。

`train_batch_size` 为真实批大小，大于 1 时需开启预编码缓存。每个桶分别组批，每轮
重新打乱桶内样本，保留尾批，不跨桶混合、不补样本也不丢图。文本特征补齐到批内最长长度，
用掩码排除补齐 token；DiT 一次前向处理整个 batch。每轮 batch 数为各桶 ceil(样本数/BS)
之和；梯度累积、任务总步数与学习率调度均基于该数计算。输出 `buckets.json` 记录分布。
改变分桶/分辨率设置会生成新的 latent 缓存，文本缓存仍可复用。

## 学习率调度

提供 `lr_scheduler=constant|linear|cosine|cosine_with_restarts`，默认真正恒定。
上游原代码的 `ConstantLR(optimizer)` 默认前 5 次调度使用 1/3 基础学习率，现不再沿用这个隐含行为。
`lr_warmup_steps` 对所有策略生效，按优化器更新次数计，0 表示不预热；开启预热时从 0
线性升到基础学习率。线性/余弦在训练末尾降到 0；余弦重启次数仅对该策略显示和生效，
重启次数+1 为余弦周期数，重启不重复预热。预热必须短于总更新数，周期数不能超过剩余步数。

`lr_schedule.py` 只在隔离的上游函数全局环境中替换调度器和逐轮重排的数据加载器工厂，
不修改固定上游源码或全局 torch。CSV/TensorBoard 的 `learning_rate` 记录每次实际更新使用的值。
权重续训仍会开始新的调度，不能恢复优化器/调度器进度。

## 验证入口

`POST /api/engines/diffsynth/dry-run` 生成配置，不创建训练任务。
独立入口 `entry.py --check-only --project-root ... --config ...` 只导入上游及解析参数，不读训练模型张量。

前端：Node 22，`npm ci` 后运行 `npm run check`。
后端：`pytest tests/test_diffsynth_engine.py tests/test_diffsynth_review.py -q`。
上游回调和入口烟测需要 DiffSynth 依赖及固定源码；`test_diffsynth_comfy.py` 另需原版 ComfyUI 及其依赖。
具体证据与剩余验收项见 `mikazuki/engines/diffsynth/FIELD_NOTES.md`。
