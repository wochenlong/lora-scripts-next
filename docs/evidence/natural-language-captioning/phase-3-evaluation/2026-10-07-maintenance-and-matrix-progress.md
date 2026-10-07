# Phase3 安全维护与完整矩阵进度

基线2cdb77f；Phase2完成门已逐项核销，Phase3 in progress，Phase4 pending。

## 新契约/实现及授权

完整goal和Phase3任务书要求回滚/清理；本批沿用同一SQLite，新增caption_formats.writer_job_id、caption_backups.format_detail和caption_rollbacks prepared/done记录，兼容旧表升级。新增POST /api/tagger/jobs/{id}/rollback与DELETE /api/tagger/jobs/{id}。这是计划内可逆实现，不改变remote-first、Key策略或LLM/Tag分工。

- 回滚仅处理实际written项，使用私有原始字节/格式/Tags/原写入者备份；核对after hash与当前writer，后续任务相同内容也不能被旧任务撤销。
- tmp/fsync/replace保留原始字节，包括CRLF；写前和提交前再核owner/hash，备份SHA损坏拒绝恢复。prepared状态使写回后DB元信息失败可以继续恢复；重复回滚幂等。
- 原不存在caption则删除本任务创建且未被改写的文件。图像/路径变化、符号链接/junction、旧缺安全格式的备份跳过，不猜来源。
- 训练占用/全局任务忙时阻止维护。DELETE仅删除job/backups/rollback记录，保留caption和format provenance；页面显式确认后才执行，说明不可再用此记录回滚。
- 前端展示restored/conflicts/skipped和逐项状态；不把备份内容、私有计划或绝对路径返回给前端。private计划保存绝对路径和对应hash map避免cwd改变。

## 实际验证

后端maintenance新增12场景，覆盖字节/格式恢复、删除新建、外部冲突、后来相同字节writer、倒序回滚、幂等、清理不删来源、prepared中断恢复、DB错误、忙状态、备份损坏、写后owner重核、API脱敏。最新相关完整suite241 passed/4 warnings/20.75s；随后维护progress归终态的定向17 passed。

Node22 check最终329 tests/51files/13.92s、typecheck/lint/build通过（2个已有warning），build1868/5.58s。首次两个TS2345是ElementPlus确认框返回类型声明MessageBoxInputData & Action；改为spy的mockImplementation并用真实浏览器确认/取消复验。没有削弱生产类型；失败不可计通过。

actual Vue/API + fake LLM浏览器根nl-caption-maintenance-browser-20261007：先自然3图完成，外部改第1个文件；取消回滚确认框仍3文件。再次确认，UI restored2/conflicts1/skipped0，两个初始无caption的文件被移除，外部第1文件保持。确认清历史后state idle/history0/backups0，caption与1条format来源仍保留。console0errors。不是真实模型/正式启动/Phase4；两个服务已停止、about:blank。

命令：Python3.11独立venv运行test_caption_maintenance、test_caption_http_contract、test_cli_entrypoints；完整相关套件是test_llm*/test_caption*/test_tag_translation*/test_tagger*及vision/local managers/dataset safety/in-use。前端使用Node22.17.1 npm --prefix frontend run check。

## 完整矩阵失败已实际复现

8个文件定向组合：11 failed /69 passed /5 skipped /356.73s。随后--lf保存脱敏逐用例日志，11 failed/35 deselected/4.06s，位于独立eval sandbox/logs/reproduced-11-failures.txt，不把stderr原路径入Git。

| 类别 | 具体用例 | 状态 |
|---|---|---|
| Anima缺torch | test_rewrite_config_file_ignores_missing_config_arg、test_rewrite_config_file_writes_adapted_config、test_wrapper_script_launch_shape_can_import_local_package | 安装CPU torch2.7.0/torchvision0.22.0后重验 |
| ChinaHub缺transformers | test_smilingwolf_download_bypasses_modelscope_patch、test_enable_china_hub_patches_transformers_download | 安装transformers4.51.3后重验 |
| README缺CLI入口 | test_readme_and_cli_docs_explain_anima_cli_entrypoints | 修复两README说明，CLI5项通过 |
| process stub依赖 | test_launch_stubs_do_not_break_anima_fast_import | 安装训练测试依赖后重验 |
| Windows符号链接权限 | test_list_datasets_excludes_symlinked_directories、test_resolve_dataset_dir_rejects_symlink_escape、test_zip_export_skips_symlinked_files、test_zip_export_skips_symlinked_directories | 实际WinError1314，等待权限环境 |

当前进程Administrator=false/未检出DeveloperMode；已通过异步问题请求用户启用开发者模式或提供有权限Windows环境，依据完整goal不得直接skip。等待期间继续其他工作；不标整体blocked或通过。微软说明：https://blogs.windows.com/windowsdeveloper/2016/12/02/symlinks-windows-10/ 。

依赖仅装到已有独立测试venv，不把torch加到GUI requirements：uv pip install --python <runtimepython> torch==2.7.0+cpu torchvision==0.22.0+cpu --index-url https://download.pytorch.org/whl/cpu；随后transformers==4.51.3 accelerate==0.33.0 safetensors（实际0.8.0）。pip不可用的初次命令退出1，改用原环境uv后成功。hardlink跨盘降级copy为工具提示，不是验收失败。后续完整训练collection和适用矩阵仍须闭环。

## 待办

真实current remote/local/ONNX、EDD人工评分、正式Zero-Short、完整矩阵剩余失败和Phase4从零重建未完成。冻结样本源URL字节和3个SHA实际核对，评分仍null；当前官方SiliconFlow支持json_schema，不以文档代替生产adapter测试。单一下一步：完成依赖补齐后的失败回归复验并记录结果，然后真实current路径。

## 依赖补齐后复验

最终Python3.11运行test_anima_train_wrapper.py、test_china_hub.py、test_cli_entrypoints.py、test_process_stub_isolation.py：17 passed /215.59s，退出0。关闭原11项中的7项（3 Anima、2 ChinaHub、1 README、1 process）。剩余4个Windows symlink仍需权限环境；另此前5 skipped/整体21 skipped和根训练collection尚须逐项审计，未获豁免。当前所有测试handle已结束。下一步：真实current adapter验收与完整矩阵继续闭环。
