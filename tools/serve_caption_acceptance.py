"""Run actual FastAPI lifespan with fresh acceptance state and built UI.

This harness redirects writable roots only; it does not replace providers,
model adapters, dictionary services, startup hooks or API behavior.
"""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--frontend-dist', type=Path, required=True)
    parser.add_argument('--port', type=int, default=28764)
    parser.add_argument('--remote', action='store_true', help='Inject the authorized profile through a hidden backend prompt')
    args = parser.parse_args()
    root = args.root.resolve()
    if root.exists():
        raise SystemExit('Acceptance state root must be new')
    if not (args.frontend_dist / 'index.html').is_file():
        raise SystemExit('Build the frontend before acceptance')
    root.mkdir(parents=True)
    for name, value in {
        'MIKAZUKI_DEV': '1',
        'MIKAZUKI_HOST': '127.0.0.1',
        'MIKAZUKI_PORT': str(args.port),
        'MIKAZUKI_FRONTEND_DIST': str(args.frontend_dist.resolve()),
        'MIKAZUKI_TAG_TRANSLATION_ROOT': str(root / 'translation'),
        'MIKAZUKI_TASK_QUEUE_FILE': str(root / 'queue.json'),
        'MIKAZUKI_TAGGER_MODELS_DIR': str(root / 'tag-models'),
        'MIKAZUKI_PLUGIN_MARKETPLACE_ROOT': str(root / 'marketplace'),
        'MIKAZUKI_MARKETPLACE_PACKAGE_ROOT': str(root / 'packages'),
        'HF_HOME': str(root / 'hf'),
    }.items():
        os.environ[name] = value

    from mikazuki.app.config import app_config
    app_config.path = root / 'app-config.json'
    from mikazuki.app.application import app
    if args.remote:
        if not sys.stdin.isatty():
            raise SystemExit('Remote acceptance requires protected terminal input')
        print('{"awaiting_runtime_secret":true}', flush=True)
        key = getpass.getpass('Runtime secret (hidden): ')
        if not key:
            raise SystemExit('Runtime key required')
        from mikazuki.llm.runtime import llm_config_store
        llm_config_store.save({'profiles': [{
            'id': 'siliconflow-qwen3.6', 'name': 'SiliconFlow Qwen3.6', 'source': 'remote',
            'endpoint': 'https://api.siliconflow.cn/v1/chat/completions',
            'model': 'Qwen/Qwen3.6-27B', 'api_key': key,
            'capabilities': ['text', 'vision'], 'languages': ['zh-CN'],
        }]})
        assert key not in llm_config_store.path.read_text(encoding='utf-8')
        del key
    from mikazuki.plugin_host.security import AgentRouteAuthorityConfig
    from mikazuki.plugin_marketplace.api import configure_marketplace_authority
    import uvicorn
    host = f'127.0.0.1:{args.port}'
    configure_marketplace_authority(AgentRouteAuthorityConfig(
        allowed_hosts=[host], allowed_origins=[f'http://{host}'], run_token=secrets.token_urlsafe(32),
    ))
    print('Actual lifespan enabled; fresh state; actual provider adapters', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, lifespan='on', log_level='warning')


if __name__ == '__main__':
    main()
