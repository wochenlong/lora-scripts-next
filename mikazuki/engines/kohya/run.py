"""kohya builtin /api/run handler: straight pass-through to trainer_mapping.

The training pipeline itself is untouched — this is the same code that used to
be the fall-through branch of ``/api/run`` in ``mikazuki.app.api``.
"""

import os

from mikazuki.app.models import APIResponseFail
from mikazuki.app.train_submit import (
    _missing_standard_train_field,
    apply_anima_training_defaults,
    apply_sdxl_prediction_type,
    apply_tokenizer_cache_dir,
    get_sample_prompts,
    sanitize_config,
    should_generate_sample_prompts,
    toml,
)
from mikazuki.engines.runner import RunContext
from mikazuki.log import log
from mikazuki.utils import train_utils

import mikazuki.process as process

TRAINER_MAPPING = {
    "sd-lora": "./scripts/stable/train_network.py",
    "sdxl-lora": "./vendor/sd-scripts/sdxl_train_network.py",

    "sd-dreambooth": "./scripts/stable/train_db.py",
    "sdxl-finetune": "./scripts/stable/sdxl_train.py",

    "sd3-lora": "./scripts/dev/anima_train_network.py",
    "anima-lora": "./scripts/dev/anima_train_network.py",
    "anima-finetune": "./scripts/dev/anima_train.py",
    "flux-lora": "./scripts/dev/flux_train_network.py",
    "flux-finetune": "./scripts/dev/flux_train.py",
}


def handle_run(config: dict, ctx: RunContext):
    model_train_type = ctx.model_train_type
    toml_file = os.path.join(ctx.autosave_dir, f"{ctx.timestamp}.toml")

    train_data_dir = str(config.get("train_data_dir") or "").strip()
    if not train_data_dir:
        return _missing_standard_train_field("train_data_dir", "训练数据集路径")
    config["train_data_dir"] = train_data_dir

    pretrained_model = str(config.get("pretrained_model_name_or_path") or "").strip()
    if not pretrained_model:
        return _missing_standard_train_field("pretrained_model_name_or_path", "底模路径")
    config["pretrained_model_name_or_path"] = pretrained_model

    suggest_cpu_threads = 8 if len(train_utils.get_total_images(train_data_dir, limit=200)) >= 200 else 2
    trainer_file = TRAINER_MAPPING[model_train_type]
    apply_sdxl_prediction_type(config, model_train_type)
    apply_anima_training_defaults(config, model_train_type)

    if model_train_type != "sdxl-finetune":
        if not train_utils.validate_data_dir(train_data_dir):
            return APIResponseFail(message="训练数据集路径不存在或没有图片，请检查目录。")

    validated, message = train_utils.validate_model(pretrained_model, model_train_type)
    if not validated:
        return APIResponseFail(message=message)

    if "prompt_file" in config and config["prompt_file"].strip() != "":
        prompt_file = config["prompt_file"].strip()
        if not os.path.exists(prompt_file):
            return APIResponseFail(message=f"Prompt 文件 {prompt_file} 不存在，请检查路径。")
        config["sample_prompts"] = prompt_file
        train_utils.normalize_sample_prompt_file(prompt_file)
    elif should_generate_sample_prompts(config):
        try:
            positive_prompt, sample_prompts_arg = get_sample_prompts(config=config, model_train_type=model_train_type)

            if positive_prompt is not None and train_utils.is_promopt_like(sample_prompts_arg):
                sample_prompts_file = os.path.join(ctx.autosave_dir, f"{ctx.timestamp}-promopt.txt")
                with open(sample_prompts_file, "w", encoding="utf-8", newline="\n") as f:
                    f.write(sample_prompts_arg + "\n")
                config["sample_prompts"] = sample_prompts_file
                log.info(f"Wrote prompts to file {sample_prompts_file}")

        except ValueError as e:
            log.error(f"Error while processing prompts: {e}")
            return APIResponseFail(message=str(e))
    else:
        train_utils.strip_disabled_preview_fields(config)

    if config.get("sample_prompts"):
        train_utils.normalize_sample_prompt_file(str(config["sample_prompts"]))

    apply_anima_training_defaults(config, model_train_type)
    apply_tokenizer_cache_dir(config, model_train_type)
    sanitize_config(config)

    if not config.get("sample_prompts"):
        config.pop("sample_at_first", None)
        config.pop("sample_every_n_epochs", None)
        config.pop("sample_every_n_steps", None)

    with open(toml_file, "w", encoding="utf-8") as f:
        f.write(toml.dumps(config))

    result = process.run_train(toml_file, trainer_file, ctx.gpu_ids, suggest_cpu_threads,
                               metadata={"train_type": model_train_type})

    return result
