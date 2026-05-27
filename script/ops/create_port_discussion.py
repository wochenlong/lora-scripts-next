#!/usr/bin/env python3
"""Create GitHub Discussion for port governance (one-off ops script)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

OWNER = "wochenlong"
REPO = "lora-scripts-next"
API = "https://api.github.com/graphql"

BODY = """## 问题

lora-scripts-next 同时运行多个本地服务（主 WebUI、TensorBoard、训练监控、Dataset Tag Editor 等），在端口被占用、环境变量残留或前端硬编码子服务端口时，会出现：

- 训练监控入口打开成 TensorBoard，或反之；
- 训练监控误连 `6006` 的 API，页面报「无法连接 GUI API」但训练数据仍在同步；
- 用户需要记住 `28000` / `6006` / `6008` / `28001` 等多个端口；
- AutoDL / 云端只映射一个端口时，静默 fallback 导致平台映射失效。

该问题在多个版本迭代中反复出现，需要团队对齐**目标架构**与 **P0 落地顺序**，避免各自修补丁再次回归。

---

## 背景

- 项目从秋叶 `lora-scripts` 分叉，保留 TensorBoard、Gradio 打标等子服务，并新增 **训练监控**（默认 `6008`）。
- 主 WebUI 默认 `28000`；子服务端口可通过 `gui.py` 参数与环境变量配置，占用时会 fallback。
- 相关用户反馈与修复记录分散在 Issue / PR / 内部交接中；维护者与 Agent 曾反复因缺少统一契约而改回硬编码端口。
- 团队成员已提交三份设计文档（见下文「现有方案」），建议作为讨论依据，**不代表 main 已全部实现**。

---

## 现有方案

### A. 仓库内已落地（main，热修 / 部分 P0）

| 项 | 说明 |
|---|---|
| 默认端口保护 | `gui.py` 为已启用服务预留各自默认端口，减少 TensorBoard 抢占 `6008` 等 |
| 路径入口 | 主页 / 引导使用 `/train-monitor`，后端 `GET /train-monitor` 重定向到实际监控端口 |
| 监控 API | `train_monitor/server.py` 探测 GUI API；失败记 `gui_warning`，不阻断其它训练数据展示 |
| Cursor 规则 | `.cursor/rules/embedded-service-ports.mdc` 禁止前端硬编码 `127.0.0.1:6008` 等 |
| 设计文档目录 | `docs/design/ports/`（不进 README 用户传送门） |

**当前用户可见路径（与目标规范尚未完全一致）**：`/train-monitor`、`/tensorboard.html`、`/proxy/tensorboard/` 等。

### B. 团队设计文档（目标架构，待分期实现）

| 文档 | 内容 |
|------|------|
| [port-interface-standard.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/design/ports/port-interface-standard.md) | 长期规范：单公共入口 + 路径路由（`/monitor/`、`/tensorboard/`、`/tagger/`）、服务注册表、健康检查 |
| [port-routing-migration-plan.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/design/ports/port-routing-migration-plan.md) | 施工计划：改哪些文件、分阶段、PRT 验收矩阵 |
| [port-routing-priority-roadmap.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/design/ports/port-routing-priority-roadmap.md) | P0 / P1 / P2 优先级 |

**方向摘要**：用户只记一个 `public_base_url`（默认 `http://127.0.0.1:28000`），子服务通过路径访问；运行时 `.runtime/services.json` 为唯一事实来源。

---

## 需要确定的事项

请维护者 / 贡献者在回复中表态（可用 👍 / 评论编号）：

1. **是否认同「单公共入口 + 路径路由」为终态？** 是否接受过渡期保留 `/train-monitor`、`/proxy/tensorboard/` 等旧路径？
2. **P0 是否接受「最小注册表」**：先用现有端口（6006/6008/28001）写入 `services.json`，**不强制** P0 内切换到 281xx 内部端口池？
3. **路径命名**：P0 是否新增 `/monitor/` 作为 `/train-monitor` 的别名（302），还是 P0 仍只用 `/train-monitor`？
4. **AutoDL 严格模式**：用户显式 `--port` / `--gateway-port` 且端口被占用时，是否**必须失败**（禁止静默 fallback）？
5. **Tag Editor / Gradio WebSocket**：是否同意放入 **P0 后半或 P1**（技术风险高于端口隔离本身）？
6. **TensorBoard `/tensorboard/` 反代**：是否同意 **P1**，P0 仅保证 `/tensorboard.html` 与 proxy 可用？
7. **发布门禁**：是否在 P1 引入 `rg` 扫描用户入口中的 `127.0.0.1:6006|6008|28001`？
8. **负责人**：P0 各子项是否有人认领（可跟帖「认领 P0-x」）？

