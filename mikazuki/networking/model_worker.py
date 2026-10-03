"""Private SDK worker, entered with resolved proxy env before SDK import."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if __name__ == "__main__":
    from mikazuki.networking.policy import redact
    from mikazuki.model_assets import download_assets
    data = json.load(sys.stdin)
    try:
        download_assets(data["train_type"], data["items"], data["source"], Path(data["project_root"]), print)
    except Exception as exc:
        print(redact(exc), file=sys.stderr)
        sys.exit(1)
