# 自然语言功能回归与验收口径

## 可复现命令

后端必须使用产品支持的 Python 3.10；另用 3.11 检查跨版本取消行为。先安装 GUI 依赖，不需要安装训练引擎或下载模型：

```sh
python --version
python -m pip install -r requirements.txt pytest
python tools/run_caption_scope_tests.py --root caption-test-results
```

报告目录必须不存在。`scope.json` 记录实际解释器、源提交和每个测试文件的 SHA256；`pytest.log`、`junit.xml` 和 `report.json` 记录真实结果。范围包括 Caption、共享 LLM、两种翻译、数据集编辑、任务衔接、词库打包和对应公共入口。用例数随源码变化，以报告为准；不要把新增测试函数数、参数化用例数、不同批次的专项数相加当成全仓结果。

runner 将断言失败、收集错误和意外跳过判为失败。Windows 缺少符号链接权限时，只允许明确的权限原因跳过；Linux CI 仍执行这些路径保护用例。任务曲线测试直接写入真实 TensorBoard 标量事件，不依赖训练引擎的 PyTorch。

Linux 上不适用的 Windows junction、robocopy 打包操作按测试模块和明确原因列入环境跳过，不能用同样的理由跳过其他功能测试；Windows job 必须执行它们。报告保留全部跳过项，不将其计入通过数。

前端必须使用 Node 22.17.1，在 `frontend` 目录运行：

```sh
npm ci
npm run check
```

`.github/workflows/dataset-caption.yml` 运行 Windows/Linux Python 3.10、Linux Python 3.11 后端，以及 Node 22 前端完整检查，保留后端报告附件。原有 Portable 检查只覆盖打包相关测试，不能替代本功能 CI。

## 取消行为专项

`test_caption_translation_parameters.py` 覆盖运行和排队取消、吞掉取消后迟到返回、迟到异常、重复取消、有界清理、并发槽和缓存保护。provider 使用独立子任务；取消的显示请求不会解析或缓存子任务的迟到结果。清理等待有上限，底层 provider 若尚未退出，会继续占用并发槽直到实际完成，避免超额请求。此行为兼容 Python 3.10，不依赖 `Task.cancelling()`。

`test_caption_translation_disconnect.py` 启动真实 Uvicorn HTTP 服务，经过三层 Starlette HTTP 中间件，关闭 TCP 连接并验证 provider 取消及缓存不回填。接口在请求体解析后独立等待 ASGI 的 `http.disconnect` 消息，避免即时轮询 `is_disconnected()` 在中间件流中漏检断连。

## 历史数字和人工评分边界

PR 初版提到的“后端 614 项”来自本地选择的 51 个测试文件，使用 Python 3.11，而非 Python 3.10 整合包验收，也不是当前 runner 的完整范围。该结果不能证明产品解释器兼容性；本次修复以重新运行的 Python 3.10 报告为准。

“8 条 Caption 五维全 4 分”来自提交者在本轮对话中的人工确认：R1–R4/L1–L4 全部 4 分，并确认共同理由及中文短路判定。原图、生成样本和对话属于本地验收资料，没有随仓库发布；维护者无法仅从仓库独立复核这项质量结论。因此它是提交者提供的历史人工验收信息，不是 CI 结果，也不作为取消兼容性修复的验证证据。

`tools/verify_caption_production.py` 的 `human_scores: None` 表示该工具不生成或冒充人工评分；只有实际审核记录才能补充人工结论。新沙盒复测必须分别注明真实模型请求和注入故障，记录版本、命令、源哈希、缓存及文件保护结果，不上传密钥或私人运行数据。
