import httpx
import pytest

from next_trainer_mcp.backend import BackendClient


def make_backend(handler) -> BackendClient:
    backend = BackendClient("http://testserver")
    backend._client = httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )
    return backend


def test_request_unwraps_data_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"status": "success", "message": None, "data": {"version": "2.9.2"}})

    backend = make_backend(handler)
    assert backend.request("GET", "/api/version") == {"version": "2.9.2"}


def test_request_fail_status_raises_with_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "fail", "message": "缺少 config 对象", "data": None})

    backend = make_backend(handler)
    with pytest.raises(Exception, match="缺少 config 对象"):
        backend.request("POST", "/api/config/validate-import", json_body={})


def test_request_http_error_raises_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Unknown task_id"})

    backend = make_backend(handler)
    with pytest.raises(Exception, match="Unknown task_id"):
        backend.request("GET", "/api/tasks/nope/metrics")


def test_request_connect_error_hints_start_app():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    backend = make_backend(handler)
    with pytest.raises(Exception, match="请先启动 Next Trainer"):
        backend.request("GET", "/api/version")


def test_request_sends_json_body_and_query_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"status": "success", "data": {"ok": True}})

    backend = make_backend(handler)
    backend.request(
        "POST",
        "/api/run",
        params={"a": 1, "skip": None},
        json_body={"k": "v"},
    )
    assert seen["body"] == '{"k": "v"}'
    assert seen["query"] == "a=1"


def test_response_without_data_key_returned_as_is():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "pending"})

    backend = make_backend(handler)
    assert backend.request("GET", "/api/graphic_cards") == {"status": "pending"}
