"""MCP sidecar for Next Trainer.

Exposes a whitelisted, snapshot-style tool surface over the local Next
Trainer HTTP API (default http://127.0.0.1:28000). The main app is never
modified; this package runs as a separate process with its own venv.
"""

__version__ = "0.1.0"
