import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip('torch')
native = Path(__file__).resolve().parents[1] / 'extensions/moss/source'
if not (native / 'library/moss/lora.py').is_file():
    pytest.skip('MOSS runtime is not installed', allow_module_level=True)
sys.path.insert(0, str(native))
from library.moss.batching import bucket_batches
from library.moss.lora import LoRANetwork, load_network
from safetensors import safe_open
from safetensors.torch import save_file


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = torch.nn.ModuleList([torch.nn.Module() for _ in range(2)])
        for layer in self.layers:
            layer.proj = torch.nn.ModuleDict({name: torch.nn.Linear(8, 8, bias=False) for name in ('q', 'k', 'v', 'o', 'ffn_up_gate', 'ffn_down')})


def test_export_roundtrip_and_legacy_loading(tmp_path):
    model = TinyModel()
    network = LoRANetwork(model, rank=2, alpha=1)
    with torch.no_grad():
        for adapter in network.adapters.values():
            adapter.up.weight.normal_()
    path = tmp_path / 'comfy.safetensors'
    network.save(path, 'fp32')
    with safe_open(path, framework='pt') as f:
        assert len(f.keys()) == 36
        assert all(k.startswith('diffusion_model.layers.') for k in f.keys())
        assert float(f.get_tensor('diffusion_model.layers.0.proj.q.alpha')) == 1
    restored, _ = load_network(model, path, dtype=torch.float32)
    assert all(torch.equal(value, restored.state_dict()[key]) for key, value in network.state_dict().items())
    legacy = tmp_path / 'legacy.safetensors'
    save_file(network.state_dict(), legacy, metadata=network.metadata(lora_dtype='fp32'))
    restored_legacy, _ = load_network(model, legacy)
    assert all(torch.equal(value, restored_legacy.state_dict()[key]) for key, value in network.state_dict().items())


def test_bucket_batches_cover_samples_and_keep_tails():
    samples = [SimpleNamespace(stem=str(i), n_img=4, n_text=2) for i in range(7)]
    shapes = {str(i): ((2, 2) if i < 5 else (4, 1)) for i in range(7)}
    batches = bucket_batches(samples, shapes, 2)
    assert sorted(sample.stem for batch in batches for sample in batch) == [str(i) for i in range(7)]
    assert sorted(map(len, batches)) == [1, 2, 2, 2]
    assert all(len({shapes[sample.stem] for sample in batch}) == 1 for batch in batches)


def test_preview_cache_needs_no_symlink_privileges(tmp_path, monkeypatch):
    import hashlib
    import json
    from library.moss import generate, preview
    from library.moss.scan import TE_SUFFIX
    from library.moss.loader import MAX_SEQUENCE_LENGTH
    caption = tmp_path / 'caption with spaces.txt'
    caption.write_text('fixed caption', encoding='utf-8')
    cache = tmp_path / 'cache'
    cache.mkdir()
    metadata = {'caption_sha256':hashlib.sha256(b'fixed caption').hexdigest(), 'max_text_tokens':str(MAX_SEQUENCE_LENGTH)}
    for name in (caption.stem, '_empty'):
        save_file({'embeds':torch.zeros(2,8)}, cache/(name+TE_SUFFIX), metadata=metadata)
    out = tmp_path / 'epoch_01'
    out.mkdir()
    job = tmp_path / 'job.json'
    job.write_text(json.dumps({'prompt_file':str(caption), 'caption_sha256':hashlib.sha256(caption.read_bytes()).hexdigest(), 'cache':str(cache), 'out_dir':str(out)}))
    monkeypatch.setattr(generate, 'run_generate', lambda request: request)
    result = preview.generate_from_job(job)
    assert result.prompt == 'fixed caption'
    assert (out/'_te_cache').is_dir() and not (out/'_te_cache').is_symlink()
    assert len(list((out/'_te_cache').glob('*.safetensors'))) == 2
