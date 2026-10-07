# Phase 2：翻译选项兼容与保存验收

基线25e954b，阶段in progress。

## 修复和契约

共享LLM UI补回标签翻译system prompt（系统提示词）和reasoning effort（推理强度）。字段存profile.metadata，后端严格校验字符串/20000上限与disabled/high/max枚举；caption提示词预设保持独立。v4迁移保留旧选项，共享配置和旧translation API双向同步，更新翻译选项改变翻译profile revision。受管模型固定关闭推理；视觉和纯文本受管模型重启保留用户名称、禁用状态和翻译metadata。

Dataset Editor batch/undo/redo遇失败后刷新历史，使后台成功部分的事务能在UI撤销；不覆盖原错误提示。

## 实际命令及结果

```powershell
& <runtime-python3.11.15> -m pytest tests/test_llm_translation_gray.py tests/test_tag_translation_config.py -q
& <runtime-python3.11.15> -m pytest (Get-ChildItem tests/test_llm*.py,tests/test_caption_*.py,tests/test_tag_translation_*.py,tests/test_tagger_*.py | Select-Object -ExpandProperty FullName) tests/test_vision_service.py tests/test_local_vision_manager.py tests/test_local_text_registry.py tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_datasets_inuse_guard.py -q
npm exec --yes --package=node@22.17.1 -- node 'I:\NdoeJS\node_modules\npm\bin\npm-cli.js' --prefix frontend run check
```

- 定向旧配置/翻译12 passed；最终相关后端226 passed / 4 warnings / 20.26s。
- 最终Node22：51 files / 325 tests passed / 20.56s；typecheck/lint/build通过（lint2个已有warning），build1868 modules / 8.24s。此前TS2322失败及修复见独立failure record；不能把组件测试等同于静态检查。
- 新增metadata非法类型、双向保存/迁移/revision、模型重启保留设置，以及共享组件编辑选项的测试。

## 实际浏览器

使用fresh fake fixture -r3（合成图片/无真实模型/无Key/词库及MyMemory替身/lifespan=off），Vue5177/API28762/provider18762。

- 实际保存纯文本profile翻译提示词与high推理；新增remote纯文本profile，取消其vision能力并保存，后端profile数3且新capabilities仅text；Tagger仍只显示1个vision选项。
- 修改提示词、删除新profile后点击取消，再打开：profile数仍3且原提示词恢复。再次删除并保存：profile数2；translation route设为fixture-text；旧API返回deepseek.reasoning_effort=high和自定义提示词。
- 选en时fixture没有支持en的vision profile，eligibleProfiles=0且启动按钮disabled；切回zh-CN恢复。
- 390px窄屏，新选项dialog宽374.39、scrollWidth374，document scrollWidth390；重新打开字段保持已保存值；Escape关闭。
- 本次导航console errors0/warnings0，只有Chromium password-not-in-form的verbose提示。fixture未包含真实凭据。
- -r3后端/Vite已停止，浏览器已转about:blank；tracked dist恢复基线，fixture config/SQLite/样本不入Git。

## 尚待完成

真实重启的恢复界面、历史选择和键盘/完整错误矩阵仍需补验；安全任务回滚/清理；Phase3真实模型/EDD/完整回归失败闭环/正式Zero-Short和Phase4隔离从零重建。不可将本报告标记为完整验收。
