"""Private real HTTP acceptance. No provider replacements and no credentials."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import requests

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--port', type=int, default=28766)
args = parser.parse_args()
ROOT = args.root.resolve()
DATA = ROOT / 'http-images'
BASE = f'http://127.0.0.1:{args.port}/api'
if DATA.exists():
    parser.error('HTTP acceptance output must be new')
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_caption_rebuild_inputs import validate_inputs
validate_inputs(ROOT / 'inputs')
REPORT = {'kind': 'fresh-rebuild-real-http', 'checks': {}, 'passed': False, 'remote': 'not configured'}


def call(method, path, payload=None, code=200):
    response = requests.request(method, BASE + path, json=payload, timeout=120)
    assert response.status_code == code, (path, response.status_code, response.text[:300])
    body = response.json()
    return body.get('data', body)


def check(name, value):
    assert value, name
    REPORT['checks'][name] = True
    print(json.dumps({'check': name, 'passed': True}), flush=True)


def prepare(name, files=('chelsea.png',)):
    root = DATA / name
    root.mkdir(parents=True)
    for file in files:
        shutil.copy2(ROOT / 'inputs/samples' / file, root / file)
    return root


def request(root, **overrides):
    return {'path': str(root), 'mode': 'natural', 'allow_local_fallback': True,
            'conflict_action': 'copy', 'use_cache': False, **overrides}


def wait(job):
    end = time.monotonic() + 180
    while time.monotonic() < end:
        state = call('GET', '/tagger/jobs/' + job)
        if state['phase'] in ('done', 'error', 'cancelled'):
            return state
        time.sleep(.1)
    raise AssertionError('real job exceeded time budget')


def active(job):
    end = time.monotonic() + 60
    while time.monotonic() < end:
        state = call('GET', '/tagger/jobs/' + job)
        if state['phase'] == 'captioning':
            return state
        assert state['phase'] not in ('done', 'error', 'cancelled'), 'job terminated before controlled action'
        time.sleep(.03)
    raise AssertionError('job did not reach captioning')


def start(root, **overrides):
    return call('POST', '/tagger/jobs', request(root, **overrides))['job_id']


try:
    started = call('POST', '/llm/local-vision/start')
    check('explicit_local_runtime_started', call('GET', '/llm/local-vision/status')['state'] == 'running')
    root = prepare('natural', ('chelsea.png', 'coffee.png', 'rocket.jpg'))
    preview = call('POST', '/tagger/jobs/preview', {**request(root), 'image_path': str(root / 'chelsea.png')})
    check('natural_preview_no_write', bool(preview['caption']) and not list(root.glob('*.txt')))
    job = start(root)
    state = wait(job)
    check('natural_three_written', state['succeeded'] == 3 and state['failed'] == 0)
    originals = {p.name: p.read_bytes() for p in root.glob('*.txt')}
    REPORT['caption_sha256'] = {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()}
    check('task_archives', len(list((ROOT / 'http-state/user_data/tasks/dataset-tagger').rglob('task.json'))) >= 1)
    skip = wait(start(root, conflict_action='ignore'))
    check('default_skip_three', skip['skipped'] == 3 and skip['succeeded'] == 0)
    items = call('POST', '/dataset-editor/scan', {'path': str(root)})['items']
    item = next(x for x in items if x['relative_path'] == 'chelsea.png')
    check('editor_natural_not_tags', all(x['caption_format'] == 'natural' and x['tags'] == [] for x in items))
    call('POST', '/dataset-editor/batch', {'root': str(root), 'images': ['chelsea.png'], 'clean': True}, code=409)
    edited = call('POST', '/dataset-editor/caption', {'root': str(root), 'image': 'chelsea.png', 'caption': '猫', 'expected_sha256': item['caption_sha256']})
    check('single_word_remains_natural', edited['caption_format'] == 'natural' and (root / 'chelsea.txt').read_bytes() == '猫'.encode())
    call('POST', '/dataset-editor/undo', {'root': str(root)})
    check('undo_preserves_bytes', (root / 'chelsea.txt').read_bytes() == originals['chelsea.txt'])
    call('POST', '/dataset-editor/redo', {'root': str(root)})
    check('redo_preserves_single_word', (root / 'chelsea.txt').read_bytes() == '猫'.encode())
    call('POST', '/dataset-editor/undo', {'root': str(root)})
    coffee = next(x for x in items if x['relative_path'] == 'coffee.png')
    (root / 'coffee.txt').write_bytes(b'external-user-edit')
    call('POST', '/dataset-editor/caption', {'root': str(root), 'image': 'coffee.png', 'caption': 'replacement', 'expected_sha256': coffee['caption_sha256']}, code=409)
    check('editor_stale_hash_never_overwrites', (root / 'coffee.txt').read_bytes() == b'external-user-edit')
    (root / 'coffee.txt').write_bytes(originals['coffee.txt'])

    cancelled = prepare('cancel')
    job = start(cancelled)
    active(job)
    call('POST', '/tagger/jobs/' + job + '/cancel')
    state = wait(job)
    check('real_cancel_zero_writes', state['phase'] == 'cancelled' and state['succeeded'] == 0 and not list(cancelled.glob('*.txt')))

    partial = prepare('partial')
    (partial / 'bad.png').write_bytes(b'controlled-corrupt-image')
    job = start(partial)
    state = wait(job)
    check('partial_real_failure', state['succeeded'] == 1 and state['failed'] == 1)
    preserved = (partial / 'chelsea.txt').read_bytes()
    shutil.copy2(ROOT / 'inputs/samples/coffee.png', partial / 'bad.png')
    retried = call('POST', '/tagger/jobs/retry-failed')['job_id']
    state = wait(retried)
    check('retry_only_failed', state['total'] == 1 and state['succeeded'] == 1 and (partial / 'chelsea.txt').read_bytes() == preserved)
    check('retry_parent', state['parent_job_id'] == job)

    conflict = prepare('conflict', ('coffee.png',))
    (conflict / 'coffee.txt').write_bytes(b'before')
    job = start(conflict)
    active(job)
    (conflict / 'coffee.txt').write_bytes(b'external-change-during-inference')
    state = wait(job)
    check('inference_write_conflict', state['failed'] == 1 and (conflict / 'coffee.txt').read_bytes() == b'external-change-during-inference')

    rollback = prepare('rollback')
    job = start(rollback)
    state = wait(job)
    check('rollback_input_generated', state['succeeded'] == 1)
    restored = call('POST', '/tagger/jobs/' + job + '/rollback')
    check('rollback_creation_only', restored['restored'] == 1 and not (rollback / 'chelsea.txt').exists() and (rollback / 'chelsea.png').exists())
    call('DELETE', '/tagger/jobs/' + job)
    check('clear_history_keeps_images', (rollback / 'chelsea.png').exists())

    document = call('GET', '/llm/prompt-presets')
    preset = {'id': 'fresh-caption', 'kind': 'caption_prompt', 'name': '隔离验收', 'template': '请用{{language}}描述可见事实。', 'system_prompt': '不要臆测。', 'output_format': 'plain_text', 'language': 'zh-CN', 'max_length': 240, 'model_capabilities': ['vision', 'caption']}
    saved = call('PUT', '/llm/prompt-presets', {'revision': document['revision'], 'presets': [preset], 'settings': {'default_caption_preset_id': 'fresh-caption'}})
    check('user_data_presets', saved['settings']['default_caption_preset_id'] == 'fresh-caption' and (ROOT / 'http-state/user_data/presets/fresh-caption.json').exists())
    call('PUT', '/llm/prompt-presets', document, code=409)
    check('stale_preset_revision_rejected', call('GET', '/llm/prompt-presets')['revision'] == saved['revision'])
    call('POST', '/llm/local-vision/stop')
    check('model_stopped', call('GET', '/llm/local-vision/status')['state'] != 'running')
    check('atomic_no_orphan_parts', not list(DATA.rglob('*.part')) and not list(DATA.rglob('*.tmp')))
    REPORT['passed'] = True
finally:
    (ROOT / 'http-real-report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
