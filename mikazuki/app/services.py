import json
import os
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / ".runtime"
SERVICES_FILE = RUNTIME_DIR / "services.json"


def public_base_url() -> str:
    host = os.environ.get("MIKAZUKI_HOST", "127.0.0.1") or "127.0.0.1"
    port = os.environ.get("MIKAZUKI_PORT", "28000") or "28000"
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    return f"http://{display_host}:{port}"


def internal_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    return f"http://{display_host}:{port}"


def read_services() -> dict[str, Any]:
    try:
        return json.loads(SERVICES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_services(services: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "services": services,
    }
    tmp = SERVICES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SERVICES_FILE)


def service_record(service_id: str) -> dict[str, Any]:
    payload = read_services()
    services = payload.get("services") or {}
    record = services.get(service_id) or {}
    return record if isinstance(record, dict) else {}


def service_internal_url(service_id: str, fallback: str) -> str:
    return str(service_record(service_id).get("internal_url") or fallback).rstrip("/")


def service_public_url(service_id: str, fallback: str) -> str:
    return str(service_record(service_id).get("public_url") or fallback).rstrip("/")
