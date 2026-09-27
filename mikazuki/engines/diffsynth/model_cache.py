"""Executed only in the independent training Python; source weights are read-only."""
import json
from pathlib import Path
import shutil
import uuid

from safetensors import safe_open
from safetensors.torch import save_file
from .inputs import cache_key


def materialize_models(models, cache_dir):
    paths = []
    for model in models:
        plan = model['conversion']
        if all(target == source and op == 'identity' for target, (source, op) in plan.items()):
            paths.append(model['files'])
            continue
        key = cache_key(model['files'])
        directory = Path(cache_dir) / ('v1-' + model['component'] + '-' + key)
        manifest = directory / 'files.json'
        if not manifest.is_file():
            temporary = directory.with_name(directory.name + '.partial-' + uuid.uuid4().hex)
            temporary.mkdir(parents=True)
            try:
                files = []
                for index, source_path in enumerate(model['files']):
                    tensors = {}
                    with safe_open(source_path, framework='pt', device='cpu') as source:
                        available = set(source.keys())
                        for target, (source_key, op) in plan.items():
                            if source_key not in available:
                                continue
                            tensor = source.get_tensor(source_key)
                            if op == 'first_half':
                                tensor = tensor[:tensor.shape[0] // 2]
                            elif op == 'second_half':
                                tensor = tensor[tensor.shape[0] // 2:]
                            elif op == 'squeeze_time':
                                tensor = tensor.squeeze(2)
                            tensors[target] = tensor.contiguous()
                        name = f'model-{index:05d}.safetensors'
                        save_file(tensors, str(temporary / name), metadata={'format': 'pt'})
                    del tensors
                    files.append(name)
                (temporary / 'files.json').write_text(json.dumps(files), encoding='utf-8')
                temporary.rename(directory)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        files = json.loads(manifest.read_text(encoding='utf-8'))
        paths.append([str(directory / name) for name in files])
    return paths
