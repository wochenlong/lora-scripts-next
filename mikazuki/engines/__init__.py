"""Engine packs: one directory per training engine.

Each pack carries a ``manifest.py`` (see ``mikazuki.engines.manifest`` for the
frozen field contract) plus the engine's adapter/preflight/launcher suite.
``mikazuki.engines.registry`` discovers packs at runtime; adding an engine
means adding a directory here, with zero changes to ``mikazuki/app/api.py``.
"""
