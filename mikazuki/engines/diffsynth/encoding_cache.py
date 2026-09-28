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


def preview_key(sample, prompt):
    return digest([prompt, sample.get('controlImages', []), sample['width'], sample['height']]) if sample.get('controlImages') else prompt


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
    from .edit_images import load_references, resized_references
    editing = config.get('training_task') == 'image-edit'
    texts, images, items = {}, {}, []
    for i, row in enumerate(dataset.data):
        caption = row['prompt']
        refs = [file_stamp(Path(args.dataset_base_path) / p) for p in row.get('edit_image', [])] if editing else []
        # Vision-conditioned TE output depends on reference pixels AND target area.
        conditioning = [refs, config.get('bucket_settings'), args.max_pixels, args.height, args.width] if editing else []
        if editing:
            conditioning.append(dataset[i]['image'].size)
        text = root / (digest([identity, 'edit-text-v1', caption, conditioning]) + '.pth') if editing else root / (digest([identity, 'text', caption]) + '.pth')
        image_path = Path(args.dataset_base_path) / row['image']
        crop_identity = [('kohya-center-v1' if config['bucket_settings'].get('enable_bucket', True) else 'diffsynth-original-v1'), config['bucket_settings']] if config.get('bucket_settings') else 'RGBA-center-crop'
        image_identity = [identity, 'image', file_stamp(image_path), args.max_pixels, args.height, args.width, crop_identity]
        if editing:
            image_identity.append(conditioning)
        image = root / (digest(image_identity) + '.pth')
        texts[text] = (caption, i if editing else None)
        images[image] = i
        items.append((text, image))
    previews = {}
    if config['samples']['enabled']:
        for sample in config['samples']['samples']:
            for caption in ('', sample['prompt']):
                conditioning = [[file_stamp(p) for p in sample.get('controlImages', [])], sample['width'], sample['height']]
                path = root / (digest([identity, 'edit-preview-v1', caption, conditioning]) + '.pth') if editing else root / (digest([identity, 'text', caption]) + '.pth')
                texts[path] = (caption, sample if editing else None)
                previews[preview_key(sample, caption)] = path

    # Only complete, readable tensor payloads are reused after interruption.
    def ready(path, key):
        try:
            value = read_tensor(path)
            tensor = value[key]
            if editing and key == 'input_latents':
                refs = value.get('edit_latents')
                if not isinstance(refs, list) or not refs or any(not isinstance(t, torch.Tensor) or t.ndim != 4 or not t.numel() or not bool(torch.isfinite(t).all()) for t in refs):
                    return False
            if key == 'prompt_embeds':
                mask = value.get('edit_image_pad_mask')
                if not isinstance(mask, torch.Tensor) or mask.shape != tensor.shape[:2]:
                    return False
                if editing and not mask.any():
                    return False
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
            from .text_encoder_hooks import cleanup_text_encoder_hooks
            for n, path in enumerate(missing_texts, 1):
                with cleanup_text_encoder_hooks(pipe.text_encoder):
                    caption, source = texts[path]
                    references = None
                    if isinstance(source, int):
                        data = dataset[source]
                        references = resized_references(pipe, data['edit_image'], *data['image'].size)
                    elif isinstance(source, dict):
                        references = resized_references(pipe, load_references(source['controlImages']), source['width'], source['height'])
                    value = unit.process(pipe, caption, references)
                    write_tensor(path, value)
                del value
                print(f'[cache TE] {n}/{len(missing_texts)}', flush=True)
            del unit, pipe
            release()
            print('[cache] TE released from CPU and GPU', flush=True)
        if missing_images:
            pipe = QwenImage21Pipeline.from_pretrained(device='cpu', torch_dtype=torch.bfloat16,
                model_configs=[ModelConfig(path=paths[2])],
                processor_config=ModelConfig(str(processor)) if editing else None)
            pipe.device = device
            pipe.vae.to(device).eval()
            for n, path in enumerate(missing_images, 1):
                data = dataset[images[path]]
                latent = pipe.vae.encode(pipe.preprocess_image(data['image'].convert('RGBA')))
                payload = {'input_latents': latent}
                if editing:
                    references = resized_references(pipe, data['edit_image'], *data['image'].size)
                    payload['edit_latents'] = [pipe.vae.encode(pipe.preprocess_image(image)) for image in references]
                write_tensor(path, payload)
                del payload
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


def cached_sample(model, sample, paths, previews, processor_path=None):
    """Share the training DiT; only VAE and small inference state are temporary."""
    from diffsynth.core import ModelConfig
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline, QwenImage21Unit_PromptEmbedder
    from types import MethodType

    pipe = QwenImage21Pipeline(device=model.pipe.device, torch_dtype=model.pipe.torch_dtype)
    if sample.get('controlImages'):
        from transformers import AutoProcessor
        pipe.processor = AutoProcessor.from_pretrained(processor_path)
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
                return model.transfer_data_to_device(read_tensor(previews[preview_key(sample, prompt)]), pipeline.device, pipeline.torch_dtype)
            unit.process = MethodType(encoded, unit)
    try:
        with preview_offload(model):
            from .edit_images import load_references
            return pipe(edit_image=load_references(sample.get('controlImages', [])), prompt=sample['prompt'], negative_prompt='', width=sample['width'], height=sample['height'],
                        seed=sample['seed'], cfg_scale=sample['guidance_scale'],
                        num_inference_steps=sample['sample_steps'], tiled=True)
    finally:
        if pipe.vae is not None:
            pipe.vae.to('cpu')
        pipe.dit = None
        del pipe
        release()
