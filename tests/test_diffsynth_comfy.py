"""Optional integration against an unmodified ComfyUI checkout (CPU tensors).

Run with PYTHONPATH=<DiffSynth-Studio>:<ComfyUI> and its dependencies installed.
This checks native loader/patch math, not full-model inference quality.
"""
import sys
from types import SimpleNamespace
import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('comfy')
import comfy.options
comfy.options.enable_args_parsing()
_original_argv = sys.argv
sys.argv = ['comfy-compatibility-test', '--cpu']
try:
    import comfy.lora
    import comfy.model_base
finally:
    sys.argv = _original_argv
from mikazuki.engines.diffsynth.formats import export_comfy_lora


def test_native_comfy_loader_maps_and_patches_all_qwen_lora_keys(tmp_path, caplog):
    from safetensors.torch import save_file, load_file
    from peft import LoraConfig, inject_adapter_in_model
    class TinyMLP(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gate_layer = torch.nn.Linear(3, 4, bias=False)
            self.proj = torch.nn.Linear(3, 4, bias=False)
            self.out = torch.nn.Linear(4, 3, bias=False)
    class TinyDiT(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.transformer_blocks = torch.nn.ModuleList([torch.nn.Module()])
            self.transformer_blocks[0].img_mlp = TinyMLP()
    dit = TinyDiT()
    inject_adapter_in_model(LoraConfig(r=2, lora_alpha=2, target_modules=['gate_layer', 'proj', 'out']), dit)
    for name, p in dit.named_parameters():
        if p.requires_grad:
            p.data.copy_(torch.arange(p.numel()).reshape(p.shape) / 10 + 0.1)
    trainable = {name: p for name, p in dit.named_parameters() if p.requires_grad}
    state = export_comfy_lora(trainable)
    file = tmp_path / 'qwen-lora.safetensors'
    save_file(state, str(file))
    state = load_file(str(file))
    prefix = 'transformer_blocks.0.img_mlp.'
    fused_key, out_key = 'diffusion_model.' + prefix + 'gate_up.weight', 'diffusion_model.' + prefix + 'out.weight'
    # Same QwenImage21 class identity and weight layout used by Comfy's native loader.
    class TinyComfyModel(comfy.model_base.QwenImage21):
        def __init__(self):
            torch.nn.Module.__init__(self)
            self.model_config = SimpleNamespace(unet_config={})
        def state_dict(self):
            return {fused_key: torch.zeros(8, 3), out_key: torch.zeros(3, 4)}
    mapping = comfy.lora.model_lora_keys_unet(TinyComfyModel(), {})
    patches = comfy.lora.load_lora(state, mapping)
    assert len(patches) == 3
    assert not any('not loaded' in record.message.lower() for record in caplog.records)
    assembled = {fused_key: [], out_key: []}
    for target, patch in patches.items():
        key, offset = target if isinstance(target, tuple) else (target, None)
        assembled[key].append((1.0, patch, 1.0, offset, None))
    expected = {name: state[prefix + name + '.lora_B.weight'] @ state[prefix + name + '.lora_A.weight'] for name in ('gate_layer', 'proj', 'out')}
    actual = comfy.lora.calculate_weight(assembled[fused_key], torch.zeros(8, 3), fused_key)
    assert torch.allclose(actual, torch.cat([expected['gate_layer'], expected['proj']]))
    actual_out = comfy.lora.calculate_weight(assembled[out_key], torch.zeros(3, 4), out_key)
    assert torch.allclose(actual_out, expected['out'])
