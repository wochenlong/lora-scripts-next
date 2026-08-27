from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sys
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
        if sys.platform == "win32":
            return self.root / ".venv" / "Scripts" / "python.exe"
        return self.root / ".venv" / "bin" / "python"

    @property
    def install_state(self) -> Path:
        return self.root / "install_state.json"

    @property
    def audit_result(self) -> Path:
        return self.root / "audit_result.json"

    @property
    def train_py(self) -> Path:
        return self.source / "train.py"

    @property
    def base_config(self) -> Path:
        return self.source / "configs" / "base.toml"

    @property
    def resize_script(self) -> Path:
        return self.source / "preprocess" / "resize_images.py"


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


def _reconcile_stale_install_state(
    layout: ExtensionLayout,
    state: str,
    facts: dict,
    reason: str,
) -> tuple[str, dict, str]:
    """Downgrade stuck installing/auditing when the background install task is gone or finished."""
    if state not in {STATE_INSTALLING, STATE_AUDITING}:
        return state, facts, reason

    from mikazuki.tasks import TaskStatus, tm

    task_id = facts.get("task_id")
    if not task_id:
        reason = reason or "install interrupted before task was recorded"
        write_install_state(layout, STATE_BROKEN, facts, reason)
        return STATE_BROKEN, facts, reason

    task = tm.tasks.get(task_id)
    if task is None:
        reason = "install task no longer active; use Repair to retry"
        write_install_state(layout, STATE_BROKEN, facts, reason)
        return STATE_BROKEN, facts, reason

    if task.status in {TaskStatus.FINISHED, TaskStatus.FAILED, TaskStatus.TERMINATED}:
        if task.status == TaskStatus.FINISHED and (task.returncode or 0) == 0:
            audit = facts.get("audit")
            if not audit and layout.audit_result.is_file():
                try:
                    audit = json.loads(layout.audit_result.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    audit = None
            if audit and audit.get("ok"):
                new_facts = {**facts, "audit": audit}
                write_install_state(layout, STATE_READY, new_facts, "reconciled from completed install task")
                return STATE_READY, new_facts, "reconciled from completed install task"
        err = task.metadata.get("error") or reason or "install task ended unsuccessfully"
        reason = str(err)
        write_install_state(layout, STATE_BROKEN, facts, reason)
        return STATE_BROKEN, facts, reason

    return state, facts, reason


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


def _missing_runtime_files(layout: ExtensionLayout) -> list[str]:
    required = (
        (layout.train_py, "train.py"),
        (layout.base_config, "configs/base.toml"),
        (layout.resize_script, "preprocess/resize_images.py"),
    )
    return [label for path, label in required if not path.is_file()]


def read_extension_status(layout: ExtensionLayout) -> ExtensionStatus:
    if not layout.root.exists():
        return ExtensionStatus(STATE_NOT_INSTALLED, str(layout.source), str(layout.venv_python), "extension root missing")
    if not layout.source.exists():
        return ExtensionStatus(STATE_NOT_INSTALLED, str(layout.source), str(layout.venv_python), "source missing")
    missing = _missing_runtime_files(layout)
    if missing and not layout.install_state.is_file():
        return ExtensionStatus(
            STATE_BROKEN,
            str(layout.source),
            str(layout.venv_python),
            "required runtime file(s) missing: " + ", ".join(missing),
        )
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
    if state in {STATE_INSTALLING, STATE_AUDITING}:
        reason = payload.get("reason", "")
        state, facts, reason = _reconcile_stale_install_state(layout, state, facts, reason)
        if state in {STATE_INSTALLING, STATE_AUDITING}:
            return ExtensionStatus(state, str(layout.source), str(layout.venv_python), "", facts)
        if state == STATE_BROKEN:
            return ExtensionStatus(STATE_BROKEN, str(layout.source), str(layout.venv_python), reason, facts)
    if missing:
        return ExtensionStatus(
            STATE_BROKEN,
            str(layout.source),
            str(layout.venv_python),
            "required runtime file(s) missing: " + ", ".join(missing),
            facts,
        )
    if state == STATE_READY and not facts.get("audit", {}).get("ok"):
        return ExtensionStatus(
            STATE_INSTALLED_UNVERIFIED,
            str(layout.source),
            str(layout.venv_python),
            "ready state is missing passing audit facts",
            facts,
        )
    if state in {STATE_READY, STATE_INSTALLING, STATE_AUDITING, STATE_UPDATE_AVAILABLE}:
        reason = payload.get("reason", "")
        return ExtensionStatus(
            state,
            str(layout.source),
            str(layout.venv_python),
            reason if state == STATE_BROKEN else "",
            facts,
        )
    if state == STATE_BROKEN:
        return ExtensionStatus(STATE_BROKEN, str(layout.source), str(layout.venv_python), payload.get("reason", "marked broken"), facts)
    return ExtensionStatus(STATE_INSTALLED_UNVERIFIED, str(layout.source), str(layout.venv_python), "not verified", facts)
