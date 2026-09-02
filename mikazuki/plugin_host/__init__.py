"""Generic plugin-host primitives shared by optional plugins."""

from .broker import CapabilityBrokerError, PluginBridgeMethod, PluginCapabilityBroker, PluginCapabilityContext
from .confirmation import ConfirmationError, ConfirmationTicket, ConfirmationTicketStore
from .runtime import ExecutablePluginRuntime, PluginRuntimeController, RuntimeSnapshot
from .security import AgentRouteAuthority, AgentRouteAuthorityConfig, AgentRouteAuthorityContext

__all__ = [
    "AgentRouteAuthority",
    "AgentRouteAuthorityConfig",
    "AgentRouteAuthorityContext",
    "CapabilityBrokerError",
    "ConfirmationError",
    "ConfirmationTicket",
    "ConfirmationTicketStore",
    "ExecutablePluginRuntime",
    "PluginCapabilityBroker",
    "PluginCapabilityContext",
    "PluginBridgeMethod",
    "PluginRuntimeController",
    "RuntimeSnapshot",
]
