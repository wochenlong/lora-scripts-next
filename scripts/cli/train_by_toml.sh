#!/bin/bash
# LoRA train script by @Akegarasu
# DEPRECATED: Anima / 新特性请用 WebUI。仅作 SD1.5/SDXL 旧式 CLI 参考。

config_file="./config/default.toml"          # config file | 使用 toml 文件指定训练参数
sample_prompts="./config/sample_prompts.txt" # prompt file for sample | 采样 prompts 文件, 留空则不启用采样功能

sdxl=0      # train sdxl LoRA | 训练 SDXL LoRA
multi_gpu=0 # multi gpu | 多显卡训练 该参数仅限在显卡数 >= 2 使用

# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================

export HF_HOME="huggingface"
export TF_CPP_MIN_LOG_LEVEL=3
export PYTHONUTF8=1

extArgs=()
launchArgs=()

if [[ $multi_gpu == 1 ]]; then
  launchArgs+=("--multi_gpu")
  launchArgs+=("--num_processes=2")
fi

if [[ $sdxl == 1 ]]; then
  trainer_file="./vendor/sd-scripts/sdxl_train_network.py"
else
  trainer_file="./vendor/sd-scripts/train_network.py"
fi

python -m accelerate.commands.launch "${launchArgs[@]}" --num_cpu_threads_per_process=8 "$trainer_file" \
  --config_file="$config_file" \
  --sample_prompts="$sample_prompts" \
  "${extArgs[@]}"
