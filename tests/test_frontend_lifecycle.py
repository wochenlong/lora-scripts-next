import os
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_api_import_does_not_require_or_build_frontend(tmp_path):
    missing = tmp_path / 'absent frontend'
    env = {**os.environ, 'MIKAZUKI_FRONTEND_DIST': str(missing)}
    subprocess.run([sys.executable, '-c',
                    'from mikazuki.engines.anima_fast import routes; '
                    'from mikazuki.app import app; assert app.routes'],
                   cwd=Path(__file__).resolve().parents[1], env=env, check=True,
                   capture_output=True, text=True)
    assert not missing.exists()


def test_lifespan_builds_before_serving_spa(tmp_path, monkeypatch):
    from mikazuki.app import application
    from mikazuki import launch_utils

    dist = tmp_path / 'frontend/dist'
    monkeypatch.setattr(launch_utils, 'base_dir_path', lambda: tmp_path)
    monkeypatch.delenv('MIKAZUKI_FRONTEND_DIST', raising=False)
    def build(path):
        assert path == dist
        path.mkdir(parents=True)
        (path / 'index.html').write_text('<main>ready</main>')
    monkeypatch.setattr(launch_utils, '_build_frontend_dist', build)
    async def startup():
        assert (dist / 'index.html').is_file()
    monkeypatch.setattr(application, 'app_startup', startup)
    app = FastAPI(lifespan=application.lifespan)
    app.mount('/', application.SPAStaticFiles(directory=dist, html=True, check_dir=False))
    assert not dist.exists()
    with TestClient(app) as client:
        assert client.get('/tasks').text == '<main>ready</main>'
        assert client.get('/assets/missing.js').status_code == 404
