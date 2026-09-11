# 程序参数

`gui.py` 支持以下命令行参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--host` | str | `127.0.0.1` | 服务器主机名 |
| `--port` | int | `28000` | GUI 端口 |
| `--listen` | bool | `false` | 监听所有网卡（`0.0.0.0`） |
| `--skip-prepare-environment` | bool | `false` | 跳过环境准备 |
| `--disable-tensorboard` | bool | `false` | 禁用 TensorBoard |
| `--disable-tageditor` | bool | `false` | 禁用标签编辑器 |
| `--disable-train-monitor` | bool | `false` | 禁用训练监控页 |
| `--tensorboard-host` | str | `127.0.0.1` | TensorBoard 主机 |
| `--tensorboard-port` | int | `6006` | TensorBoard 端口 |
| `--train-monitor-port` | int | `6008` | 训练监控页端口 |
| `--localization` | str | | 界面语言 |
| `--dev` | bool | `false` | 开发者模式 |

## 示例

```bash
# 本地默认启动
python gui.py

# 监听所有网卡（远程访问）
python gui.py --listen

# AutoDL 环境（自定义端口）
python gui.py --port 6006 --listen --skip-prepare-environment --disable-tensorboard

# 禁用训练监控
python gui.py --disable-train-monitor
```

## 纯命令行训练入口

如果云平台不能访问 WebUI，可以直接使用 CLI 脚本训练。注意：根目录 `train.sh` 是旧式 SD/SDXL/Flux LoRA 入口，Anima 有独立入口。

| 场景 | 命令 |
|------|------|
| SD/SDXL/Flux 旧式 LoRA | `bash train.sh` |
| TOML 方式 SD/SDXL LoRA | `bash train_by_toml.sh path/to/config.toml` |
| Anima LoRA 标准模式（非 Fast） | `bash train_anima_by_toml.sh docs/examples/anima-lora-benchmark-kohya.toml` |
| Anima LoRA Fast 插件模式 | `bash scripts/cli/install_anima_fast.sh` 后运行 `bash train_anima_fast_by_toml.sh docs/examples/anima-lora-benchmark-fast.toml` |
| Anima 全量微调 | `python scripts/dev/anima_train.py --config_file docs/examples/anima-full-finetune.toml` |

Anima 标准模式配置示例：`docs/examples/anima-lora-benchmark-kohya.toml`。训练前请复制一份并修改：

- `pretrained_model_name_or_path`：Anima DiT 主权重，例如 `./sd-models/anima/anima-base-v1.0.safetensors`
- `vae`：Qwen Image VAE，例如 `./sd-models/anima/qwen_image_vae.safetensors`
- `qwen3`：Qwen3 文本模型，例如 `./sd-models/anima/qwen_3_06b_base.safetensors`
- `dataset_config`：数据集配置 TOML，示例为 `docs/examples/anima-lora-benchmark-dataset.toml`
- `output_dir` / `output_name`：输出目录与模型名称
