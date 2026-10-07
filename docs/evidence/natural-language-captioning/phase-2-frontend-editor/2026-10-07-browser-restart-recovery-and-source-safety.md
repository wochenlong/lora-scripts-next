# Phase2：实际重启恢复与来源安全

基线3b369e8；本批独立fake fixture root为workspace/sandboxes/nl-caption-browser-recovery-20261007，Vue5177/FastAPI28762/fake provider18762。lifespan=off、模型/Tag/词库/网络翻译均为替身，不是Phase4或真实模型质量验收。

## 实际行为

- fixture新增--resume，只允许本工具标记的root，并拒绝真实endpoint或真实凭据；fresh root仍拒绝已有目录，恢复时不覆盖图片/config。
- 创建三图未完成任务后停止实际Python后端，再同root恢复。恢复状态error/recovered=true/failed3；新的fake provider requests=0，caption files=0，没有自动推理或写回。
- 浏览器natural页面显示中断/恢复提示及重试按钮。点击retry创建parent关联新任务，total3/succeeded3，实际写出3个文件。
- 刷新历史并选择原job，报告显示原job的3个interrupted项。发现缺code时原因隐藏，修复后同一旧报告中文原因可见。新增code会存入SQLite，新旧报告均兼容。
- 对已生成natural样本外部改为短词和CRLF：API scan为unknown/tags[]、字节原样；原前端错误地显示Tag芯片，现已遵循来源保护并显示禁清理提示，无删除按钮。
- 通过实际保存接口把另一natural caption改为“猫”，格式仍natural；浏览器重新加载后仍禁Tag清理、排序、拖拽和批量操作；过滤/翻译标签不再从自然短句生成。
- 为无caption图片批量新增Tag保留旧功能，写回明确记录tag格式；存在unknown/natural/mixed仍不可Tag批量修改。

## 命令与结果

```powershell
& <runtime-python3.11.15> tools/serve_caption_browser_fixture.py --root <new-recovery-root>
& <runtime-python3.11.15> tools/serve_caption_browser_fixture.py --root <same-recovery-root> --resume
& <runtime-python3.11.15> -m pytest tests/test_caption_durable_jobs.py tests/test_caption_http_contract.py -q
& <runtime-python3.11.15> -m pytest tests/test_dataset_caption_provenance.py tests/test_dataset_caption_format.py tests/test_dataset_editor_api.py tests/test_caption_durable_jobs.py tests/test_caption_tag_gray.py -q
& <runtime-python3.11.15> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_local_text_registry.py tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
npm exec --yes --package=node@22.17.1 -- node 'I:\NdoeJS\node_modules\npm\bin\npm-cli.js' --prefix frontend run check
```

最终相关后端229 passed/4 warnings/22.53s；Node22 typecheck/lint/build通过，328 tests/51 files/13.11s，build1868 modules/5.34s。两项已有Lint warning。失败和修复见同目录recovery-and-provenance-failure-resolved记录。

## 清理和边界

fixture配置/SQLite/合成图片/状态文件均在sandbox，不入Git。所有本轮dev服务已停止，浏览器转about:blank；tracked dist恢复基线。未执行正式lifespan启动、真实remote/LLM/ONNX评测或从零依赖/模型重建。无来源的历史短词仍存在Tag/natural语义歧义；本批保证已生成来源不会因外部修改或前端启发式而失去安全保护。Phase2待完成门审计，Phase3/4及宽范围11失败/21跳过仍待执行/修复。
