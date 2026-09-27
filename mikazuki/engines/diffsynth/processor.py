"""Prepare the pinned Qwen processor in the project's shared tokenizer cache."""
import json
import os
from pathlib import Path
import uuid

REPO = 'Qwen/Qwen-Image-2.1'
REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
FILES = ('added_tokens.json', 'chat_template.jinja', 'merges.txt',
         'preprocessor_config.json', 'special_tokens_map.json', 'tokenizer.json',
         'tokenizer_config.json', 'video_preprocessor_config.json', 'vocab.json')


def processor_directory(root):
    return Path(root).resolve() / 'tokenizer-cache' / 'Qwen_Qwen-Image-2.1' / 'processor'


def valid_file(path):
    try:
        text = path.read_text(encoding='utf-8')
        if not text.strip():
            return False
        if path.name.endswith('.json'):
            value = json.loads(text)
            return isinstance(value, dict) and bool(value)
        return not text.lstrip().lower().startswith(('<html', '<!doctype'))
    except (OSError, ValueError, UnicodeError):
        return False


def ensure_processor(root):
    import requests

    directory = processor_directory(root)
    missing = [name for name in FILES if not valid_file(directory / name)]
    if not missing:
        print(f'[processor] Local cache ready: {directory}', flush=True)
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    endpoints = list(dict.fromkeys([os.environ.get('HF_ENDPOINT') or 'https://hf-mirror.com',
                                    'https://huggingface.co']))
    with requests.Session() as session:
        for name in missing:
            print(f'[processor] Downloading {name}', flush=True)
            errors = []
            for endpoint in endpoints:
                temporary = directory / (uuid.uuid4().hex + '-' + name)
                try:
                    response = session.get(f'{endpoint.rstrip("/")}/{REPO}/resolve/{REVISION}/processor/{name}', timeout=(15, 90))
                    response.raise_for_status()
                    temporary.write_bytes(response.content)
                    if not valid_file(temporary):
                        raise ValueError('下载的 Processor 文件为空或格式无效')
                    temporary.replace(directory / name)
                    break
                except (requests.RequestException, OSError, ValueError) as exc:
                    errors.append(f'{endpoint}: {exc}')
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                raise RuntimeError(f'Processor 下载失败：{name}。请检查下载源或代理后重新开始训练。' + '; '.join(errors))
    print(f'[processor] Ready: {directory}', flush=True)
    return directory
