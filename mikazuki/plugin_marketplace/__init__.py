"""Generic optional-plugin marketplace host.

This package deliberately contains no Agent or Pi runtime imports.  The core
host validates opaque plugin packages and launches only manifest-declared
executables through the runtime layer added by later Stage 1 phases.
"""

from .manager import MarketplaceManager
from .models import MarketplaceEntry, PluginManifest, PluginStatus

__all__ = ["MarketplaceEntry", "MarketplaceManager", "PluginManifest", "PluginStatus"]
