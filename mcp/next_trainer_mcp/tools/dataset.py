"""Dataset tools: scan / interrogate / tagger status / server path browse.

Note: dataset file delivery is out of scope — large files go over
ssh/rsync to a server path, then scan_dataset points the backend at it.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..backend import BackendClient


def register(mcp: FastMCP, backend: BackendClient) -> None:

    @mcp.tool()
    def scan_dataset(path: str) -> dict:
        """扫描服务器上的数据集目录（图片 + caption 清单）。

        参数：
        - path: 服务器文件系统上的数据集根目录（不是 agent 本机路径）。
          数据集投递走 ssh/rsync，本工具只让后端扫描已在服务器上的目录。
        """
        return backend.request("POST", "/api/dataset-editor/scan", json_body={"path": path})

    @mcp.tool()
    def interrogate(
        path: str,
        interrogator_model: str = "wd14-convnextv2-v2",
        threshold: float = 0.35,
    ) -> dict:
        """对单张图片或目录提交打标任务（WD14 系列）。会写入 caption 文件。

        参数：
        - path: 服务器上的图片路径或目录
        - interrogator_model: 打标模型名（默认可用 wd14-convnextv2-v2）
        - threshold: 标签阈值 0-1
        返回提交确认；进度用 get_tagger_status 轮询。已有打标任务进行中时会被后端拒绝。
        """
        return backend.request(
            "POST",
            "/api/interrogate",
            json_body={
                "path": path,
                "interrogator_model": interrogator_model,
                "threshold": threshold,
            },
        )

    @mcp.tool()
    def get_tagger_status() -> dict:
        """查询打标任务状态（是否进行中/进度）。"""
        return backend.request("GET", "/api/tagger/status")

    @mcp.tool()
    def browse_server_path(path: str = "", mode: str = "folder", name_filter: str = "") -> dict:
        """浏览服务器文件系统（网页路径选择器同款接口）。

        参数：
        - path: 目录路径，空字符串 = 根级入口列表
        - mode: "folder"（只列目录）或 "file"（列文件）
        - name_filter: 名称过滤子串
        """
        return backend.request(
            "GET",
            "/api/path_browser/list",
            params={"path": path, "mode": mode, "name_filter": name_filter},
        )

    @mcp.tool()
    def list_files(pick_type: str) -> dict:
        """按用途列出常用目录下的文件。

        参数：
        - pick_type: "model-file"（底模）/ "model-saved-file"（训练产物）/ "train-dir"（训练数据目录）等
        """
        return backend.request("GET", "/api/get_files", params={"pick_type": pick_type})
