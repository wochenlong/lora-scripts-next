"""Review contracts. Synthetic tensors only: never load/train Qwen model weights."""
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_diffsynth_engine import configured
from mikazuki.engines.diffsynth.adapter import adapt_config, dump_config
from mikazuki.engines.diffsynth.inputs import dataset_inputs, weight_files, tensor_headers
from mikazuki.engines.diffsynth.samples import sample_config, DEFAULT_SAMPLE


@pytest.mark.parametrize('extension', ['json', 'jsonl', 'csv'])
def test_native_metadata_preserves_source_and_ignores_directory_repeat(configured, extension):
    rt, config = configured
    base = Path(config['train_data_dir'])
    row = {'image': '3_character/sample.png', 'prompt': ''}
    file = base / ('metadata.' + extension)
    file.write_text(json.dumps([row]) if extension == 'json' else json.dumps(row) + '\n' if extension == 'jsonl' else 'image,prompt\n3_character/sample.png,\n', encoding='utf-8')
    config.update(dataset_format='metadata', dataset_base_path=str(base), dataset_metadata_path=str(file), dataset_repeat=99)
    original = file.read_bytes()
    adapted = adapt_config(config, rt)
    assert adapted.arguments['dataset_repeat'] == 1
    assert adapted.dataset == [row]
    saved = dump_config(adapted, rt.project_root / 'auto', 'test')
    assert json.loads(saved.read_text())['arguments']['dataset_metadata_path'] == str(file)
    assert original == file.read_bytes()


def test_mixed_directory_repeats_and_empty_caption(configured):
    rt, config = configured
    base = Path(config['train_data_dir'])
    (base / 'ordinary').mkdir()
    for path in [base / 'root.png', base / 'ordinary/a.png']:
        Image.new('RGB', (32, 32)).save(path)
        path.with_suffix('.txt').write_text('')
    config['dataset_repeat'] = 2
    adapted = adapt_config(config, rt)
    assert len(adapted.dataset) == 5
    assert adapted.arguments['dataset_repeat'] == 2
    assert sum(row['prompt'] == '' for row in adapted.dataset) == 2


def test_comfy_component_mode_and_processor_errors(configured):
    rt, config = configured
    model = Path(config['diffsynth_model_dir'])
    config.update(model_input_mode='components', dit_path=str(model / 'transformer'), text_encoder_path=str(model / 'text_encoder'), vae_path=str(model / 'vae'))
    adapted = adapt_config(config, rt)
    assert len(adapted.engine['models']) == 3
    plan = adapted.engine['models'][0]['conversion']
    assert plan['transformer_blocks.0.img_mlp.gate_layer.weight'][1] == 'first_half'
    assert plan['transformer_blocks.0.img_mlp.proj.weight'][1] == 'second_half'
    assert any(op == 'squeeze_time' for _, op in adapted.engine['models'][2]['conversion'].values())
    (model / 'processor/tokenizer.json').unlink()
    with pytest.raises(ValueError, match='Processor'):
        adapt_config(config, rt)


def test_bad_index_and_ambiguous_models_fail(tmp_path):
    index = tmp_path / 'model.safetensors.index.json'
    index.write_text(json.dumps({'weight_map': {'x': '../outside.safetensors'}}))
    with pytest.raises(ValueError, match='越界'):
        weight_files(index, 'dit_path')
    index.unlink()
    for name in ('a.safetensors', 'b.safetensors'):
        (tmp_path / name).touch()
    with pytest.raises(ValueError, match='多个候选'):
        weight_files(tmp_path, 'dit_path')


def test_bf16_and_header_integrity(tmp_path):
    torch = pytest.importorskip('torch')
    from safetensors.torch import save_file
    file = tmp_path / 'test.safetensors'
    save_file({'weight': torch.zeros(2, 3)}, str(file))
    with pytest.raises(ValueError, match='BF16'):
        tensor_headers([file], 'dit_path')
    save_file({'weight': torch.zeros(2, 3, dtype=torch.bfloat16)}, str(file))
    assert tensor_headers([file], 'dit_path')['weight']['shape'] == [2, 3]
    file.write_bytes(file.read_bytes()[:-1])
    with pytest.raises(ValueError, match='truncated'):
        tensor_headers([file], 'dit_path')


