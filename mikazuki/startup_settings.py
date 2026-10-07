"""Resolve a startup-only settings snapshot; never persist runtime fallbacks."""

from dataclasses import dataclass
import ipaddress
import socket

from mikazuki.log import log


class PortConflictError(RuntimeError):
    pass


@dataclass
class Service:
    host: str
    port: int
    enabled: bool = True
    port_conflict: str = "error"


@dataclass
class StartupSettings:
    gui: Service
    monitor: Service
    tensorboard: Service
    open_browser: bool | None = None


def read_startup_settings():
    from mikazuki.user_data import UserDataStore

    return UserDataStore().read_settings()


def port_available(host: str, port: int) -> bool:
    """Probe every resolved bind address, including IPv6 and wildcard hosts."""
    sockets = []
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        seen = set()
        for family, kind, proto, _, address in addresses:
            if (family, address) in seen:
                continue
            seen.add((family, address))
            sock = socket.socket(family, kind, proto)
            sockets.append(sock)
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(address)
        return bool(sockets)
    except OSError:
        return False
    finally:
        for sock in sockets:
            sock.close()


def _service(values, defaults):
    if not isinstance(values, dict):
        raise ValueError("Startup service settings must be an object")
    result = Service(**{**defaults, **{k: v for k, v in values.items()
                                     if k in {"host", "port", "enabled", "port_conflict"}}})
    return result


def _allocate(service, label, reserved, protected, probe):
    if not service.enabled:
        return
    end = min(service.port + (20 if service.port_conflict == "next_available" else 1), 65536)
    for port in range(service.port, end):
        # Direct requests use allocation order (GUI first); only fallbacks must
        # preserve the requested ports of services not yet allocated.
        if port != service.port and port in protected:
            continue
        if port not in reserved and probe(service.host, port):
            if port != service.port:
                log.warning(f"{label} port {service.port} unavailable or reserved; using {port} instead.")
            service.port = port
            reserved.add(port)
            return
    if service.port_conflict == "disable":
        service.enabled = False
        log.warning(f"{label} disabled: requested port {service.port} is unavailable or reserved.")
        return
    raise PortConflictError(f"{label}: no available port from {service.port} to {end - 1}")


def resolve_startup(settings, args, *, probe=None):
    """CLI overrides saved settings; changes take effect only on next launch."""
    saved = settings.get("startup", {})
    if not isinstance(saved, dict):
        raise ValueError("startup must be an object")
    gui = _service(saved.get("gui", {}), dict(host="127.0.0.1", port=28000))
    gui.enabled = True
    monitor = _service(saved.get("monitor", {}), dict(
        host="127.0.0.1", port=6008, port_conflict="next_available"))
    tensorboard = _service(saved.get("tensorboard", {}), dict(
        host="127.0.0.1", port=6007, enabled=False, port_conflict="disable"))
    if saved.get("monitor", {}).get("mode", "integrated") != "integrated":
        raise ValueError("Only integrated monitor mode is supported")
    monitor.host = "127.0.0.1"
    for service, mappings in [
        (gui, {"host": "host", "port": "port", "port_conflict": "port_conflict"}),
        (monitor, {"port": "train_monitor_port", "port_conflict": "train_monitor_port_conflict"}),
        (tensorboard, {"host": "tensorboard_host", "port": "tensorboard_port",
                       "port_conflict": "tensorboard_port_conflict"}),
    ]:
        for field, option in mappings.items():
            value = getattr(args, option, None)
            if value is not None:
                setattr(service, field, value)
    for service, option in [(monitor, "disable_train_monitor"), (tensorboard, "disable_tensorboard")]:
        value = getattr(args, option, None)
        if value is not None:
            service.enabled = not value
    if args.tensorboard_port is not None and args.disable_tensorboard is None:
        tensorboard.enabled = True
    if args.listen:
        gui.host = tensorboard.host = "0.0.0.0"
    open_browser = saved.get("gui", {}).get("open_browser")
    if getattr(args, "open_browser", None) is not None:
        open_browser = args.open_browser
    elif args.browser is not None:
        open_browser = True
    if open_browser is not None and type(open_browser) is not bool:
        raise ValueError("open_browser must be a boolean")
    for service in (gui, monitor, tensorboard):
        if type(service.port) is not int or not 1 <= service.port <= 65535:
            raise ValueError("Startup port must be an integer between 1 and 65535")
        if type(service.enabled) is not bool:
            raise ValueError("Startup enabled must be a boolean")
        if not isinstance(service.host, str) or not service.host.strip():
            raise ValueError("Startup host must be a nonempty string")
        policies = {"error", "next_available"} if service is gui else {"error", "next_available", "disable"}
        if service.port_conflict not in policies:
            raise ValueError("Invalid startup port_conflict policy")
    reserved = set()
    protected = {service.port for service in (monitor, tensorboard) if service.enabled}
    probe = probe or port_available
    _allocate(gui, "GUI", reserved, protected, probe)
    _allocate(monitor, "Train monitor", reserved, protected, probe)
    _allocate(tensorboard, "TensorBoard", reserved, protected, probe)
    for service, label in ((gui, "GUI"), (tensorboard, "TensorBoard")):
        if not service.enabled:
            continue
        try:
            loopback = ipaddress.ip_address(service.host).is_loopback
        except ValueError:
            loopback = service.host.lower() == "localhost"
        if not loopback:
            log.warning(
                f"{label} is listening on non-loopback host {service.host} without "
                "built-in authentication. Use a trusted network or an authenticated reverse proxy."
            )
    return StartupSettings(gui, monitor, tensorboard, open_browser)
