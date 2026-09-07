"""Discovery tools: read-only inspection of schemas, presets, GPUs, version."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..backend import BackendClient


def register(mcp: FastMCP, backend: BackendClient) -> None:

    @mcp.tool()
    def get_schemas() -> dict:
        """获取全部训练参数 schema（每个训练页一份，含字段名/类型/默认值/说明）。

        这是构造训练配置的依据：先按 page_train_type 找到目标 schema，再填字段。
        返回 {"schemas": [...]}，内容较大，建议只取目标页那一份。
        """
        return backend.request("GET", "/api/schemas/all")

    @mcp.tool()
    def list_presets() -> dict:
        """列出训练参数预设（用户保存的常用配置模板）。"""
        return backend.request("GET", "/api/presets")

    @mcp.tool()
    def list_gpus() -> dict:
        """列出可用 GPU（型号/显存）。提交训练前必查，确认 gpu_ids 怎么填。"""
        return backend.request("GET", "/api/graphic_cards")

    @mcp.tool()
    def get_version() -> dict:
        """获取 Next Trainer 版本号。"""
        return backend.request("GET", "/api/version")

    @mcp.tool()
    def list_saved_params() -> dict:
        """列出已保存的训练参数草稿（只读，无写入接口）。"""
        return backend.request("GET", "/api/config/saved_params")
