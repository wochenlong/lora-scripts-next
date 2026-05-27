#!/usr/bin/env python3
"""Append supplement to port governance discussion #53."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

OWNER = "wochenlong"
REPO = "lora-scripts-next"
DISCUSSION_NUMBER = 53
API = "https://api.github.com/graphql"

SUPPLEMENT = """> **补充说明（2026-05-26）**
>
> 1. **文档来源**：`docs/design/ports/` 下三份设计文档（接口规范、迁移计划、优先级路线图）由团队成员 [@MikumikuDAIFans](https://github.com/MikumikuDAIFans)（Displace_Asher）整理提出，作为**技术方案草案**供讨论，**尚未经团队评审定为最终共识**。
> 2. **讨论定位**：本 Discussion 用于对齐端口/路径治理的方向与 P0 范围；采纳、修改或搁置均以团队在此处的结论为准，不代表已承诺按文档全文实施。
> 3. **项目背景**：端口问题只是 lora-scripts-next 当前多项工作之一（训练稳定性、整合包、Anima、数据集/打标、前端体验等并行）。端口 P0 力求**改动小、收益大**，避免占用整条发版线；其它事项仍按各自 Issue / 里程碑推进，互不阻塞但需维护者协调优先级。

---

"""


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if sys.platform == "win32":
        import winreg

        try:
            return winreg.QueryValueEx(
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment"), "GITHUB_TOKEN"
            )[0]
        except OSError:
            pass
    raise SystemExit("GITHUB_TOKEN not set")


def gql(token: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False, indent=2))
    return data["data"]


def main() -> None:
    token = get_token()
    data = gql(
        token,
        """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            discussion(number: $number) {
              id
              body
              url
            }
          }
        }
        """,
        {"owner": OWNER, "name": REPO, "number": DISCUSSION_NUMBER},
    )
    disc = data["repository"]["discussion"]
    if not disc:
        raise SystemExit(f"Discussion #{DISCUSSION_NUMBER} not found")

    body = disc["body"]
    marker = "**补充说明（2026-05-26）**"
    if marker in body:
        print("Supplement already present, skipping.")
        print(disc["url"])
        return

    new_body = SUPPLEMENT + body
    gql(
        token,
        """
        mutation($input: UpdateDiscussionInput!) {
          updateDiscussion(input: $input) {
            discussion { url }
          }
        }
        """,
        {"input": {"discussionId": disc["id"], "body": new_body}},
    )
    print(f"Updated discussion #{DISCUSSION_NUMBER}: {disc['url']}")


if __name__ == "__main__":
    main()
