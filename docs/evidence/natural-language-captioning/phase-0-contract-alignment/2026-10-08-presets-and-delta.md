# 2026-10-08 Issue #409 契约差异与预设首批实施

## 范围与基线

分支 feat/NL-Captioning，源 HEAD a6c1784；本轮是 Issue #409 重规划后的首次实施，非最终交付。#405 原文重新核对：项目根 user_data、类型隔离、原子保存/备份、schema_version、并发修订检测、显式一次性旧设置迁移。既有 auth.json 契约与用户锁定的仅运行时凭据边界不同；本任务维持用户更严格的运行时边界，不修改 Agent auth/provider。

## 差异表

| 要求 | 当前证据 | 后续动作 |
|---|---|---|
| 首版无组合入口 | Vue 已移除按钮/布局；API start/preview 返回 caption_combined_unsupported | manager 直接调用、retry、旧 combined 任务尚需拒绝/兼容审计 |
| user_data Caption 预设 | 新 prompt_presets 存储于项目根 user_data/presets；kind=caption_prompt | 与 #405 后续共享 CRUD 适配，确认多文件失败恢复和跨进程并发 |
| 类型隔离 | 保存只删除 Caption 文件，拒绝与其他类型 ID 冲突 | 补跨浏览器实际验收 |
| settings 保留 | 保存默认引用保留其他 settings 字段、保留 schema_version | 补多写入者场景 |
| 版本/备份/并发 | 预设 schema_version、内容 revision、文档 revision、409 冲突、上一份有效 .bak、fsync+replace | 多文件整体事务/锁补验 |
| 内置/用户模板 | Vue 分组，内置修改生成用户副本，另存为、恢复默认、切换未保存确认 | 实际浏览器和刷新行为补验 |
| 迁移 | 只提供 confirmed=true 的显式 import-legacy；用户已有 ID 胜出，旧文件不修改 | UI 显式导入按钮待接 |
| 单图/批量预设一致 | API 两条路径从 user_data 解引用，system prompt 进入生成和缓存 revision | 默认模板、系统提示词编辑和模型参数快照完善 |
| 底部进度/页面宽度 | CSS 改单列、最大1100px、底部静态进度和动作，目录占整行 | 浏览器桌面/390px验证 |
| 运行方式/模型分组 | 仍为 Tag/Caption 模式页 | 下一步 model-first catalog/selector、系列折叠和搜索 |
| 参数能力 | 仍有旧 flat request，Caption 带 Tag 字段 | 分离请求序列化和后端字段校验 |
| 安全写回/任务联动 | 已有持久任务、hash、Editor provenance | 与 user_data/tasks 档案和既有任务页联动复核 |
| 完整验收 | 历史证据仍在，未重验新契约 | 全矩阵、真实模型、Zero-Short、Phase5 fresh rebuild |

## 实际验证

后端 Python3.11：

```powershell
python -m pytest tests/test_caption_prompt_presets.py tests/test_caption_http_contract.py tests/test_caption_job.py tests/test_llm_client.py tests/test_llm_fake_integration.py -q
```

44 passed，2项既有依赖 warning，3.18秒。包含训练预设/settings保留、ID冲突、stale revision拒绝、显式导入、HTTP409、system prompt单图/批量冻结和组合预览拒绝。

前端 Node22.17.1：

```powershell
npm --prefix frontend run check
```

331 tests / 51 files，typecheck/lint/build通过；2项既有 EngineStatusBar lint warning，VueUse PURE注释和大chunk构建提示。新增未保存取消保护及内置模板另存用户副本测试。此次是实际源代码构建，tracked dist随后恢复基线，不提交构建产物。

## 状态

未执行新契约浏览器、真实资源或隔离重建。Phase0/1持续进行，不宣告阶段完成。Goal active，无 Agent/product接口修改。tests/test_diffsynth_review.py 保留既有未提交状态。

单一下一步：建立后端模型能力目录，并将 TaggerPage 的一级选择改为本地模型/API 服务；再按模型能力隔离请求字段。
