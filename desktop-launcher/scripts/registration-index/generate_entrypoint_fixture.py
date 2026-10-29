"""固定uv离线生成受控入口启动器；不安装或执行实际GUI依赖。"""
import base64, configparser, csv, hashlib, io, json, os, subprocess, zipfile
from pathlib import Path

WORK = Path(__file__).parent
INDEX = WORK / 'gui-cp310-installed-files-v1.json'
UV = Path(r'E:\OpenSourceTeamWork\workspace\tools\launcher-foundation-20261028\正式 安装\tools\uv.exe')
CONTROL = Path(r'E:\NTRegCtrl\a5-20261029-ctrl1\g0000000000000000')
raw = INDEX.read_bytes()
if hashlib.sha256(raw).hexdigest() != '3e0c861b6b4c7e2b9a1a5615193cca976a194e72100aaa1afc54a39065d8bea8':
    raise ValueError('trusted index input identity differs')
index = json.loads(raw)
if hashlib.sha256(UV.read_bytes()).hexdigest() != index['uv_exe_sha256']:
    raise ValueError('fixed uv differs')
launchers = {}
sections = {'console_scripts': {}, 'gui_scripts': {}}
for package in index['packages']:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(package['entry_points'] or '')
    for section in sections:
        for name, target in parser.items(section) if parser.has_section(section) else ():
            if not name or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for char in name):
                raise ValueError('invalid generated entrypoint name')
            if name.lower() in launchers:
                raise ValueError('generated entrypoint conflict')
            sections[section][name] = target
            launchers[name.lower()] = {'package': package['name'], 'path': 'Scripts/' + name + '.exe', 'target': target}
    if package['name'] == 'pip' and 'pip' in sections['console_scripts']:
        sections['console_scripts']['pip3.10'] = sections['console_scripts']['pip']
        launchers['pip3.10'] = {'package': 'pip', 'path': 'Scripts/pip3.10.exe', 'target': sections['console_scripts']['pip']}
entrypoints = ''.join('[' + section + ']\n' + ''.join(name + ' = ' + target + '\n' for name, target in sorted(items.items())) + '\n' for section, items in sections.items())
dist = 'nt_registration_control-0.0.1.dist-info'
files = {
    'nt_registration_control.py': b'"""Controlled generation fixture; never imported."""\n',
    dist + '/METADATA': b'Metadata-Version: 2.1\nName: nt-registration-control\nVersion: 0.0.1\nLicense: MIT\n',
    dist + '/WHEEL': b'Wheel-Version: 1.0\nGenerator: next-trainer-trusted-index\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
    dist + '/entry_points.txt': entrypoints.encode(),
}
rows = [[name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data))] for name, data in files.items()]
rows.append([dist + '/RECORD', '', ''])
stream = io.StringIO(newline=''); csv.writer(stream, lineterminator='\n').writerows(rows)
files[dist + '/RECORD'] = stream.getvalue().encode()
wheel = WORK / 'nt_registration_control-0.0.1-py3-none-any.whl'
with zipfile.ZipFile(wheel, 'x', compression=zipfile.ZIP_STORED) as archive:
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('UV_', 'PIP_', 'PYTHON'))}
env.update(UV_PYTHON_DOWNLOADS='never', UV_NO_CONFIG='1', UV_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
           UV_CACHE_DIR=str(WORK/'entrypoint-cache'), HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', ALL_PROXY='http://127.0.0.1:9', NO_PROXY='')
result = subprocess.run([str(UV), '--no-config', '--offline', 'pip', 'install', '--no-deps', '--no-index', '--python', str(CONTROL/'Scripts/python.exe'), str(wheel)],
                        env=env, capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(WORK/'entrypoint-uv.stdout.log').write_bytes(result.stdout); (WORK/'entrypoint-uv.stderr.log').write_bytes(result.stderr)
if result.returncode:
    raise RuntimeError('controlled entrypoint generation failed')

print("Fixed synthetic wheel and entrypoint fixture generated; next run extract_entrypoint_controls.py")
