# 风险备忘录（维护者）

> 记录**已发生过或高概率再次发生**的风险与检查项。发 Release、合 `main`、打整合包前建议扫一眼。详细操作见 `build/整合包打包规范.md`、`doc/local/AGENT_INTERNAL.md`（本地）。

## 发布与整合包

| 风险 | 后果 | 检查 / 规避 |
|------|------|-------------|
| 7z 打入本机 `config/autosave`、私有 preset、日志 | 用户隐私泄露、配置串号 | 打包前确认来源为干净 worktree；`7z l` 抽查；规范禁止带入 `doc/`、`data/` |
| 整合包缺 `frontend/dist` 图片或静态资源 | 主页裂图、引导异常 | 对照 `assets/readme`、发布 checklist |
| 整合包 `mikazuki` 与 main 不同步 | 缺 API（如 train tasks）、P0 行为不一致 | 热修后同步 main + 重打 7z；或明确版本说明 |
| 用户 `git pull` 与纯 7z 用户路径不一致 | 更新后仍旧 bug | Release 说明写清「需新 7z」或 `Update-Next-Trainer.bat` |
| 根目录契约 bat/sh 被改名或删除 | 双击无法启动、AutoDL 开机失败 | [repo-layout.md](../repo-layout.md)；PR 需主维护者审批 |

## 端口与子服务

| 风险 | 后果 | 检查 / 规避 |
|------|------|-------------|
| 前端 / patch 硬编码 `127.0.0.1:6008` | 点开训练监控却进 TensorBoard | 用 `/train-monitor`；`.cursor/rules/embedded-service-ports.mdc` |
| TensorBoard fallback 占用 6008 | 同上 | `gui.py` 保护各服务默认端口 |
| 训练监控连 `6006` API | 404、误导报错 | `train_monitor` 读主 WebUI 端口；`gui_warning` 非阻断 |
| AutoDL 显式端口被静默 fallback | 平台映射失效 | 显式指定端口时占用应失败（待 Issue 落地） |
| 浏览器自动打开子服务裸端口 | 用户记错地址 | 打开主站 + 路径入口 |

讨论与草案：[Discussion #53](https://github.com/wochenlong/lora-scripts-next/discussions/53)、`docs/design/ports/`。

## 训练与后端

| 风险 | 后果 | 检查 / 规避 |
|------|------|-------------|
| `config/autosave` 目录不存在 | `/api/run` 500，无法开训 | 写 toml 前 `makedirs` |
| Windows `torch_compile` + Triton | 启动即崩 | `sanitize_config` 移除 compile |
| Anima `full_bf16` + 部分优化器 | `loss=nan` | `apply_anima_training_defaults`；见 `docs/anima-training.md` |
| Accelerate resume 缺 `step` 元数据 | 续训 KeyError | `train_util` fallback |
| 改 `vendor/sd-scripts` 面过大 | 难合并上游 | 控制 diff，关键路径加测试 |

## 协作与流程

| 风险 | 后果 | 检查 / 规避 |
|------|------|-------------|
| 无 Issue 直接改 main | 无法追溯、优先级混乱 | [团队约定](README.md)：仅 Issue 进入解决流程 |
| 设计草案当定稿实施 | 与 main 行为不一致 | 文首标草案；Discussion 讨论后再拆 Issue |
| 多人同时改 `frontend/dist` | 冲突、漏 patch | 约定 patch 脚本与负责人；PR 说明 |

## 修订

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 初版：合并已知整合包、端口、训练与协作风险 |

发现新事故后请开 Issue，修复合并后在本表补一行（或 PR 更新本文件）。
