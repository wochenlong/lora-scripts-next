"""Generic plugin-host primitives shared by optional plugins."""

from .security import AgentRouteAuthority, AgentRouteAuthorityConfig, AgentRouteAuthorityContext

__all__ = [
    "AgentRouteAuthority",
    "AgentRouteAuthorityConfig",
    "AgentRouteAuthorityContext",
]
