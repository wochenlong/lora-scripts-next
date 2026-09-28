# 标签翻译迁移清单与 Phase 1 探针证据

日期：2026-09-29  
目标分支：`feat/tag-translation`  
关联任务书：`docs/tasks/tag-translation-task-book.md`  
参考项目：`ComfyUI-Autocomplete-Aaalice`  
参考快照：`37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0`（2026-08-31）

## 1. 来源和许可证

Aaalice 仓库的 `LICENSE` 是 MIT。迁移时保留版权和许可证说明，不复制 ComfyUI 业务页面。

WeiLin 仓库的 `LICENSE` 是 GPL-2.0-only，本次不直接复制其实现代码，只保留行为和分层参考。

Aaalice 核心源文件 SHA-256：

| 文件 | SHA-256 | 结论 |
| --- | --- | --- |
| `modules/chinese_dictionary_service.py` | `DDD77E49B96E063B63287FA6A57BD14BB031B0A4C63ACD245B29B95079207B15` | 迁移核心类，改用户路径和 HTTP 适配 |
| `modules/translation_service.py` | `8F23D092C73B64277A09FEAD310E1A23FF1AB1AD974B4DE25DF3652E36D1C362` | 迁移批量/重试/校验，替换 DeepSeek 专用配置 |
| `modules/translation_store.py` | `A8CB4B34FBF11F11506A5DAA1625B7593A360E6EF96D03D020BA10A552EFABE8` | 可选迁移，先评估是否需要持久缓存 |
| `modules/translation_config.py` | `5B2E8F307BEC126DE49D6AC13E94CE938F3A0747E52E289A9A07AE853C87F051` | 迁移配置模型，改 provider 字段 |
| `modules/api.py` | `DC443B789F82186549F3DD157E27AD350F6AFC704C101A4FCC83EB4A59C64663` | 不直接迁移，提取接口契约改写为 FastAPI |

## 2. 依赖扫描结论

### 可以直接迁移核心逻辑

`chinese_dictionary_service.py` 使用标准库和 `aiohttp`，不依赖 ComfyUI。保留下载、校验、查询逻辑，注入 Next Trainer 的 HTTP session 和用户数据目录。

`translation_service.py` 使用标准库、`aiohttp`、`translation_config.py` 和 `translation_store.py`，不依赖 ComfyUI。保留批处理、重试、拆批和 JSON 校验，抽象 DeepSeek 为通用 OpenAI 兼容 endpoint。

`translation_store.py` 只使用 `sqlite3`、`contextlib` 和 `datetime`，不依赖 ComfyUI。它可直接迁移，但首版先保留为可选，避免把“翻译缓存”和“词库 SQLite”混为一个数据库。

`translation_config.py` 只使用标准库，保留 masked config 和原子写入，改为 Next Trainer 的设置入口。

### 必须改写

`api.py` 依赖 `folder_paths`、`server.PromptServer`、`aiohttp.web` 以及 Aaalice 的 completion、Danbooru 和 CSV 模块。因此不复制 `api.py`，只迁移翻译相关 endpoint 的输入/输出契约到 Next Trainer FastAPI。

Aaalice 的 `web/` 页面直接依赖 ComfyUI DOM 和文本框事件。不复制页面，只参考加载状态、来源状态和流式翻译展示，在 `DatasetEditorPage.vue` 中实现薄适配。

## 3. ffdkj SQLite 探针

临时探针路径：`.tmp/tag-translation-probe/tag.sqlite`。该目录在 `.runtime` worktree 下，不进入提交。

下载元数据：

```text
source: ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table
remote GitHub blob SHA: 9fd36696392d459b7b29dc645a14fb4ea1edd16e
file size: 24,387,584 bytes
local SHA-256: 22e08842eef5d7a8442f525D8CF6EE0E6FF1C0C25FAF4226F63AC61AE077ABD9
```

SQLite 校验：

```text
PRAGMA quick_check: ok
tables: tags
rows: 330241
columns: name, category, cn_name, post_count
```

UTF-8 查询样本：

| tag | category | cn_name | post_count |
| --- | ---: | --- | ---: |
| `blue_eyes` | 0 | 蓝瞳 | 2,487,418 |
| `long_hair` | 0 | 长发 | 6,252,853 |
| `1girl` | 0 | 单人女性 | 8,468,518 |
| `hakurei_reimu` | 4 | 博丽灵梦（东方Project） | 101,478 |
| `touhou` | 3 | 东方Project | 1,101,852 |
| `unknown_tag` | - | 未命中 | - |

探针结论：下载元数据流程可用；SQLite schema 与 Aaalice 查询逻辑一致；词库有 330,241 行，体积约 23.3 MiB；查询可直接使用 `name` 主键；`cn_name` 已覆盖 general、character、copyright 等类别；后续仍需审计许可、更新频率和错误译名治理。

## 4. 迁移边界

| 来源能力 | Next Trainer 动作 | Phase 1 结论 |
| --- | --- | --- |
| SQLite 下载和 SHA/完整性检查 | 迁移核心类 | 直接迁移，注入路径和 session |
| Danbooru lookup | 新建 FastAPI service wrapper | 直接复用查询逻辑 |
| DeepSeek 专用 client | 通用 OpenAI 兼容 client | 改写 endpoint/config，不照搬 provider 名称 |
| retry / split / response validation | 保留 | 直接迁移后补测试 |
| translation_store | 先保留为可选 | Phase 2 决定是否启用持久缓存 |
| ComfyUI API routes | FastAPI router | 不迁移，只按契约重写 |
| ComfyUI web overlay | Dataset Editor chip/tooltip | 不迁移页面，只迁移交互语义 |
| Aaalice completion/alias 模块 | 当前不需要 | 不迁移 |
| WeiLin local_translate.py | 行为参考 | 不复制，避免 GPL-2.0-only 代码边界 |

## 5. Phase 1 结论

Phase 1 的迁移清单、依赖扫描、许可证边界和 SQLite 最小探针已经完成。下一阶段应在 `mikazuki/tag_translation/` 中迁移 Aaalice 的词库核心和配置/服务核心，暂不迁移 ComfyUI API、前端页面或持久翻译缓存。
