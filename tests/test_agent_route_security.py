from __future__ import annotations

import asyncio
import unittest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from mikazuki.plugin_host.security import AgentRouteAuthority, AgentRouteAuthorityConfig


RUN_TOKEN = "test-run-token-that-is-long-enough"
APP_HOST = "127.0.0.1:28000"
APP_ORIGIN = f"http://{APP_HOST}"


def make_request(
    *,
    method: str = "POST",
    client_host: str = "127.0.0.1",
    host: str = APP_HOST,
    origin: str | None = APP_ORIGIN,
    sec_fetch_site: str | None = "same-origin",
    content_type: str | None = "application/json",
    run_token: str | None = RUN_TOKEN,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", host.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if sec_fetch_site is not None:
        headers.append((b"sec-fetch-site", sec_fetch_site.encode("ascii")))
    if content_type is not None:
        headers.append((b"content-type", content_type.encode("ascii")))
    if run_token is not None:
        headers.append((b"x-nexttrainer-run-token", run_token.encode("ascii")))

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "scheme": "http",
            "method": method,
            "path": "/api/agent/sessions",
            "raw_path": b"/api/agent/sessions",
            "query_string": b"",
            "headers": headers,
            "client": (client_host, 51000),
            "server": ("127.0.0.1", 28000),
        }
    )


class LoopbackClientScope:
    """Make Starlette TestClient model an actual loopback peer."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = ("127.0.0.1", 51000)
        await self.app(scope, receive, send)


class AgentRouteAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        config = AgentRouteAuthorityConfig(
            allowed_hosts={APP_HOST},
            allowed_origins={APP_ORIGIN},
            run_token=RUN_TOKEN,
        )
        self.mutation_authority = AgentRouteAuthority.for_json_mutation(config)
        self.stream_authority = AgentRouteAuthority.for_stream(config)
        self.bootstrap_authority = AgentRouteAuthority.for_bootstrap(config)

    def authorize(self, request: Request, *, stream: bool = False):
        authority = self.stream_authority if stream else self.mutation_authority
        return asyncio.run(authority(request))

    def assert_rejected(self, request: Request, reason: str, *, stream: bool = False) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.authorize(request, stream=stream)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, {"code": "AGENT_ROUTE_FORBIDDEN", "reason": reason})

    def test_accepts_exact_same_origin_json_mutation_from_loopback(self):
        context = self.authorize(make_request())

        self.assertEqual(context.host, APP_HOST)
        self.assertEqual(context.origin, APP_ORIGIN)
        self.assertEqual(context.client_host, "127.0.0.1")

    def test_rejects_cross_site_request(self):
        self.assert_rejected(make_request(sec_fetch_site="cross-site"), "cross-site")

    def test_rejects_bad_host_even_when_origin_and_token_are_valid(self):
        self.assert_rejected(make_request(host="localhost:28000"), "host")

    def test_rejects_bad_origin_even_when_host_and_token_are_valid(self):
        self.assert_rejected(make_request(origin="http://127.0.0.1:28001"), "origin")

    def test_rejects_originless_mutation(self):
        self.assert_rejected(make_request(origin=None), "origin")

    def test_rejects_missing_run_token(self):
        self.assert_rejected(make_request(run_token=None), "run-token")

    def test_rejects_wrong_run_token(self):
        self.assert_rejected(make_request(run_token="wrong-token"), "run-token")

    def test_rejects_lan_client(self):
        self.assert_rejected(make_request(client_host="192.168.1.50"), "loopback")

    def test_rejects_non_json_mutation(self):
        self.assert_rejected(make_request(content_type="text/plain"), "content-type")

    def test_accepts_json_content_type_parameters(self):
        context = self.authorize(make_request(content_type="application/json; charset=utf-8"))

        self.assertEqual(context.client_host, "127.0.0.1")

    def test_stream_requires_origin_and_token_but_not_json_content_type(self):
        request = make_request(method="GET", content_type=None)
        context = self.authorize(request, stream=True)

        self.assertEqual(context.origin, APP_ORIGIN)

    def test_stream_rejects_missing_origin(self):
        self.assert_rejected(make_request(method="GET", origin=None, content_type=None), "origin", stream=True)

    def test_bootstrap_requires_same_origin_json_but_not_an_existing_run_token(self):
        context = asyncio.run(self.bootstrap_authority(make_request(run_token=None)))
        self.assertEqual(context.origin, APP_ORIGIN)
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.bootstrap_authority(make_request(run_token=None, origin="http://127.0.0.1:9")))
        self.assertEqual(raised.exception.detail["reason"], "origin")

    def test_accepts_ipv6_loopback_client(self):
        context = self.authorize(make_request(client_host="::1"))

        self.assertEqual(context.client_host, "::1")

    def test_is_usable_as_a_fastapi_dependency(self):
        app = FastAPI()

        @app.post("/api/agent/probe")
        async def probe(context=Depends(self.mutation_authority)):
            return context.dict()

        client = TestClient(LoopbackClientScope(app), base_url=APP_ORIGIN)
        response = client.post(
            "/api/agent/probe",
            json={"probe": True},
            headers={
                "Origin": APP_ORIGIN,
                "Sec-Fetch-Site": "same-origin",
                "X-NextTrainer-Run-Token": RUN_TOKEN,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["client_host"], "127.0.0.1")

    def test_configuration_rejects_non_exact_host_and_origin_values(self):
        invalid = (
            {"allowed_hosts": {"http://127.0.0.1:28000"}, "allowed_origins": {APP_ORIGIN}},
            {"allowed_hosts": {APP_HOST}, "allowed_origins": {f"{APP_ORIGIN}/path"}},
            {"allowed_hosts": {APP_HOST}, "allowed_origins": {"*"}},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                AgentRouteAuthorityConfig(run_token=RUN_TOKEN, **overrides)


if __name__ == "__main__":
    unittest.main()