def test_conversion_cache_changes_values_correctly_and_keeps_original(tmp_path):
    torch = pytest.importorskip('torch')
    from safetensors.torch import save_file, load_file
    from mikazuki.engines.diffsynth.model_cache import materialize_models
    source = tmp_path / 'comfy.safetensors'
    fused = torch.arange(24, dtype=torch.bfloat16).reshape(8, 3)
    vae = torch.arange(6, dtype=torch.bfloat16).reshape(2, 3, 1, 1, 1)
    save_file({'fused': fused, 'conv': vae}, str(source))
    original = source.read_bytes()
    models = [{'component': 'test', 'files': [str(source)], 'conversion': {
        'gate': ['fused', 'first_half'], 'proj': ['fused', 'second_half'], 'vae': ['conv', 'squeeze_time']}}]
    paths = materialize_models(models, tmp_path / 'cache')
    state = load_file(paths[0][0])
    assert torch.equal(state['gate'], fused[:4]) and torch.equal(state['proj'], fused[4:])
    assert torch.equal(state['vae'], vae.squeeze(2))
    assert source.read_bytes() == original
    assert paths == materialize_models(models, tmp_path / 'cache')
    save_file({'fused': fused + 1, 'conv': vae}, str(source))
    assert paths != materialize_models(models, tmp_path / 'cache')


def test_preview_configuration_roundtrips_and_rejects_unsupported_fields(configured):
    from mikazuki.utils.config_import import validate_config_import
    from mikazuki.utils.config_export import normalize_config_for_export
    rt, config = configured
    config.update(sample_enabled=True, sample_every_n_steps=7, preview_samples=[json.dumps({**DEFAULT_SAMPLE, 'prompt': '中文'}), json.dumps({**DEFAULT_SAMPLE, 'seed': 99})])
    exported, _ = normalize_config_for_export(config, page_train_type='qwen-image-21-lora')
    restored = validate_config_import('qwen-image-21-lora', exported)['config']
    assert adapt_config(restored, rt).engine['samples']['samples'][1]['seed'] == 99
    with pytest.raises(ValueError, match='不支持'):
        sample_config({**config, 'preview_samples': [json.dumps({'prompt': '', 'sampler': 'bogus'})]})
    with pytest.raises(ValueError, match='CPU 卸载'):
        adapt_config({**config, 'enable_model_cpu_offload': True}, rt)


def test_optimizer_updates_not_microsteps_drive_logging(tmp_path):
    torch = pytest.importorskip('torch')
    pytest.importorskip('diffsynth')
    from mikazuki.engines.diffsynth.training import QwenLogger
    logger = QwenLogger(tmp_path, {'enabled': False}, 'test')
    losses, saves = [], []
    logger.loggers_initialized = True
    logger.loggers = [SimpleNamespace(log=lambda key, value, step: losses.append((step, value)))]
    logger.save_model = lambda accelerator, model, name: saves.append(name)
    accelerator = SimpleNamespace(sync_gradients=False, optimizer_step_was_skipped=False, is_main_process=True)
    # Three microbatches at accumulation=2: includes the final incomplete update.
    for sync, loss in [(False, 2.), (True, 4.), (True, 8.)]:
        accelerator.sync_gradients = sync
        logger.on_step_end(accelerator, None, save_steps=2, loss=torch.tensor(loss))
    assert losses == [(1, 3.), (2, 8.)]
    assert saves == ['step-2.safetensors']


