from pathlib import Path
import pytest
from mikazuki import launch_utils


def test_missing_source_frontend_builds_with_node_and_npm_cli(tmp_path, monkeypatch):
    root = tmp_path / 'trainer with spaces'
    frontend = root / 'frontend'
    frontend.mkdir(parents=True)
    (frontend / 'package-lock.json').write_text('{}')
    node = root / 'Node with spaces/node.exe'
    npm = node.parent / 'npm.cmd'
    cli = node.parent / 'node_modules/npm/bin/npm-cli.js'
    cli.parent.mkdir(parents=True)
    for p in (node, npm, cli):
        p.touch()
    monkeypatch.setattr(launch_utils, 'base_dir_path', lambda: root)
    monkeypatch.delenv('MIKAZUKI_FRONTEND_DIST', raising=False)
    monkeypatch.setattr(launch_utils.shutil, 'which', lambda name: str(node if name == 'node' else npm))
    monkeypatch.setattr(launch_utils.subprocess, 'check_output', lambda *a, **k: 'v22.23.3\n')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs['cwd'] == frontend and kwargs['check']
        if args[-2:] == ['run', 'build']:
            (frontend / 'dist').mkdir()
            (frontend / 'dist/index.html').write_text('<div id="app"></div>')
    monkeypatch.setattr(launch_utils.subprocess, 'run', run)
    launch_utils.ensure_frontend_dist()
    assert calls == [[str(node), str(cli), 'ci'], [str(node), str(cli), 'run', 'build']]


def test_packaged_frontend_needs_no_node(tmp_path, monkeypatch):
    dist = tmp_path / 'frontend/dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('ready')
    monkeypatch.setattr(launch_utils, 'base_dir_path', lambda: tmp_path)
    monkeypatch.delenv('MIKAZUKI_FRONTEND_DIST', raising=False)
    monkeypatch.setattr(launch_utils.shutil, 'which', lambda name: pytest.fail('packaged GUI must not need Node'))
    launch_utils.ensure_frontend_dist()


def test_custom_frontend_path_is_not_built(tmp_path, monkeypatch):
    monkeypatch.setattr(launch_utils, 'base_dir_path', lambda: tmp_path)
    monkeypatch.setenv('MIKAZUKI_FRONTEND_DIST', str(tmp_path / 'custom frontend'))
    monkeypatch.setattr(launch_utils.shutil, 'which', lambda name: pytest.fail('custom frontend must not be overwritten'))
    with pytest.raises(SystemExit):
        launch_utils.ensure_frontend_dist()
