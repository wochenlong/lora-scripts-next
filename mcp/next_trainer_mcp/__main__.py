"""CLI entrypoint: python -m next_trainer_mcp / next-trainer-mcp."""

from __future__ import annotations

import argparse

from .server import create_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="next-trainer-mcp",
        description="MCP sidecar for Next Trainer (agent control plane over the local HTTP API)",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:28000",
        help="Next Trainer 后端地址（默认 http://127.0.0.1:28000）",
    )
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default="streamable-http",
        help="MCP 传输方式（默认 streamable-http；stdio 用于本机单客户端）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1；不要绑 0.0.0.0，远程请走 ssh 端口转发）")
    parser.add_argument("--port", type=int, default=28001, help="监听端口（默认 28001）")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="只注册发现/监控/文档类工具，不注册训练提交/控制/数据集写入工具",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="后端 HTTP 超时秒数（默认 10）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    mcp = create_server(
        base_url=args.base_url,
        read_only=args.read_only,
        timeout=args.timeout,
    )
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
