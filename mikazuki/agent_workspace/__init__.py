"""Host-owned AgentWorkspace and training artifact domain services.

The package intentionally contains no Pi/LLM implementation.  It provides the
small, deterministic boundary used by a plugin adapter and by the legacy
manual-import path.
"""

from .errors import AgentDomainError
from .redaction import redact, redact_for_log
from .workspace import AgentWorkspace, WorkspaceManifest
from .artifacts import TrainingConfigArtifactService, TrainingConfigDraft

# These lazy-facing helpers are exported for Host Tool adapters.  Importing
# the API module here would eagerly import FastAPI, so keep the package's
# normal domain imports lightweight.
def ensure_workspace(*args, **kwargs):
    from .api import ensure_workspace as _ensure_workspace
    return _ensure_workspace(*args, **kwargs)

def get_workspace(*args, **kwargs):
    from .api import get_workspace as _get_workspace
    return _get_workspace(*args, **kwargs)

def get_artifact_service(*args, **kwargs):
    from .api import get_artifact_service as _get_artifact_service
    return _get_artifact_service(*args, **kwargs)

__all__ = [
    "AgentDomainError",
    "AgentWorkspace",
    "TrainingConfigArtifactService",
    "TrainingConfigDraft",
    "WorkspaceManifest",
    "redact",
    "redact_for_log",
    "ensure_workspace",
    "get_workspace",
    "get_artifact_service",
]
