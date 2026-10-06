# Phase 0 统一 LLM focused verification

- Branch: feat/NL-Captioning
- Source commit before implementation: fc193789c46f6724bfcc92e203644ba3f77db995
- Runtime: Windows, Python 3.14 host
- Secret scan: no API key or authorization value persisted

## Commands

- python -m pytest tests/test_llm_contracts.py tests/test_llm_client.py tests/test_llm_unified_store.py tests/test_caption_api.py -q
- python -c "from mikazuki.app.api import router; ..."

## Result

- Focused shared LLM, configuration migration, masking, revision, remote-first/local-fallback and route registration: PASS.
- Latest focused group: 11 passed.
- Existing TestClient suites remain environment-bound on the host because Python 3.14 cannot import the project-pinned httpcore 0.17.x; they require the supported isolated runtime for final evidence.

## Scope boundary

This evidence proves the contract and route seams only. It does not prove complete real API connectivity, local model startup, or final acceptance.
