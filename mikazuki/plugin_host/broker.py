from __future__ import annotations

import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from .runtime import PluginRuntimeRequestError


_METHOD = re.compile(r"^[a-z][a-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)+$")


class CapabilityManager(Protocol):
    def capability_context(self, plugin_id: str): ...

    async def capability_request(self, plugin_id: str, request_id: str, method: str, params: dict[str, Any]): ...

    async def capability_stream(self, plugin_id: str, request_id: str, method: str, params: dict[str, Any]): ...


@dataclass(frozen=True)
class PluginBridgeMethod:
    permission: str
    params_schema: dict[str, Any]


@dataclass(frozen=True)
class PluginCapabilityContext:
    plugin_id: str
    version: str
    manifest_permissions: frozenset[str]
    granted_permissions: frozenset[str]
    requests: dict[str, PluginBridgeMethod]
    streams: dict[str, PluginBridgeMethod]


class CapabilityBrokerError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code
        self.retryable = retryable


RequestHandler = Callable[[PluginCapabilityContext, dict[str, Any]], Any | Awaitable[Any]]
StreamHandler = Callable[
    [PluginCapabilityContext, dict[str, Any]],
    AsyncIterator[Any] | Awaitable[AsyncIterator[Any]],
]


@dataclass(frozen=True)
class _Registration:
    permissions: frozenset[str]
    handler: RequestHandler | StreamHandler
    dynamic_authorization: bool = False
    host_owned: bool = False


