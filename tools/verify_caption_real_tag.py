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
    args = parser.parse_args()
    root = args.root.resolve()
    if root.exists():
        raise RuntimeError('Tag verification requires a new root')
    os.environ['MIKAZUKI_TAG_TRANSLATION_ROOT'] = str(root / 'state')
    os.environ['MIKAZUKI_TAGGER_MODELS_DIR'] = str(args.tag_models.resolve())
    from mikazuki.app.models import TaggerInterrogateRequest
    from mikazuki.tagger import jobs
    from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
    from mikazuki.tagger.caption_store import CaptionJobStore
    from mikazuki.tagger.progress import tagger_progress

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
              'model': 'wd14-convnextv2-v2', 'samples': []}
    started = time.perf_counter()
    try:
        tagger_progress.reset_idle()
        jobs.run_interrogate_job(TaggerInterrogateRequest(path=str(old), batch_output_action_on_conflict='copy'))
        assert tagger_progress.get()['phase'] == 'done'
        journal = CaptionJobStore(root / 'state' / 'translations.sqlite3')
        manager = CaptionJobManager(NoLLM(), job_store=journal)
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
            detail = journal.find_format_detail(right, caption_sha256(right))
            assert detail['format'] == 'tag' and detail['tags']
            report['samples'].append({'id': sample['id'], 'bytes_equal': True,
                                      'tag_count': len(detail['tags']), 'after_hash': caption_sha256(right)})
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
