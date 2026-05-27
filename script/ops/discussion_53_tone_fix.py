#!/usr/bin/env python3
"""Soften Discussion #53 closing tone and post invite comment to @MikumikuDAIFans."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

OWNER = "wochenlong"
REPO = "lora-scripts-next"
DISCUSSION_NUMBER = 53
API = "https://api.github.com/graphql"

OLD_CLOSING = """---

**请回复**：对「需要确定的事项」逐条意见，并认领 P0-4～P0-14 中你可负责项。确定后可将共识写回 `docs/design/ports/README.md` 的「P0 执行顺序」小节。
"""

NEW_CLOSING = """---

欢迎在下方**随意跟帖**：若对「需要确定的事项」有想法、对 P0 表有不同排序或想一起做其中某几项，直接写出来即可；不必按固定格式回复。讨论沉淀后，维护者会把**已达成的一致意见**整理进 `docs/design/ports/README.md`（例如「P0 执行顺序」），草案文档也会随结论更新。
"""

INVITE_COMMENT = """@MikumikuDAIFans 你好，感谢整理 `docs/design/ports/` 下三份端口/路径草案，我们已放进仓库的 `docs/design/ports/` 并开了本讨论串（文首补充说明了：目前是**方案草案**，还不是团队定稿）。

想请你和其他关心这块的同学一起看看：

- 方向是否贴合你当初的设想？有没有需要改或暂缓写的部分？
- 若愿意，可以在上文「需要确定的事项」或 P0 表里随手留言——**开放式讨论即可**，没有固定回复模板，也不必「认领」任务；只是方便大家对齐接下来先做什么。

端口只是项目里并行的一件事，其它线（训练、整合包、Anima 等）也会继续推进；这里主要是避免再反复踩端口/TB/监控错连的坑。谢谢 🙏
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
    body = disc["body"]

    if OLD_CLOSING in body:
        new_body = body.replace(OLD_CLOSING, NEW_CLOSING)
        gql(
            token,
            """
            mutation($input: UpdateDiscussionInput!) {
              updateDiscussion(input: $input) { discussion { url } }
            }
            """,
            {"input": {"discussionId": disc["id"], "body": new_body}},
        )
        print("Updated discussion closing tone.")
    elif NEW_CLOSING.strip() in body:
        print("Closing already updated.")
    else:
        print("Warning: old closing not found; body ending not patched.")

    gql(
        token,
        """
        mutation($input: AddDiscussionCommentInput!) {
          addDiscussionComment(input: $input) {
            comment { url }
          }
        }
        """,
        {"input": {"discussionId": disc["id"], "body": INVITE_COMMENT}},
    )
    print(f"Posted invite comment on {disc['url']}")


if __name__ == "__main__":
    main()