class PluginCapabilityBroker:
    """Generic typed dispatch; Agent/Pi method names live in plugin adapters, not core."""

    def __init__(self) -> None:
        self._requests: dict[str, _Registration] = {}
        self._streams: dict[str, _Registration] = {}

    def register_request(self, method: str, permissions: Iterable[str], handler: RequestHandler) -> None:
        self._register(self._requests, method, permissions, handler)

    def register_dynamic_request(self, method: str, handler: RequestHandler) -> None:
        self._register(
            self._requests,
            method,
            (),
            handler,
            dynamic_authorization=True,
            host_owned=True,
        )

    def register_stream(self, method: str, permissions: Iterable[str], handler: StreamHandler) -> None:
        self._register(self._streams, method, permissions, handler)

    def unregister(self, method: str) -> None:
        self._requests.pop(method, None)
        self._streams.pop(method, None)

    def capabilities_for(self, manager: CapabilityManager, plugin_id: str) -> list[str]:
        try:
            context = manager.capability_context(plugin_id)
        except Exception:
            return []
        runtime_methods = {
            method
            for method, declaration in {**context.requests, **context.streams}.items()
            if self._allowed(context, frozenset({declaration.permission}))
        }
        host_methods = {
            method
            for method in set(self._requests) | set(self._streams)
            if method in context.requests or method in context.streams
            if self._registration(method).dynamic_authorization
            or self._allowed(context, self._registration(method).permissions)
        }
        return sorted(runtime_methods | host_methods)

    async def request(
        self,
        manager: CapabilityManager,
        plugin_id: str,
        request_id: str,
        method: str,
        params: dict[str, Any],
    ) -> Any:
        context = self._context(manager, plugin_id)
        registration = self._requests.get(method)
        if registration is not None and registration.host_owned and (
            method in context.requests or method in context.streams
        ):
            context = self._authorize_registration(context, registration)
            result = registration.handler(context, params)
            return await result if inspect.isawaitable(result) else result
        if registration is not None and not registration.host_owned and method in context.requests:
            context = self._authorize_registration(context, registration)
            result = registration.handler(context, params)
            return await result if inspect.isawaitable(result) else result
        declaration = context.requests.get(method)
        if declaration is not None:
            self._authorize_declaration(context, declaration, params)
            try:
                return await manager.capability_request(plugin_id, request_id, method, params)
            except PluginRuntimeRequestError as exc:
                raise CapabilityBrokerError(
                    exc.code, exc.public_message, status_code=exc.status_code, retryable=exc.retryable,
                ) from exc
        registration = self._requests.get(method)
        if registration is None:
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_UNAVAILABLE",
                "The requested plugin capability is unavailable.",
                status_code=404,
            )
        context = self._authorize_registration(context, registration)
        result = registration.handler(context, params)
        return await result if inspect.isawaitable(result) else result

    async def stream(
        self,
        manager: CapabilityManager,
        plugin_id: str,
        request_id: str,
        method: str,
        params: dict[str, Any],
    ) -> AsyncIterator[Any]:
        context = self._context(manager, plugin_id)
        registration = self._streams.get(method)
        if registration is not None and method in context.streams:
            context = self._authorize_registration(context, registration)
            result = registration.handler(context, params)
            stream = await result if inspect.isawaitable(result) else result
            if not hasattr(stream, "__aiter__"):
                raise CapabilityBrokerError(
                    "PLUGIN_STREAM_FAILED",
                    "The plugin event stream could not be opened.",
                    status_code=500,
                    retryable=True,
                )
            return stream
        declaration = context.streams.get(method)
        if declaration is not None:
            self._authorize_declaration(context, declaration, params)
            try:
                return await manager.capability_stream(plugin_id, request_id, method, params)
            except PluginRuntimeRequestError as exc:
                raise CapabilityBrokerError(
                    exc.code, exc.public_message, status_code=exc.status_code, retryable=exc.retryable,
                ) from exc
        registration = self._streams.get(method)
        if registration is None:
            raise CapabilityBrokerError(
                "PLUGIN_STREAM_UNAVAILABLE",
                "The requested plugin event stream is unavailable.",
                status_code=404,
            )
        context = self._authorize_registration(context, registration)
        result = registration.handler(context, params)
        stream = await result if inspect.isawaitable(result) else result
        if not hasattr(stream, "__aiter__"):
            raise CapabilityBrokerError(
                "PLUGIN_STREAM_FAILED",
                "The plugin event stream could not be opened.",
                status_code=500,
                retryable=True,
            )
        return stream

    def _context(
        self,
        manager: CapabilityManager,
        plugin_id: str,
    ) -> PluginCapabilityContext:
        try:
            context = manager.capability_context(plugin_id)
        except (FileNotFoundError, ValueError):
            raise CapabilityBrokerError(
                "PLUGIN_NOT_READY",
                "The plugin is not enabled and ready.",
                status_code=409,
            ) from None
        return context

    def _authorize_registration(
        self,
        context: PluginCapabilityContext,
        registration: _Registration,
    ) -> PluginCapabilityContext:
        if not registration.dynamic_authorization and not self._allowed(context, registration.permissions):
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_FORBIDDEN",
                "The plugin is not authorized for this capability.",
                status_code=403,
            )
        return context

    def _authorize_declaration(
        self,
        context: PluginCapabilityContext,
        declaration: PluginBridgeMethod,
        params: dict[str, Any],
    ) -> None:
        if not self._allowed(context, frozenset({declaration.permission})):
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_FORBIDDEN",
                "The plugin is not authorized for this capability.",
                status_code=403,
            )
        from .schema import PluginSchemaValidationError, validate_json_instance

        try:
            validate_json_instance(declaration.params_schema, params)
        except PluginSchemaValidationError:
            raise CapabilityBrokerError(
                "PLUGIN_CAPABILITY_PARAMS_INVALID",
                "The plugin capability parameters are invalid.",
                status_code=400,
            ) from None

    @staticmethod
    def _allowed(context: PluginCapabilityContext, permissions: frozenset[str]) -> bool:
        return permissions <= context.manifest_permissions and permissions <= context.granted_permissions

    def _registration(self, method: str) -> _Registration:
        return self._requests.get(method) or self._streams[method]

    @staticmethod
    def _register(
        registry: dict[str, _Registration],
        method: str,
        permissions: Iterable[str],
        handler,
        *,
        dynamic_authorization: bool = False,
        host_owned: bool = False,
    ) -> None:
        if not _METHOD.fullmatch(method) or len(method) > 128:
            raise ValueError("capability method must be a namespaced identifier")
        if method in registry:
            raise ValueError(f"capability method is already registered: {method}")
        required = frozenset(permissions)
        if (not required and not dynamic_authorization) or any(not isinstance(value, str) or not value for value in required):
            raise ValueError("capability registration requires explicit permissions")
        registry[method] = _Registration(
            permissions=required,
            handler=handler,
            dynamic_authorization=dynamic_authorization,
            host_owned=host_owned,
        )


__all__ = [
    "CapabilityBrokerError",
    "PluginCapabilityBroker",
    "PluginCapabilityContext",
    "PluginBridgeMethod",
]
