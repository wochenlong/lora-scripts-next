"""ai-toolkit run.py driver: apply pack-side overrides, then hand off to upstream.

Runs inside the extension venv with cwd = toolkit source root (launcher
contract). Binds Klein's class-level TE path, SDXL's local single-file configs,
and Qwen's native component loaders before handing off. No weights are copied
or rewritten. The upstream run.py receives the training seed through SEED.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def local_component_loader(model_class, path, config_dir):
    """Bind a native v2 loader to explicit files for this training subprocess."""
    original = model_class.load_model.__func__

    def load(cls, name_or_path, *args, **kwargs):
        kwargs['config_path'] = config_dir
        kwargs['use_comfy_weights'] = False
        kwargs['local_files_only'] = True
        return original(cls, path, *args, **kwargs)

    model_class.load_model = classmethod(load)


def preserve_qwen_reference_size(encoder_class):
    original = encoder_class.load_processor.__func__

    def load(cls, *args, **kwargs):
        processor = original(cls, *args, **kwargs)
        # Qwen already grid-resizes references for both TE and VAE. The
        # processor's minimum-area resize would change only the TE slot count.
        processor.image_processor.do_resize = False
        return processor

    encoder_class.load_processor = classmethod(load)


def apply_local_inputs(model):
    options = model.get('model_kwargs', {})
    if model.get('arch') == 'sdxl' and options.get('next_trainer_sdxl_config'):
        from diffusers import StableDiffusionXLPipeline
        original = StableDiffusionXLPipeline.from_single_file.__func__

        def load(cls, path, **kwargs):
            return original(cls, path, config=options['next_trainer_sdxl_config'], local_files_only=True, **kwargs)

        StableDiffusionXLPipeline.from_single_file = classmethod(load)
    components = options.get('next_trainer_components')
    if model.get('arch') == 'qwen_image_2':
        from extensions_built_in.diffusion_models.qwen_image_2.qwen_image_2 import (
            QwenImage21Transformer2DModel, QwenImage21TextEncoder, AutoencoderKLQwenImage21,
        )
        preserve_qwen_reference_size(QwenImage21TextEncoder)
        if components:
            for key, cls in [('transformer', QwenImage21Transformer2DModel), ('text_encoder', QwenImage21TextEncoder), ('vae', AutoencoderKLQwenImage21)]:
                local_component_loader(cls, components[key], model['extras_name_or_path'])


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: driver.py <config.yaml> [run.py args...]")
    root = Path.cwd().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import yaml
    job = yaml.safe_load(Path(sys.argv[1]).read_text(encoding='utf-8'))
    model = job['config']['process'][0]['model']
    # Upstream run.py consumes SEED from the environment, not TrainConfig.seed.
    os.environ['SEED'] = str(job['config']['process'][0]['train']['seed'])
    te_path = os.environ.get("AI_TOOLKIT_TE_PATH", "").strip()
    if te_path and model.get('arch', '').startswith('flux2_klein_'):
        from extensions_built_in.diffusion_models.flux2 import Flux2Klein4BModel, Flux2Klein9BModel

        Flux2Klein4BModel.flux2_klein_te_path = te_path
        Flux2Klein9BModel.flux2_klein_te_path = te_path

    apply_local_inputs(model)

    sys.argv = ["run.py", *sys.argv[1:]]
    runpy.run_path(str(root / "run.py"), run_name="__main__")


if __name__ == "__main__":
    main()
