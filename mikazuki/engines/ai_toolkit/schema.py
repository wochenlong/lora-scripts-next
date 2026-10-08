"""Generate capability-driven form declarations: python -m mikazuki.engines.ai_toolkit.schema."""
import json
from pathlib import Path
from .capabilities import MODELS, TRAIN_TYPES, family, schema_name


def schema_sources():
    for variant, spec in MODELS.items():
        if variant == 'klein-9b':
            continue
        types = [key for key, value in TRAIN_TYPES.items() if family(value) == family(variant)]
        declaration = {**spec, 'family': family(variant), 'train_types': types}
        yield schema_name(variant), 'SHARED_SCHEMAS.AI_TOOLKIT(' + json.dumps(declaration, ensure_ascii=False, indent=2) + ')\n'


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2] / 'schema'
    for name, source in schema_sources():
        (root / f'{name}.ts').write_text(source, encoding='utf-8')
