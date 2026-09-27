"""Thin standalone entry, using the complete pinned DiffSynth checkout."""
import argparse
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
from functools import partial

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from mikazuki.engines.diffsynth.resource import environment_lock
from mikazuki.engines.diffsynth.settings import Runtime, TRAIN_SCRIPT


def main():
    if sys.platform == 'win32':
        # Upstream DiskMap periodically reopens safetensors mappings. On Windows
        # this can invalidate storage and crash in torch_cpu.dll (upstream #1563).
        # Keep mappings alive; this is a parameter-count threshold, not allocation.
        os.environ.setdefault('DIFFSYNTH_DISK_MAP_BUFFER_SIZE', '1000000000000')
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--check-only', action='store_true', help='Validate config and upstream parser; never load model tensors or train.')
    options = parser.parse_args()
    rt = Runtime(Path(options.project_root))
    config = json.loads(Path(options.config).read_text(encoding='utf-8'))
    sys.path.insert(0, str(rt.source))
    spec = importlib.util.spec_from_file_location('qwen21_upstream', rt.source / TRAIN_SCRIPT)
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    if importlib.util.find_spec('triton') is None:
        # torch.compile is lazy: importing Flex Attention succeeds even when
        # its CUDA compiler is absent. Use the upstream segmented SDPA path.
        import diffsynth.models.qwen_image_21_dit as qwen_dit
        qwen_dit.FLEX_ATTN_AVAILABLE = False
        print('Triton unavailable: using Qwen-Image-2.1 segmented PyTorch attention.', flush=True)
    argv = []
    for key, value in config['arguments'].items():
        if isinstance(value, bool):
            if value:
                argv.append('--' + key)
        else:
            argv.extend(['--' + key, str(value)])
    args = upstream.qwen_image_21_parser().parse_args(argv)
    if options.check_only:
        print(json.dumps({'arguments': vars(args), 'samples': config['samples'], 'model_components': [m['component'] for m in config['models']]}, ensure_ascii=False))
        return
    from mikazuki.engines.diffsynth.processor import ensure_processor
    args.processor_path = str(ensure_processor(rt.project_root))
    from accelerate import Accelerator
    from diffsynth.core import UnifiedDataset
    from diffsynth.diffusion import launch_training_task
    from mikazuki.engines.diffsynth.model_cache import materialize_models
    from mikazuki.engines.diffsynth.training import QwenLogger
    if args.customized_optimizer == 'bitsandbytes.optim.AdamW8bit':
        try:
            from bitsandbytes.optim import AdamW8bit  # noqa: F401
        except ImportError as exc:
            raise RuntimeError('AdamW8bit 需要 bitsandbytes，请在训练引擎管理中修复 DiffSynth 环境。') from exc
    alpha = float(config.get('lora_alpha', args.lora_rank))

    class TrainingModule(upstream.QwenImage21TrainingModule):
        def add_lora_to_model(self, model, target_modules, lora_rank, lora_alpha=None, upcast_dtype=None):
            return super().add_lora_to_model(model, target_modules, lora_rank, alpha, upcast_dtype)

    accelerator = Accelerator(gradient_accumulation_steps=args.gradient_accumulation_steps, mixed_precision='bf16')
    if accelerator.device.type != 'cuda':
        raise RuntimeError('DiffSynth 训练需要 CUDA GPU，但启动器选择了 CPU。请检查 CUDA_VISIBLE_DEVICES 和 Accelerate 配置，并重启 GUI 后重新提交训练。')
    with environment_lock(rt.root):
        paths = materialize_models(config['models'], config['cache_dir'])
        args.model_paths = json.dumps(paths)
        output = Path(args.output_path)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'engine_config.json').write_text(json.dumps({**config, 'arguments': vars(args)}, ensure_ascii=False, indent=2), encoding='utf-8')
        dataset = UnifiedDataset(base_path=args.dataset_base_path, metadata_path=args.dataset_metadata_path,
                                 repeat=args.dataset_repeat, data_file_keys=['image'],
                                 main_data_operator=UnifiedDataset.default_image_operator(base_path=args.dataset_base_path,
                                     max_pixels=args.max_pixels, height=args.height, width=args.width,
                                     height_division_factor=32, width_division_factor=32, convert_RGB=False, convert_RGBA=True))
        if config.get('bucket_settings'):
            from mikazuki.engines.diffsynth.buckets import BucketImageLoader
            dataset.main_data_operator = BucketImageLoader(args.dataset_base_path, config['bucket_settings'])
            (output / 'buckets.json').write_text(json.dumps(config['bucket_summary'], indent=2), encoding='utf-8')
            print('[buckets] ' + json.dumps(config['bucket_summary']) + '; batch_size=' + str(config['train_batch_size']), flush=True)
        # pandas represents an explicitly empty CSV caption as NaN. The UI preflight
        # already distinguishes it from a missing prompt column; preserve empty TXT semantics.
        for row in dataset.data:
            if isinstance(row['prompt'], float) and row['prompt'] != row['prompt']:
                row['prompt'] = ''
        sample_callback = None
        if config.get('cache_embeddings', False):
            from mikazuki.engines.diffsynth.encoding_cache import prepare_cache, cached_sample
            dataset, previews = prepare_cache(dataset, paths, args, config, accelerator.device)
            if config.get('bucket_settings'):
                from mikazuki.engines.diffsynth.buckets import batched_dataset
                dataset = batched_dataset(dataset, [tuple(s) for s in config['bucket_sizes']], config['train_batch_size'])
            args.model_paths = json.dumps([paths[0]])
            sample_callback = partial(cached_sample, paths=paths, previews=previews)
        parameters = inspect.signature(upstream.QwenImage21TrainingModule).parameters
        model_args = {key: value for key, value in vars(args).items() if key in parameters}
        model_args['device'] = 'cpu' if args.initialize_model_on_cpu or args.enable_model_cpu_offload else accelerator.device
        if args.lora_checkpoint:
            from safetensors.torch import load_file
            from mikazuki.engines.diffsynth.formats import prepare_lora_checkpoint
            model_args['lora_checkpoint'] = prepare_lora_checkpoint(load_file(args.lora_checkpoint), args.lora_rank, alpha)
        model = TrainingModule(**model_args)
        if config.get('cache_embeddings', False):
            model.pipe.units = []
            assert model.pipe.text_encoder is None and model.pipe.vae is None
            print('[training] DiT only; TE/VAE absent; optimizer=' + str(args.customized_optimizer)
                  + f'; rank={args.lora_rank}, alpha={alpha}', flush=True)
        logger = QwenLogger(args.output_path, config['samples'], config['output_name'], alpha, sample_callback, len(dataset))
        from mikazuki.engines.diffsynth.lr_schedule import launch_with_schedule, schedule_config
        import math
        total_steps = math.ceil(len(dataset) / args.gradient_accumulation_steps) * args.num_epochs
        settings = config.get('lr_schedule') or schedule_config({}, total_steps)
        if settings['total_steps'] != total_steps:
            raise ValueError('学习率总步数与实际数据集不一致，请重新提交配置')
        launch_with_schedule(accelerator, dataset, model, logger, args, settings)


if __name__ == '__main__':
    main()
