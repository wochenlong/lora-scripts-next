# 持久任务、错误矩阵与真实批量验证

本批次基于 a308a8b，属于 Phase 1 后端完成门证据。未声称前端完整验收、EDD 评分或 Phase 4 完成。

## 实现

- 任务状态、原请求的受限字段、计划图片、已处理索引、失败项和写回意图保存在共享 `translations.sqlite3` 的 caption 表中；API Key、完整 LLM 配置和提供方原始响应不进入任务存储。
- 私有恢复数据包含服务端路径及原 caption 字节备份，存于后端数据目录，不进入公开 report/history 响应或 Git。公开报告返回快照修订、模式/语言、profile/prompt revision、图像/写回 hash、错误码和结果。
- 服务重启不自动推理。已完成项保持不变，未处理项标记 interrupted、等待显式重试；部分失败重试只处理失败路径；每次重试创建关联 parent_job_id 的新任务，使用当前 LLM 配置与凭据，同时保留原提示词和 before hash。
- 原子写回前记录 intent。若进程在文件替换后、结果提交前退出，恢复时以 after hash 识别已完成写回，避免再次 prepend/append。
- prompt_id 在提交时展开为冻结模板/语言；用户后来删除预设，失败重试仍使用冻结内容。公开 report 不返回私有恢复字段。
- 新增 history、历史 detail 和 report API；组合预览真正组合 WD/CL Tag 与 LLM 自然语言，保持不写盘；预览服从共享 busy/cancel guard。
- 新旧 Tag 写回均采用 atomic replace/before hash；Tag 格式保持旧排序、去重、冲突策略及末尾字节约定。自然语言/mixed 禁止进入 Tag 合并清理；短自然语言另以路径+hash 的生成来源信息保护。
- 移除 Tag 日志中的输入/输出绝对路径，错误提示只显示分类，不回显提供方正文或缓存路径。旧 Tag 发生冲突时卸载模型并释放任务占用。

## 测试与覆盖

实际运行独立 Python 3.11.15 venv 的相关回归：

```powershell
& <runtime-python> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
```

本批首次完整相关 suite：195 passed / 4 warnings / 15.29s；新增组合布局后 199 passed / 4 warnings / 20.24s；fallback report 后 200 passed；补预设上限/revision 和 EXIF 隐私测试后最终 203 passed / 4 warnings / 18.10s。Node 22 完整 check 最新为 309 tests / 48 files passed，typecheck/lint/build pass；lint 2 项已有 warning，build 1858 modules / 8.46s。

| 用例 | 实际行为证据 |
| --- | --- |
| 重启后部分失败重试 | 完成文件字节保持不变，只调用失败图片，旧任务报告仍可查询 |
| 写回后强制退出 | 子进程 os._exit(91)，重新构造 manager，after hash 识别已写回，不重复追加 |
| 重试时外部编辑 | 原 before hash 保留，写回被拒绝，用户内容保持原样 |
| 任务级错误/中断 | 不自动调用模型；未完成项可显式重试 |
| SQLite 保存失败 | 不启动推理、不写 caption，释放共享 reservation，错误不回显私有路径 |
| prompt 预设删除 | 冻结提示词仍被失败项重试使用 |
| 真实 HTTP fake matrix | 429 一次后成功；401 不重试；非法 JSON 两次后失败；短 timeout 稳定错误码；部分 503 后重启重试 |
| explicit fallback report | remote 请求先于 local；显式启用后成功，报告登记实际 local profile/revision |
| Tag/natural/combined | Tag 不调用 LLM；natural 只写自然语言；组合四布局由独立 Tag 输出与 HTTP caption 合成 |
| Tag 灰度 | ignore/copy/prepend/append，已有/空/缺失 caption 逐文件逐字节一致；混合/自然语言被拒绝合并 |
| 公开报告隐私 | history/detail/report 不返回服务端目录、expected_hashes、冻结内部标记和秘密 |

## 本地 Qwen 真实批量

实际命令：同一 venv 运行 `tools/verify_managed_caption_runtime.py --batch --root <new-root> --assets <P1-models> --runtime <b11327-server> --samples <chelsea> <coffee> <rocket>`。新 root、新配置和 SQLite，模型/runtime 明确复用 P1 资产，故不具备 Phase 4 独立性。

第一次退出码 1：验证脚本错误选取第一个 text-only profile 进行最后的 vision connection test。此前批量/冲突/取消已执行，但不将该次整体命令视为通过。已修复为明确选择固定的受管视觉 asset_id，然后以另一个新 root 重跑，退出码 0。

第二次完整实测：

- 启动 3.065s；三张自然语言写回 14.803s，succeeded=3；
- 三张均满足严格 caption JSON、中文规则和写回 hash；
- RSS 峰值 3094904832 bytes，约 3.09 GB；
- 真实推理期间模拟外部修改，触发 caption_conflict，用户编辑保持不变；
- 真实 job cancel 0.026s，未覆盖现有文件；随后精确 vision connection test 通过；
- SQLite 中保留 3 个任务记录，服务已停止；没有原始响应/图片/模型/Key 写入 Git。

公开样本原始 SHA：

| 样本 | SHA256 |
| --- | --- |
| chelsea | 596aa1e7cb875eb79f437e310381d26b338a81c2da23439704a73c4651e8c4bb |
| coffee | cc02f8ca188b167c775a7101b5d767d1e71792cf762c33d6fa15a4599b5a8de7 |
| rocket | c2dd0de7c538df8d111e479619b129464d0269d0ae5fd18ca91d33a7fdfea95c |

## 完成边界

预设保存时由服务端计算 revision，包含模板/语言/max_length；调用方不能伪造 revision。字符上限 1–2000，进入冻结任务、响应 schema/解析与 cache key；前端提供上限输入和撤销，拒绝非法值。图片编码保持 EXIF orientation，明确清空其余元数据，测试验证不发送私有 EXIF。

Phase 1 的 fake/contract/gray/低限额本地真实写回已有证据；真实远程中文、真实 WD/CL 三模式、完整缓存成本/EDD/Zero-Short/浏览器人工验收和干净重建仍由后续阶段闭环。Dataset Editor 必须在 Phase 2 接入生成来源格式，防止将短自然语言误识别为 Tag；不能仅依赖文本启发式。备份已保存，安全回滚接口和清理策略仍待实现/验收，不宣称已提供完整回滚 UI。
