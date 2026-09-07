"""Shared helpers for sidecar tool tests.

These tests need the sidecar package (its own venv). When collected from
the main repo test venv (e.g. a bare `pytest` run at the repo root), skip
the whole directory instead of failing the collection.
"""

try:
    import next_trainer_mcp  # noqa: F401
except ModuleNotFoundError:
    collect_ignore_glob = ["*"]
else:
    import asyncio

    import httpx

    from next_trainer_mcp import server as server_module
    from next_trainer_mcp.backend import BackendClient

    def run(coro):
        return asyncio.run(coro)

    def patch_backend(monkeypatch, handler):
        """Swap BackendClient for a MockTransport-backed instance."""

        def factory(base_url, timeout=10.0):
            backend = BackendClient(base_url, timeout=timeout)
            backend._client = httpx.Client(
                base_url=base_url,
                transport=httpx.MockTransport(handler),
            )
            return backend

        monkeypatch.setattr(server_module, "BackendClient", factory)

    def tool_text(result) -> str:
        """Extract the text payload from a FastMCP call_tool result.

        FastMCP returns a bare content list for structured (dict) tools, and
        a (content, structured) tuple for plain-str tools.
        """
        content = result[0] if isinstance(result, tuple) else result
        block = content[0]
        return block.text if hasattr(block, "text") else str(block)

    def tool_names(mcp) -> set[str]:
        return {t.name for t in run(mcp.list_tools())}
