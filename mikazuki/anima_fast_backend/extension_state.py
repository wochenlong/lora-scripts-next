from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from datetime import datetime, timezone


STATE_NOT_INSTALLED = "not_installed"
STATE_INSTALLING = "installing"
STATE_AUDITING = "auditing"
STATE_INSTALLED_UNVERIFIED = "installed_unverified"
STATE_READY = "ready"
STATE_BROKEN = "broken"
STATE_UPDATE_AVAILABLE = "update_available"


@dataclass(frozen=True)
class ExtensionLayout:
    root: Path

    @property
    def source(self) -> Path:
        return self.root / "source"

    @property
    def venv_python(self) -> Path:
        return self.root / ".venv" / "Scripts" / "python.exe"

    @property
    def install_state(self) -> Path:
        return self.root / "install_state.json"

    @property
    def audit_result(self) -> Path:
        return self.root / "audit_result.json"

    @property
    def train_py(self) -> Path:
        return self.source / "train.py"


@dataclass(frozen=True)
class ExtensionStatus:
    state: str
    source: str
    python: str
    reason: str = ""
    facts: dict | None = None

    def as_dict(self) -> dict:
        data = {
            "state": self.state,
            "source": self.source,
            "python": self.python,
            "reason": self.reason,
        }
        if self.facts:
            data["facts"] = self.facts
        return data


def default_layout(root: Path | None = None) -> ExtensionLayout:
    base = (root or Path.cwd()).resolve()
    return ExtensionLayout(base / "extensions" / "anima_lora")


def write_install_state(layout: ExtensionLayout, state: str, facts: dict | None = None, reason: str = "") -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "facts": facts or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        payload["reason"] = reason
    layout.install_state.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_extension_status(layout: ExtensionLayout) -> ExtensionStatus:
    if not layout.root.exists():
        return ExtensionStatus(STATE_NOT_INSTALLED, str(layout.source), str(layout.venv_python), "extension root missing")
    if not layout.source.exists():
        return ExtensionStatus(STATE_NOT_INSTALLED, str(layout.source), str(layout.venv_python), "source missing")
    if not layout.train_py.is_file():
        return ExtensionStatus(STATE_BROKEN, str(layout.source), str(layout.venv_python), "train.py missing")
    if not layout.venv_python.is_file():
        return ExtensionStatus(STATE_INSTALLED_UNVERIFIED, str(layout.source), str(layout.venv_python), "python missing")
    if not layout.install_state.is_file():
        return ExtensionStatus(STATE_INSTALLED_UNVERIFIED, str(layout.source), str(layout.venv_python), "install_state missing")

    try:
        payload = json.loads(layout.install_state.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ExtensionStatus(STATE_BROKEN, str(layout.source), str(layout.venv_python), "install_state invalid json")

    state = payload.get("state") or STATE_INSTALLED_UNVERIFIED
    facts = payload.get("facts") or {}
    if state == STATE_READY and not facts.get("audit", {}).get("ok"):
        return ExtensionStatus(
            STATE_INSTALLED_UNVERIFIED,
            str(layout.source),
            str(layout.venv_python),
            "ready state is missing passing audit facts",
            facts,
        )
    if state in {STATE_READY, STATE_INSTALLING, STATE_AUDITING, STATE_UPDATE_AVAILABLE}:
        return ExtensionStatus(state, str(layout.source), str(layout.venv_python), facts=facts)
    if state == STATE_BROKEN:
        return ExtensionStatus(STATE_BROKEN, str(layout.source), str(layout.venv_python), payload.get("reason", "marked broken"), facts)
    return ExtensionStatus(STATE_INSTALLED_UNVERIFIED, str(layout.source), str(layout.venv_python), "not verified", facts)
