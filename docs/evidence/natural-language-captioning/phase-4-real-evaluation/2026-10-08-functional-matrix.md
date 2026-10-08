# Issue #409 功能范围完整回归矩阵

2026-10-08，业务源码6829ec8。新增tools/run_caption_scope_tests.py将当前用户授权范围固化为可复跑的测试集合：Caption、统一LLM、Tagger、翻译、数据集/编辑器、Tasks、日志、配置导入导出、SPA入口和训练数据集配置兼容，共51文件。Agent、sidecar、plugin及训练引擎内部实现遵循用户明确收敛的范围，不属于本版完成门，不能将其记录为通过。

实际运行506 passed / 4 failed / 0 skipped / 17 subtests passed / 42.46秒，完整集合和逐文件SHA在私有sandbox的scope.json，junit.xml及pytest.log记录实际失败。

失败均为Windows原生symlink创建权限，未进入功能断言：

- tests/test_datasets_api.py::test_list_datasets_excludes_symlinked_directories
- tests/test_datasets_api.py::test_resolve_dataset_dir_rejects_symlink_escape
- tests/test_datasets_export.py::test_zip_export_skips_symlinked_files
- tests/test_datasets_export.py::test_zip_export_skips_symlinked_directories

状态仍fail/环境权限阻塞；不自动豁免、不用junction替换、不将本次返回码1记作通过。正在准备独立WSL/Python3.11环境运行这四个原始case，以补充真实POSIX symlink证据；这不会把Windows失败改写为Windows通过，也不是Phase5从零重建。

补充实际结果：独立Linux/Python3.11.15、干净6829ec8源码及新venv中，四个原始case使用真实POSIX symlink全部通过，未改测试。最初因libGL.so.1缺失无法collection，改用相同4.8.1.78版本的原生opencv-python-headless（仅此venv）后4 passed，退出码0。Python安装包SHA 171dffd8c0f66e8a0725364a7428015b22fc18dd298b24f541392e17dd0e561f；headless wheel从PyPI下载并验证其发布SHA。Windows原运行仍4失败，已向用户请求“启用开发者模式复验”或“批准这四项跨平台组合覆盖”的验收选择，尚未收到决定。

f53582e修复提交后重新运行同一完整选择集合：51文件/513 case（新增三个取消/归档恢复case），509 passed/4相同Windows权限失败/0skip；无新增失败。source_commit与每个测试文件SHA均由runner记录，未用此前子集结果代替。最终环境口径仍待用户决定。

相关后端子集299通过、前端341/52完整check通过、真实ONNX/本地Qwen和正式lifespan Zero-Short通过，见2026-10-08-current-tag-local-zero.md。整体goal仍active，最终测试和全新隔离重建未闭环。
