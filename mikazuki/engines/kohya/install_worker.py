"""Task-owned installer supervisor; cancellation kills all uv/audit children."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from mikazuki.engines.kohya.environment import install_env, audit_environment
from mikazuki.engines.kohya.extension_state import write_state, fingerprint
from mikazuki.engines.kohya.resource import environment_lock
from mikazuki.engines.kohya.settings import Runtime


def main():
    rt = Runtime(Path(sys.argv[1]))
    plan = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    facts = {'task_id': sys.argv[3]}
    with environment_lock(rt.root):
        try:
            if plan['repair']:
                for path in (rt.root / '.venv', rt.python_install_dir):
                    if path.exists():
                        shutil.rmtree(path)
            commands = plan['commands']
            for index, command in enumerate(commands):
                print('[mikazuki-progress] ' + json.dumps({"percent": int(index * 90 / len(commands)), "message": " ".join(command)}, ensure_ascii=False), flush=True)
                print('[install] ' + ' '.join(command), flush=True)
                subprocess.run(command, env=install_env(rt), check=True)
            write_state(rt, 'auditing', facts)
            audit = audit_environment(rt)
            print(json.dumps(audit, ensure_ascii=False), flush=True)
            if not audit['ok']:
                raise RuntimeError('; '.join(audit['errors']))
            write_state(rt, 'ready', {**facts, 'audit': audit, 'fingerprint': fingerprint(rt)})
            print('[mikazuki-progress] ' + json.dumps({'percent': 100, 'message': '环境检查完成'}, ensure_ascii=False), flush=True)
        except Exception as exc:
            write_state(rt, 'broken', facts, str(exc))
            raise


if __name__ == '__main__':
    main()