def test_preview_restores_rng_scheduler_modes_and_serves_existing_api(tmp_path):
    torch = pytest.importorskip('torch')
    np = pytest.importorskip('numpy')
    pytest.importorskip('diffsynth')
    from mikazuki.engines.diffsynth.training import QwenLogger
    from mikazuki.utils.task_insights import list_preview_images
    class Pipeline(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.scheduler = {'training': True}
        def forward(self, **kwargs):
            random.random(); np.random.rand(); torch.rand(1)
            self.scheduler['training'] = False
            return Image.new('RGB', (kwargs['width'], kwargs['height']))
    model = torch.nn.Module()
    model.pipe = Pipeline()
    model.train()
    rng = torch.random.get_rng_state().clone()
    original_scheduler = model.pipe.scheduler
    logger = QwenLogger(tmp_path, {'enabled': True, 'every_steps': 1, 'samples': [{**DEFAULT_SAMPLE, 'width': 32, 'height': 64}]}, 'test')
    logger.num_steps = 4
    logger.sample(model)
    assert torch.equal(rng, torch.random.get_rng_state())
    assert model.training and model.pipe.training
    assert model.pipe.scheduler is original_scheduler and original_scheduler['training']
    previews = list_preview_images({'backend': 'diffsynth', 'output_dir': str(tmp_path), 'output_name': 'test'})
    assert len(previews) == 1 and previews[0]['step'] == 4 and previews[0]['sample_id'] == 1
    assert Image.open(tmp_path / 'sample' / previews[0]['name']).size == (32, 64)


def test_install_task_cancels_supervisor_and_child_then_releases_lock(tmp_path, monkeypatch):
    import sys
    import time
    import psutil
    from mikazuki.engines.diffsynth import installer
    from mikazuki.engines.diffsynth.settings import Runtime
    from mikazuki.engines.diffsynth.resource import environment_lock
    from mikazuki.engines.diffsynth.extension_state import read_status
    from mikazuki.tasks import TaskStatus
    rt = Runtime(tmp_path)
    pid_file = tmp_path / 'child.pid'
    code = "import os,time;from pathlib import Path;Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid()));time.sleep(60)"
    monkeypatch.setattr(installer, 'installation_plan', lambda runtime, sources: [[sys.executable, '-c', code]])
    result = installer.start_install(rt)
    task = installer.tm.tasks[result['task_id']]
    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert pid_file.exists()
        pid = int(pid_file.read_text())
        with pytest.raises(ValueError, match='正在使用'):
            with environment_lock(rt.root):
                pass
        with pytest.raises(ValueError, match='尚未结束'):
            installer.remove_extension(rt)
        installer.tm.terminate_task(task.task_id)
        task.wait()
        assert task.status == TaskStatus.TERMINATED
        assert not psutil.pid_exists(pid)
        assert read_status(rt)['state'] == 'broken'
        with environment_lock(rt.root):
            pass
    finally:
        if task.status == TaskStatus.RUNNING:
            task.terminate()
        installer.tm.tasks.pop(task.task_id, None)


def test_ready_becomes_broken_on_environment_drift(tmp_path):
    from mikazuki.engines.diffsynth.settings import Runtime, TRAIN_SCRIPT
    from mikazuki.engines.diffsynth.extension_state import write_state, read_status, fingerprint
    rt = Runtime(tmp_path)
    rt.python.parent.mkdir(parents=True)
    rt.python.touch()
    file = rt.source / TRAIN_SCRIPT
    file.parent.mkdir(parents=True)
    file.write_text('# initial')
    write_state(rt, 'ready', {'fingerprint': fingerprint(rt)})
    assert read_status(rt)['state'] == 'ready'
    file.write_text('# changed')
    assert read_status(rt)['state'] == 'broken'


def test_http_run_spawns_real_entry_parser_without_training(configured, monkeypatch):
    import sys
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    from mikazuki.engines.diffsynth import run
    from mikazuki.tasks import TaskManager
    from mikazuki.train_log_hub import hub
    rt, config = configured
    source = Path(__file__).resolve().parents[2] / 'DiffSynth-Studio'
    if not source.exists():
        pytest.skip('Pinned upstream checkout required for subprocess smoke')
    pytest.importorskip('diffsynth')
    rt.root.mkdir(parents=True)
    rt.source.symlink_to(source, target_is_directory=True)
    (rt.root / '.venv').symlink_to(Path(sys.prefix), target_is_directory=True)
    monkeypatch.chdir(rt.project_root)
    monkeypatch.setattr(run, 'check_runtime', lambda runtime: None)  # Test-only CUDA gate substitute.
    manager = TaskManager()
    monkeypatch.setattr(run, 'tm', manager)
    def submit(task):
        task.command.append('--check-only')  # Real parser/import path, no tensors/training.
        task.execute()
        task.wait()
    monkeypatch.setattr(manager, 'submit', submit)
    response = TestClient(app).post('/api/run', json={**config, 'gradient_accumulation_steps': 2}).json()
    assert response['status'] == 'success', response
    task = manager.tasks[response['data']['task_id']]
    assert task.returncode == 0, hub.tail(task.task_id, 30)
    output = '\n'.join(hub.tail(task.task_id, 20))
    assert 'model_components' in output
    assert '"lora_rank": 8' in output
    assert task.metadata['total_steps'] == 4  # ceil(3/2) * 2 epochs
    assert not Path(task.metadata['output_dir']).exists()


def test_retry_uses_new_output_and_reruns_preflight(configured, monkeypatch):
    from fastapi.testclient import TestClient
    from mikazuki.app.application import app
    from mikazuki.engines.diffsynth import run
    from mikazuki.tasks import TaskStatus
    rt, config = configured
    monkeypatch.chdir(rt.project_root)
    monkeypatch.setattr(run, 'check_runtime', lambda runtime: None)
    submitted = []
    monkeypatch.setattr(run.tm, 'submit', submitted.append)
    client = TestClient(app)
    first = client.post('/api/run', json=config).json()
    task = submitted[0]
    try:
        stored = client.get('/api/tasks/' + task.task_id + '/config').json()['data']
        assert stored['train_type'] == 'qwen-image-21-lora'
        assert stored['config']['diffsynth_model_dir'] == config['diffsynth_model_dir']
        task.status = TaskStatus.FINISHED
        result = client.get('/api/tasks/retry/' + task.task_id).json()
        assert result['status'] == 'success', result
        retried = submitted[1]
        assert retried.metadata['output_dir'] != task.metadata['output_dir']
        assert result['data']['task_ids'] == [retried.task_id]
        assert retried.metadata['config_path'] != task.metadata['config_path']
        task.status = TaskStatus.FINISHED
        (Path(config['train_data_dir']) / '3_character/sample.txt').unlink()
        result = client.get('/api/tasks/retry/' + task.task_id).json()
        assert result['status'] == 'fail' and '标注' in result['message']
    finally:
        for task in submitted:
            run.tm.tasks.pop(task.task_id, None)


def test_worker_progress_uses_existing_hub_event_stream():
    from mikazuki.train_log_hub import TrainLogHub
    hub = TrainLogHub()
    hub.start_task('install')
    hub.append_line('install', '[mikazuki-progress] {"percent": 25, "message": "installing"}\n')
    events, _, _ = hub.snapshot_events_from('install', 0)
    assert events == [{'type': 'progress', 'percent': 25, 'message': 'installing'}]
    hub.append_line('install', '[mikazuki-progress] malformed')
    hub.append_line('install', 'normal output')
    assert hub.tail('install')[-1] == 'normal output'


@pytest.mark.parametrize('references', [[], ['reference.png'], '', None])
def test_shared_sample_contract_allows_only_empty_t2i_references(references):
    sample = {**DEFAULT_SAMPLE, 'controlImages': references}
    config = {'sample_enabled': True, 'preview_samples': [json.dumps(sample)]}
    if references == []:
        assert sample_config(config)['samples'] == [DEFAULT_SAMPLE]
    else:
        with pytest.raises(ValueError, match='controlImages'):
            sample_config(config)
