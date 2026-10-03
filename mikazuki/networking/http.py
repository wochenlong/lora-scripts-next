"""HTTP transport only: callers retain their size/signature/cache transactions."""
import base64
import logging
from urllib.parse import urlsplit, unquote
import urllib.request
import urllib.error
import socket

from .policy import NetworkPolicy, resolve_policy, redact
from .events import emit

logger = logging.getLogger(__name__)


class PolicyProxyHandler(urllib.request.ProxyHandler):
    def __init__(self, policy: NetworkPolicy):
        self.policy = policy
        # Install handlers even for direct mode, so redirect policy is explicit.
        super().__init__({"http": "policy", "https": "policy"})

    def proxy_open(self, req, proxy, type):
        proxy = self.policy.proxy_for(req.full_url)
        if not proxy:
            return None
        parsed = urlsplit(proxy)
        if parsed.username is not None:
            credentials = f"{unquote(parsed.username)}:{unquote(parsed.password or '')}"
            req.add_unredirected_header("Proxy-Authorization", "Basic " + base64.b64encode(credentials.encode()).decode())
        host = parsed.netloc.rsplit("@", 1)[-1]
        original_type = req.type
        req.set_proxy(host, parsed.scheme)
        if original_type == parsed.scheme or original_type == "https":
            return None
        return self.parent.open(req, timeout=req.timeout)


class HttpDownloadAdapter:
    def __init__(self, policy: NetworkPolicy | None = None):
        self.policy = policy or resolve_policy()
        self.opener = urllib.request.build_opener(PolicyProxyHandler(self.policy))

    def open(self, request, *, timeout=30):
        url = request.full_url if isinstance(request, urllib.request.Request) else request
        logger.info("[network] %s target=%s", self.policy.diagnostic(url), redact(url))
        emit(**self.policy.diagnostic(url), target=redact(url))
        try:
            return self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            kind = {407: "proxy_auth_required", 404: "source_not_found", 403: "source_forbidden"}.get(exc.code, "http_error")
            logger.warning("[network] error_type=%s http_status=%s", kind, exc.code)
            emit(error_type=kind, http_status=exc.code)
            raise
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ConnectionRefusedError):
                kind = "proxy_connection_refused" if self.policy.proxy_for(url) else "source_connection_refused"
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                kind = "transport_timeout"
            else:
                kind = "transport_error"
            emit(error_type=kind)
            logger.warning("[network] error_type=%s", kind)
            raise


def open_url(request, *, timeout=30):
    return HttpDownloadAdapter().open(request, timeout=timeout)
