# Phase 1 视觉任务 focused verification

- Branch: feat/NL-Captioning
- Secret scan: no API key, local image, raw response, or model binary persisted

## Commands

- python -m pytest tests/test_caption_contract.py tests/test_caption_job.py tests/test_vision_service.py tests/test_dataset_caption_format.py -q
- python -m pytest supported tag translation and tagger subset, excluding the Python 3.14/httpcore-bound TestClient module

## Result

- Caption contract, strict JSON, prompt rendering, data URL, atomic write, before-hash conflict guard, job manager, cancellation state, and caption format projection: PASS.
- Combined/tag job model preparation and real local/remote resources: NOT YET VERIFIED.
