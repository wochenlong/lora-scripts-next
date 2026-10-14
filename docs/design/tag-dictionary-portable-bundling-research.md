# Tag 中文词库随整合包内置：调研与接入方案

日期：2026-10-13（Asia/Shanghai）。范围：当前 `feat/NL-Captioning` 工作副本的词库服务、下载 CLI、Windows 整合包构建与 Release 更新。状态：源码审计、上游核实和公共词库最小分发探针完成；本轮不修改业务实现或构建脚本，不产出完整整合包。

实施追加：用户后续已批准全面执行。当前实现与真实从零宿主验收已完成，见 [实施与从零验收](../evidence/tag-translation/2026-10-13-dictionary-bundling-acceptance.md)；下文保留调研时的现状和决策依据。

## 结论与产品契约

可以在打包时下载 Tag 中文词库并保留在整合包中。现有主构建链已经有默认开启的预取步骤，后端也能直接离线使用包内 SQLite；需要修补现有链路的依赖、副作用、校验和更新边界，使“默认内置”成为所有正式包型的发行门。

用户新要求取代历史“词库首次现场下载”的发行策略。二进制数据库仍不提交 Git，构建产物默认包含公开词库；用户首次启动无需为词库执行下载或配置模型。保留手动检查更新、更新/重试入口。词库未命中的 Tag 仍遵循“词库 + 免费接口”或“词库 + LLM”的既有来源选择；内置词库不意味着未收录标签也能离线翻译。自然语言正文仍固定使用共用 LLM，不使用此 Tag 词库。

## 现场核实的来源与体积

来源：[ffdkj Danbooru 中英文对照表](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table)。现场 Contents API 与固定 commit 下载结果如下：

| 项目 | 结果 |
| --- | --- |
| 上游 commit | `623a41c0ba1ea8b7be0ccf7cc925b15f8ec77222` |
| commit 时间 | `2026-10-11T12:50:37Z` |
| 文件 | `tag.sqlite` |
| 字节数 | 24,678,400，约 24.7 MB / 23.54 MiB |
| 条目数 | 332,385，现场只读 SQL 查询 |
| Git blob SHA | `d9e302a6078ac266ab17c48aa79477c262cc1da9` |
| SHA256 | `876ee9885218a7c1dbf7c879ef7b3339024eb47b3f9e8b98fbb77af16897a2bb` |
| ZIP 探针字节数 | 14,602,033，约 14.6 MB / 13.93 MiB，含下列四份资产 |
| 许可 | [上游 MIT LICENSE](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table/blob/623a41c0ba1ea8b7be0ccf7cc925b15f8ec77222/LICENSE)，版权 2026 ffdkj |

上游公开许可包含分发许可与保留版权/许可文本的条件。因此随数据库附完整 LICENSE 和来源信息；当前 Aaalice 迁移代码的许可文件不能替代该数据库的许可。上述体积是 ZIP 探针实测，不是最终 7z 增量体积，也不承诺未来词库仍为相同大小。

推荐整合包公共资产契约：

```text
Next-Trainer/
  assets/tag_translation/danbooru/
    tag.sqlite
    metadata.json
    source-manifest.json
    LICENSE.ffdkj.txt
```

`metadata.json` 保持现有运行时字段，包括 installed/remote blob SHA、row_count、时间和来源 URL；`source-manifest.json` 记录出厂固定 commit、SHA256、大小、条目数和许可文件身份。出厂清单描述发行基线，用户后续更新的实际库身份由运行 metadata 跟踪，不能用原出厂 hash 拒绝用户合法更新。

## 当前链路与实际缺口

| 位置 | 已有行为 / 待完善项 |
| --- | --- |
| `build-scripts/build_portable.ps1:625` | Step 3c 默认下载词库到包内目录；只有显式 `-SkipTagDictionaryPrefetch` 才跳过。已有文件只经 `Test-Path` 判断，不验证完整性。 |
| `build_portable_2026_full.ps1`、`build_portable_kohya_only.ps1` | 正常构建继承主构建链的默认词库步骤。 |
| `build_portable_musubi_only.ps1`、`resume_portable_2026_full.ps1` | 正常构建继承；跳过 skeleton / 恢复已有输出时缺少统一词库门。 |
| `build-scripts/build-all.ps1:42`、`03-copy-project.ps1:66` | 旧链整仓复制，没有专用预取。未排除 `assets/tag_translation`，词库可能缺失，也可能误带开发机配置、译文缓存和模型。 |
| `scripts/prefetch_tag_dictionary.py:36` | 为获得默认路径导入业务 runtime；CLI 解析参数之前就加载整个翻译/LLM 依赖链，并在依赖齐全时初始化默认根的 SQLite 缓存。传 `--directory` 也不能消除此副作用。 |
| `build_portable.ps1:618`、`:644` | 前阶段清空 embedded site-packages，词库阶段只装 aiohttp；runtime 导入链要求 Pillow，全新构建可能在解析参数前失败。 |
| `prefetch_tag_dictionary.py:95` | `--if-missing` 只检查文件存在，可将损坏数据库当作已安装。 |
| `prefetch_tag_dictionary.py:62` | raw fallback 只查 COUNT(*)、自行计算 SHA 后作为 remote SHA 记录，缺完整 schema / quick_check / 与独立预期 hash 的比较，下载 URL 默认 main。 |
| `mikazuki/tag_translation/runtime.py:17` | 默认路径由项目源码位置确定，整包移动后仍能定位；环境变量 `MIKAZUKI_TAG_TRANSLATION_ROOT` 完全覆盖路径，空外置数据根没有包内播种策略。 |
| `chinese_dictionary_service.py:115` | 已有库时 `ensure()` 不联网；已有完整 SQLite 验证函数可复用。运行 ready 当前主要依赖文件存在，应避免以此替代发行验证。 |
| `scripts/portable/update_from_release.ps1:203` | `/E /IS /IT` 更新合并未排除 `assets/tag_translation`，包内空缓存可覆盖用户缓存，较旧出厂库可覆盖用户更新后的词库。 |
| `scripts/portable/verify_portable_release.ps1` | 没有词库硬门；现有 packaging test 主要匹配脚本文本，不能证明最终包内资产可用。 |

