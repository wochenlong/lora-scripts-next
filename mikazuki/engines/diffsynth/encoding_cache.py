"""Local text/latent cache. Reuse upstream encoders; never cache training noise."""
import gc
import hashlib
import json
import pickle
from contextlib import contextmanager
from pathlib import Path
import torch


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_stamp(path):
    path = Path(path).resolve()
    stat = path.stat()
    return [str(path), stat.st_size, stat.st_mtime_ns]


def cpu_tree(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().contiguous()
    if isinstance(value, dict):
        return {k: cpu_tree(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(cpu_tree(v) for v in value)
    return value


def write_tensor(path, value):
    temporary = path.with_suffix('.tmp')
    torch.save(cpu_tree(value), temporary)
    temporary.replace(path)


def read_tensor(path):
    return torch.load(path, map_location='cpu', weights_only=True)


def release():
    gc.collect()
    torch.cuda.empty_cache()


class EncodedDataset(torch.utils.data.Dataset):
    load_from_cache = True

    def __init__(self, items, repeat, args):
        self.items, self.repeat, self.args = items, repeat, args

    def __len__(self):
        return len(self.items) * self.repeat

    def __getitem__(self, index):
        text, image = self.items[index % len(self.items)]
        shared = read_tensor(image)
        shared.update(use_gradient_checkpointing=self.args.use_gradient_checkpointing,
                      use_gradient_checkpointing_offload=self.args.use_gradient_checkpointing_offload)
        return shared, read_tensor(text), {}


def prepare_cache(dataset, paths, args, config, device):
    from diffsynth.core import ModelConfig
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline, QwenImage21Unit_PromptEmbedder
    import transformers

    root = Path(config['cache_dir']).parent / 'encodings'
    root.mkdir(parents=True, exist_ok=True)
    processor = Path(args.processor_path)
    identity = {'version': 1, 'transformers': transformers.__version__,
                'processor': [(p.name, hashlib.sha256(p.read_bytes()).hexdigest())
                              for p in sorted(processor.iterdir()) if p.is_file()],
                'te': [file_stamp(p) for p in paths[1]], 'vae': [file_stamp(p) for p in paths[2]]}
    texts, images, items = {}, {}, []
    for i, row in enumerate(dataset.data):
        caption = row['prompt']
        text = root / (digest([identity, 'text', caption]) + '.pth')
        image_path = Path(args.dataset_base_path) / row['image']
        crop_identity = [('kohya-center-v1' if config['bucket_settings'].get('enable_bucket', True) else 'diffsynth-original-v1'), config['bucket_settings']] if config.get('bucket_settings') else 'RGBA-center-crop'
        image = root / (digest([identity, 'image', file_stamp(image_path), args.max_pixels,
                               args.height, args.width, crop_identity]) + '.pth')
        texts[text] = caption
        images[image] = i
        items.append((text, image))
    previews = {}
    if config['samples']['enabled']:
        for caption in ['', *[s['prompt'] for s in config['samples']['samples']]]:
            path = root / (digest([identity, 'text', caption]) + '.pth')
            texts[path] = caption
            previews[caption] = path

    # Only complete, readable tensor payloads are reused after interruption.
    def ready(path, key):
        try:
            value = read_tensor(path)
            tensor = value[key]
            return (isinstance(tensor, torch.Tensor) and tensor.numel() > 0
                    and tensor.ndim == (4 if key == 'input_latents' else 3)
                    and bool(torch.isfinite(tensor).all()))
        except (OSError, RuntimeError, ValueError, KeyError, EOFError, pickle.UnpicklingError):
            return False

    missing_texts = [p for p in texts if not ready(p, 'prompt_embeds')]
    missing_images = [p for p in images if not ready(p, 'input_latents')]
    print(f'[cache] text {len(texts)-len(missing_texts)}/{len(texts)} reused; '
          f'VAE {len(images)-len(missing_images)}/{len(images)} reused', flush=True)
    with torch.no_grad():
        if missing_texts:
            pipe = QwenImage21Pipeline.from_pretrained(device='cpu', torch_dtype=torch.bfloat16,
                model_configs=[ModelConfig(path=paths[1])], processor_config=ModelConfig(str(processor)))
            pipe.device = device
            pipe.text_encoder.to(device).eval()
            unit = QwenImage21Unit_PromptEmbedder()
            norm = pipe.text_encoder.model.model.language_model.norm
            for n, path in enumerate(missing_texts, 1):
                hooks = set(norm._forward_hooks)
                try:
                    value = unit.process(pipe, texts[path], None)
                    write_tensor(path, value)
                finally:
                    # Upstream registers a new temporary capture hook on every call.
                    for key in set(norm._forward_hooks) - hooks:
                        del norm._forward_hooks[key]
                del value
                print(f'[cache TE] {n}/{len(missing_texts)}', flush=True)
            del norm, unit, pipe
            release()
            print('[cache] TE released from CPU and GPU', flush=True)
        if missing_images:
            pipe = QwenImage21Pipeline.from_pretrained(device='cpu', torch_dtype=torch.bfloat16,
                model_configs=[ModelConfig(path=paths[2])])
            pipe.device = device
            pipe.vae.to(device).eval()
            for n, path in enumerate(missing_images, 1):
                data = dataset[images[path]]
                latent = pipe.vae.encode(pipe.preprocess_image(data['image'].convert('RGBA')))
                write_tensor(path, {'input_latents': latent})
                del latent, data
                print(f'[cache VAE] {n}/{len(missing_images)}', flush=True)
            del pipe
            release()
            print('[cache] VAE released from CPU and GPU', flush=True)
    manifest = {'version': 1, 'rows': len(items), 'repeat': dataset.repeat,
                'items': [[str(a), str(b)] for a, b in items],
                'preview_texts': {k: str(v) for k, v in previews.items()}}
    Path(args.output_path, 'encoding_cache.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[cache] complete; training will load DiT only (TE=None, VAE=None)', flush=True)
    return EncodedDataset(items, dataset.repeat, args), previews


@contextmanager
def preview_offload(model):
    """Keep each inference forward offloaded, without altering training hooks."""
    manager = getattr(model, '_preview_offload_manager', None)
    handles, states = [], []
    try:
        if manager is not None:
            for unit in manager.units:
                states.append((unit, unit._in_recompute.copy()))
                unit._in_recompute.clear()
                # The upstream forward hook normally keeps subsequent recomputes
                # resident for backward. Inference has no backward/recompute.
                def finish_forward(module, args, output, unit=unit):
                    unit._in_recompute.clear()
                handles.append(unit.param_manager.model.register_forward_hook(finish_forward))
        yield
    finally:
        for handle in handles:
            handle.remove()
        for unit, state in states:
            for offloader in unit.param_manager.param_offloaders.values():
                offloader.offload()
            unit._in_recompute.clear()
            unit._in_recompute.update(state)


def cached_sample(model, sample, paths, previews):
    """Share the training DiT; only VAE and small inference state are temporary."""
    from diffsynth.core import ModelConfig
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline, QwenImage21Unit_PromptEmbedder
    from types import MethodType

    pipe = QwenImage21Pipeline(device=model.pipe.device, torch_dtype=model.pipe.torch_dtype)
    pipe.dit = model.pipe.dit
    assert pipe.dit is model.pipe.dit
    print('[sampling] reusing training DiT; no second DiT loaded', flush=True)

    def load_components(self, names):
        # Never .to() the shared DiT: it is either resident or managed by the
        # original training offload hooks; optimizer parameter identities stay put.
        if 'vae' in names and self.vae is None:
            vae_pipe = QwenImage21Pipeline.from_pretrained(device='cpu', torch_dtype=self.torch_dtype,
                                                          model_configs=[ModelConfig(path=paths[2])])
            self.vae = vae_pipe.vae
            self.vae.to(self.device).eval()
    pipe.load_models_to_device = MethodType(load_components, pipe)
    # The regular inference units remain intact except prompt encoding.
    for unit in pipe.units:
        if isinstance(unit, QwenImage21Unit_PromptEmbedder):
            def encoded(self, pipeline, prompt, edit_image):
                return model.transfer_data_to_device(read_tensor(previews[prompt]), pipeline.device, pipeline.torch_dtype)
            unit.process = MethodType(encoded, unit)
    try:
        with preview_offload(model):
            return pipe(prompt=sample['prompt'], negative_prompt='', width=sample['width'], height=sample['height'],
                        seed=sample['seed'], cfg_scale=sample['guidance_scale'],
                        num_inference_steps=sample['sample_steps'], tiled=True)
    finally:
        if pipe.vae is not None:
            pipe.vae.to('cpu')
        pipe.dit = None
        del pipe
        release()
