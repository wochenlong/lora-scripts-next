"""Compare legacy and caption Tag jobs using real ONNX and public samples."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--samples', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--tag-models', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--rebuild-inputs', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.exists():
        raise RuntimeError('Tag verification requires a new root')
    os.environ['MIKAZUKI_TAG_TRANSLATION_ROOT'] = str(root / 'state')
    os.environ['MIKAZUKI_USER_DATA_ROOT'] = str(root / 'user_data')
    os.environ['MIKAZUKI_TAGGER_MODELS_DIR'] = str(args.tag_models.resolve())
    from mikazuki.app.models import TaggerInterrogateRequest
    from mikazuki.tagger import jobs
    from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
    from mikazuki.tagger.caption_store import CaptionJobStore
    from mikazuki.tagger.progress import tagger_progress
    from mikazuki.tagger.task_bridge import CaptionTaskBridge

    if args.rebuild_inputs:
        from download_caption_rebuild_inputs import validate_inputs
        fresh, _ = validate_inputs(args.rebuild_inputs)
        if args.samples.resolve() != fresh / 'samples' or args.tag_models.resolve() != fresh / 'tag-models':
            raise ValueError('rebuild Tag must use its fresh downloaded inputs')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    old, new = root / 'legacy', root / 'new'
    for folder in (old, new):
        folder.mkdir(parents=True)
        for sample in manifest['samples']:
            source = args.samples / sample['filename']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == sample['sha256']
            shutil.copy2(source, folder / sample['filename'])

    class NoLLM:
        async def complete_vision(self, *args, **kwargs):
            raise AssertionError('Tag must not call an LLM')

    report = {'source_commit': args.commit, 'phase_4': False, 'provider': 'real-ONNX-CPU',
              'model': 'wd14-convnextv2-v2', 'samples': [], 'fresh_rebuild_inputs': bool(args.rebuild_inputs)}
    started = time.perf_counter()
    try:
        tagger_progress.reset_idle()
        jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(old), batch_output_action_on_conflict='copy'))
        assert tagger_progress.get()['phase'] == 'done'
        journal = CaptionJobStore(root / 'state' / 'translations.sqlite3')
        manager = CaptionJobManager(NoLLM(), job_store=journal, task_bridge=CaptionTaskBridge(root / 'user_data'))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from mikazuki.tagger import caption_api
        caption_api.caption_job_manager = manager
        app = FastAPI()
        app.include_router(caption_api.router, prefix='/api')
        with TestClient(app) as client:
            previews = {}
            for sample in manifest['samples']:
                preview = client.post('/api/tagger/jobs/preview', json={'path': str(new), 'image_path': str(new / sample['filename']),
                    'mode': 'tag', 'model_id': report['model'], 'runtime': 'local'})
                assert preview.status_code == 200
                previews[sample['filename']] = preview.json()['data']['caption']
                assert not (new / Path(sample['filename']).with_suffix('.txt')).exists()
        manager.start({'path': str(new), 'mode': 'tag', 'conflict_action': 'copy',
                       'interrogator_model': report['model']})
        manager._thread.join(300)
        if manager._thread.is_alive():
            manager.cancel()
            manager._thread.join(15)
            raise RuntimeError('Tag verification time budget exceeded')
        assert manager.status()['succeeded'] == 3 and manager.status()['failed'] == 0
        for sample in manifest['samples']:
            filename = Path(sample['filename']).with_suffix('.txt')
            left, right = old / filename, new / filename
            assert left.read_bytes() == right.read_bytes()
            assert right.read_text(encoding='utf-8').strip() == previews[sample['filename']]
            detail = journal.find_format_detail(right, caption_sha256(right))
            assert detail['format'] == 'tag' and detail['tags']
            report['samples'].append({'id': sample['id'], 'bytes_equal': True,
                                      'preview_equal': True,
                                      'tag_count': len(detail['tags']), 'after_hash': caption_sha256(right)})
        archive = manager.task_bridge.locations[manager.status()['job_id']]
        assert (archive / 'config.json').is_file() and (archive / 'task.json').is_file()
        report['task_archive_present'] = True
        report['preview_no_write'] = True
        manager.start({'path': str(new), 'mode': 'tag', 'conflict_action': 'ignore', 'interrogator_model': report['model']})
        manager._thread.join(60)
        assert manager.status()['skipped'] == 3 and manager.status()['succeeded'] == 0
        report['default_skip'] = True
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error_type'] = type(error).__name__
        report['error_code'] = getattr(error, 'code', 'real_tag_acceptance_failed')
    report['seconds'] = round(time.perf_counter() - started, 3)
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    return report['passed']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