主构建器通过已提交 HEAD 的浅克隆生成干净项目，忽略文件通常不会从开发机带入；但预取脚本本身仍能生成包内缓存。当前工作副本存在未提交功能改动，真正打包前必须固定候选提交，不能把开发工作副本验证误认为归档已包含这些改动。

## 已完成的隔离探针

所有下载与探针位于 `.runtime/tag-dictionary-packaging-research-20261013/`，未访问用户现有词库、配置、密钥、模型或业务缓存，未重启运行项目。

1. 从固定 commit 下载公开数据库和完整 LICENSE；对照 GitHub Contents 的 blob SHA，通过 SQLite magic/四列结构、quick_check、非空行数检查，计算 SHA256。
2. 生成公共 metadata/source manifest，仅打入四份公共资产，ZIP 中无 `translation.json` 或 `translations.sqlite3`。
3. 解压到另一目录，哈希相同；使用现有 `ChineseDictionaryService`，禁用网络 session factory，`ensure('zh-CN')` 为 ready、零网络调用。查询 `blue_eyes=蓝瞳`、`long_hair=长发`、`white_background=白色背景`。
4. 在独立空 runtime 根执行现有预取 CLI 的 `--help`：退出码 0，但默认 `danbooru/` 和 `translations.sqlite3` 已创建；指定输出目录尚未创建。确认副作用发生在参数解析前。
5. 在独立进程模拟构建阶段缺 Pillow：现有 CLI 的 `--help` 在参数解析前抛出 `ModuleNotFoundError`。这是依赖边界模拟，未实际安装新的 embedded Python 或执行完整构建。

证据：`result.json`、`probe_offline_dictionary.py`、`dictionary-payload-probe.zip`、`import-full-dependencies/result.json`、`import-no-pillow/result.json`、`probe_prefetch_imports.py`。本轮只验证公共资产可分发与直接服务离线可用，没有完整应用 HTTP/UI 冷启动或真实最终 7z 验收。

## 最小实施方案

1. **先解耦预取脚本。** 独立计算目录或引入轻量路径模块；只加载词库下载/校验所需模块。统一维护可提交的公开来源锁定清单，默认固定 commit/hash；不为预取额外安装完整 LLM/训练依赖，不创建运行缓存。
2. **统一预取和验证。** 复用词库完整性验证函数；已有文件先校验，不能只 `Test-Path`。所有网络候选（包括 API 限流 fallback）验证同一预期 blob SHA / SHA256。下载到临时文件，验证后原子安装；失败阻断发行，不能生成“缺词库也成功”的正式包。metadata/许可/来源清单也纳入验证。
3. **接入全部发行入口。** 主入口、旧 build-all、正常/恢复/SkipSkeleton 均调用同一词库准备和归档前验证门。开发诊断可保留 skip 开关，但正式 release 验收必须拒绝缺库或坏库，不使用用户当前资源目录作为打包种子。
4. **严格限定发布文件。** 整包复制排除 `assets/tag_translation` 用户状态，再只注入公共词库四份资产。发行验收拒绝该区域出现 `translation.json`、`translations.sqlite3`、WAL/SHM、模型/runtime、临时下载文件或维护机配置。
5. **适配外置用户根。** 默认根直接使用包内库；如果外置翻译根为空，从已验证包内库首次原子播种。已有有效用户库保持，不覆盖新版或显式设置。不自动以出厂版本替换用户损坏库，提供明确状态与现有重试途径。
6. **保护升级。** Release 更新保留用户翻译配置、缓存、模型/runtime 和已有词库；仅在目标缺库时播种公共词库。已有库的升级由原词库更新器处理，避免版本回退。更新器不删除整个翻译资源目录。
7. **补文档与验收。** 打包指南声明内置契约、版本锁定和断网首用；保留历史按需下载记录，追加本次策略。最终包解压到新位置、空用户根、阻断外网后验证，不用 staging 文件存在代替最终包验收。

## 实施后的验收门

| 验收门 | 必须证明 |
| --- | --- |
| 干净构建 | 只安装预取必要依赖即可运行；不会读写默认业务缓存，显式 staging 路径有效。 |
| 复用/失败 | 已验证同版本可以断网复用；损坏、截断、错 hash/schema、限流 fallback 与网络失败不会误放行发行。 |
| 所有入口 | 正常包、恢复包、训练裁剪包、旧入口都满足四份公共资产及同一验证门。 |
| 最终归档 | 解压后的文件 hash/结构/条目数匹配发行清单，公共词库边界无用户状态。 |
| 首次离线 | 默认根、外置空用户根均 ready；已知 Tag 释义正常、词库命中零免费接口/LLM调用、零词库下载任务。 |
| 升级 | 用户配置/cache/model/runtime保持；用户较新词库不降级；缺库播种成功。 |
| 功能保持 | 两种 Tag 来源词库优先、只处理缺词；自然语言翻译固定 LLM，原文不因打包发生改动。 |

下一步：实现轻量预取与统一验证门，再将它接入所有构建和更新入口。
