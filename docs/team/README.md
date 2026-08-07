# 团队协作约定（维护者）

> 面向核心维护者与贡献者；**不上 README 主页传送门**。当前为多人协作初期的运作方式，随团队扩大可修订。  
> 成员介绍与历史 PR 见根目录 [`CONTRIBUTORS.md`](../../CONTRIBUTORS.md)。

## 成员与分工（当前）

| 成员 | 角色 | 主要负责 | 写代码 | 备注 |
|------|------|----------|--------|------|
| [@wochenlong](https://github.com/wochenlong) | 项目负责人 | 全栈；发布 / 合 `main` / PR review；项目级决策 | 是 | 契约路径与发版最终审批 |
| [@SupermarKleet](https://github.com/SupermarKleet) | UI / 美术 | 界面设计、品牌与素材（看板娘、Logo 等） | **否** | 交付设计稿与资产，由开发落地到 `frontend/dist` 或 patch |
| [@ageless-h](https://github.com/ageless-h) | 后端开发 | Anima / sd-scripts 后端、整合包相关修复 | 是 | **未来约 1～2 周较忙，暂不接新任务**；紧急项由项目负责人协调 |
| [@niangao2331](https://github.com/niangao2331) | 开发（vibe coding） | 打标器、Dataset Tag Editor | 是 | 若实践后难以独立维护该模块，可改任 **Issue 分诊**（仍参与协作，调整职责） |
| [@MikumikuDAIFans](https://github.com/MikumikuDAIFans) | 开发（vibe coding） | 训练引擎相关、**端口与路径治理**（草案见 `docs/design/ports/`） | 是 | 先小步落地 P0；方案为草案，合入前经 Discussion / PR review |
| [@IryNeko](https://github.com/IryNeko) | 前端重构 | Vue3 四栏 IA、训练工作台与前端源码（`dev` / [#209](https://github.com/wochenlong/lora-scripts-next/pull/209)） | 是 | 核心参与前端重构；持续合入以 `dev` 为主 |

### 领域负责人（DRI）

与上表对应；领域内在不破坏其它模块稳定、对用户有明确收益时，负责人可自行决策后提 PR（见下节「决策」）。

| 领域 | DRI | 备份 / 协调 |
|------|-----|-------------|
| 项目级 / Release / 合 `main` | @wochenlong | — |
| UI / 品牌素材 | @SupermarKleet（出图） | @wochenlong（进仓库） |
| Vue3 前端 / `dev` IA | @IryNeko | @wochenlong |
| 打标 / Dataset Tag Editor | @niangao2331 | @wochenlong |
| 端口、启动、`gui.py` 子服务 | @MikumikuDAIFans | @wochenlong |
| 训练引擎 / Anima 后端 / sd-scripts | @MikumikuDAIFans（引擎与端口线） | @ageless-h（恢复后）、@wochenlong |
| 整合包构建与发布质检 | @wochenlong | @ageless-h（恢复后） |
| Issue 分诊 | _待定_（候选 @niangao2331） | @wochenlong |

---

## 决策

| 层级 | 谁定 | 说明 |
|------|------|------|
| **项目级** | @wochenlong | 跨模块、发布、契约路径、优先级、是否采纳设计草案 |
| **领域级** | 上表 DRI | 改动**不削弱其它功能稳定性**且**对用户有明确正面作用**时，可自行决策并提 PR |
| **方案讨论** | 开放式 | [Discussions](https://github.com/wochenlong/lora-scripts-next/discussions)（如 [端口 #53](https://github.com/wochenlong/lora-scripts-next/discussions/53)、[整合包更新 #73](https://github.com/wochenlong/lora-scripts-next/discussions/73)）不定稿；**落地须拆 Issue** |

---

## 待办与 Issue（强制）

- **所有进入「要解决」流程的工作，必须有 GitHub Issue**。
- Discussion、口头约定不代替 Issue；结论落地时新建或关联 Issue 再开发。
- PR 关联 Issue；本地 `doc/local/scratch/` 不作团队排期依据。

**Issue 分诊**：待指定（候选 @niangao2331）。职责：浏览新 Issue、打标签、查重、按 [priority.md](priority.md) 建议优先级（项目级优先级由 @wochenlong 确认）。

---

## 发布、合并与审批

| 事项 | 当前约定 |
|------|----------|
| **Release** | @wochenlong |
| **合并 `main`** | @wochenlong |
| **契约路径改动** | @wochenlong 审批（[repo-layout.md](../repo-layout.md)） |
| **PR Review** | 当前阶段 @wochenlong |
| **`main`** | 可发布基线；**不直接在 `main` 开发**，功能分支 + PR |

整合包见 [`build/整合包打包规范.md`](../../build/整合包打包规范.md)。

---

## 协作规矩（当前阶段）

1. `main` 拉分支 → PR → @wochenlong review → 合并。  
2. 契约路径改动须在 PR 中说明并已审批。  
3. 讨论保持开放；可交付工作以 Issue 为准。  
4. 设计草案在 `docs/design/`；用户文档在 `docs/`。

---

## 全项目优先级

由 @wochenlong 维护总表；**条目级 backlog** 见 **[backlog-priorities.md](backlog-priorities.md)**（含 **发版 TOP** / **排期 TOP**、AI 建议列与空的「团队优先级」列）。分级定义见 [priority.md](priority.md)（草案）。端口与 #41：先完成排期第一阶段门禁，再上大 UI。领域 Discussion 中的 P0 须与全项目 P0 对齐，但不等同。

---

## 后续待办（团队）

| 项 | 状态 | 说明 |
|----|------|------|
| 贡献者入门文档 | 待做 | Issue 跟踪 |
| P0/P1/P2 定稿 | 草案 | [priority.md](priority.md) |
| Issue 分诊人确认 | 待定 | 候选 @niangao2331 |
| @ageless-h 恢复后排期 | 暂停 | 后端 / 整合包支援 |

---

## 相关链接

- [全项目待办优先级总表](backlog-priorities.md)
- [风险备忘录](risk-memo.md)
- [优先级分级（草案）](priority.md)
- [仓库契约路径](../repo-layout.md)
- [端口设计（草案）](../design/ports/README.md)
- [CONTRIBUTORS.md](../../CONTRIBUTORS.md)