---

## 建议确认的优先度（共识草案）

| 层级 | 范围 | 说明 |
|------|------|------|
| **P0** | 行为正确、少踩坑 | 端口不串台、链接路径化、监控连对 API、启动日志/清单、AutoDL 严格端口 |
| **P1** | 工程化 | 完整注册表、健康检查、`/tensorboard/` `/tagger/` 反代、WS/SSE 测试、文档与 rg 门禁 |
| **P2** | 扩展 | 插件注册、API 版本、多实例、公网权限、观测与诊断平台 |

---

## P0 待办事项（建议执行顺序：改动小 → 收益大在前）

状态列供跟帖更新：`[ ]` 未开始，`[x]` 已完成，`[~]` 进行中。

| ID | 状态 | 事项 | 说明 |
|----|------|------|------|
| P0-1 | [x] | 各服务默认端口互不抢占 | `gui.py` `protected_default_ports`；建议补回归单测 |
| P0-2 | [x] | 主页/引导监控链路径化 | `/train-monitor`，patch 脚本；发布前 `rg` 扫 `:6008` |
| P0-3 | [x] | 训练监控连主 WebUI API | 探测 + `gui_warning`；可再接注册表 |
| P0-4 | [ ] | 启动日志打印「访问地址清单」 | 主站、监控、TB、打标最终 URL |
| P0-5 | [ ] | 浏览器自动打开路径入口 | 打开主站 + `/train-monitor`，非 `:6008` |
| P0-6 | [ ] | 最小 `.runtime/services.json` | 启动时写入；`.runtime/` gitignore |
| P0-7 | [ ] | 监控从注册表读 `api` 地址 | 替代仅 env 推断 |
| P0-8 | [ ] | 公共入口 28000 fallback 28001–28020 | 仅未显式指定端口时 |
| P0-9 | [ ] | AutoDL 显式端口占用则失败 | 避免映射错位 |
| P0-10 | [ ] | Tag Editor / proxy 去除硬编码 28001 | env 或注册表 |
| P0-11 | [ ] | `/monitor/` 与 `/train-monitor` 并存 | 302 别名，不删旧路径 |
| P0-12 | [ ] | `/tensorboard/`、`/tagger/` 全路径反代 | **建议 P0 后半或 P1** |
| P0-13 | [ ] | 内部端口迁 281xx 池 | **建议 P1**，非 P0 阻塞项 |
| P0-14 | [ ] | PRT-007/008 等验收 | 先单测 + 手工 checklist |

### P0 验收（最小集）

- PRT-007：TensorBoard 占用监控候选端口时，`/train-monitor`（或 `/monitor/`）不得打开 TB。
- PRT-008：训练监控请求主 WebUI `/api`，不得访问 `6006/api`。

---

## 相关链接

- 设计文档索引：[docs/design/ports/README.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/design/ports/README.md)
- 用户文档（当前行为）：[docs/train-monitor.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/train-monitor.md)、[docs/cli-args.md](https://github.com/wochenlong/lora-scripts-next/blob/main/docs/cli-args.md)
- 端口痛点 Issue（若已创建请跟帖编号）

---

**请回复**：对「需要确定的事项」逐条意见，并认领 P0-4～P0-14 中你可负责项。确定后可将共识写回 `docs/design/ports/README.md` 的「P0 执行顺序」小节。
"""

TITLE = "【讨论】端口与路径路由治理：背景、方案、待决事项与 P0 待办"


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
        query($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            id
            discussionCategories(first: 20) {
              nodes { id name slug }
            }
          }
        }
        """,
        {"owner": OWNER, "name": REPO},
    )
    repo_id = data["repository"]["id"]
    cats = {c["slug"]: c for c in data["repository"]["discussionCategories"]["nodes"]}
    if not cats:
        raise SystemExit("No discussion categories on repo")
    # Prefer General / Ideas / Q&A
    for slug in ("general", "ideas", "q-a", "announcements"):
        if slug in cats:
            category_id = cats[slug]["id"]
            break
    else:
        category_id = next(iter(cats.values()))["id"]

    result = gql(
        token,
        """
        mutation($input: CreateDiscussionInput!) {
          createDiscussion(input: $input) {
            discussion { number url title }
          }
        }
        """,
        {
            "input": {
                "repositoryId": repo_id,
                "categoryId": category_id,
                "title": TITLE,
                "body": BODY,
            }
        },
    )
    d = result["createDiscussion"]["discussion"]
    print(f"Created discussion #{d['number']}: {d['url']}")


if __name__ == "__main__":
    main()
