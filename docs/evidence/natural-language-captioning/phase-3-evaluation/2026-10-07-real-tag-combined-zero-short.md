# 真实 Tag、组合模式和正式空配置启动

生产模块基线 `776c082`；验证器随本批提交。均为 Phase3，中间环境复用现有测试依赖，不能作为 Phase4。

## 真实 ONNX

使用项目默认 `wd14-convnextv2-v2`。从 [SmilingWolf 官方仓库锁定 revision](https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2/tree/bf364499ea843a403cc2770072f31f5cfb2ffa58) 下载 model.onnx 和 selected_tags.csv，仅放 sandbox：

- model.onnx SHA256：`e91daa19cd9e8725125b7d70702d1560855fb687f8d8c4218eddaa821f41834a`。
- selected_tags.csv SHA256：`8c8750600db36233a1b274ac88bd46289e588b338218c2e4c62bbc9f2b516368`。
- Hugging Face CLI 初次直连超时；设置本地 HTTP/HTTPS 代理后成功；未改变模型版本或下载校验。
- 自动 providers 先尝试 CUDA，但测试环境缺 CUDA DLL；实际 session providers 为 CPUExecutionProvider。本次不宣称 GPU 验证。

执行 `tools/verify_caption_real_tag.py`，同一冻结三图分别运行真实旧 Tag 和新 mode=tag，3/3 caption 逐字节相同，耗时 8.366 秒；chelsea/coffee/rocket 分别为 13/11/8 个 Tag。真实 Tag 不调用 LLM，来源记录为 tag，记录输出 SHA。

执行 `tools/verify_caption_production.py --local --mode combined --tag-models <isolated-assets>`，实际 ONNX + Qwen3-VL-2B：3/3，24.208 秒；启动 3.002 秒，峰值 RSS 3,069,792,256 字节。Tag 与自然语言以空行分隔，来源记录 mixed，actualTags 与真实 Tag 行完全相同。缓存复跑 3 次命中且不请求 LLM，预览未更改 caption，本地模型已停止。此测试允许显式本地兜底，空 remote profile；真实远程优先已有独立证据。

结果保存在 workspace/sandboxes 下 `nl-caption-real-tag-20261007/report.json`、`nl-caption-real-combined-20261007/report.json`；图片、模型、数据库和完整配置不提交。组合模式的自然语言段与原 B 组 SHA 相同，人工评分只沿用这些精确文本，未新增机器评分。

## 正式 Zero-Short

Node22.17.1 从当前源码构建新 dist（1868 模块，5.98 秒），输出 `nl-caption-zero-short-20261007-dist`。通过 `tools/serve_caption_acceptance.py` 启动实际 FastAPI **lifespan=on**，仅将可写配置/queue/HF/Tag/marketplace 根指向全新 `nl-caption-zero-short-20261007`；不替换 provider、模型、词库或启动钩子。MIKAZUKI_DEV=1 仅禁止自动弹出 Windows 浏览器。

实际浏览器打开 `/dataset/tagger`，静态资源和业务 API 正常。核验：

- `/api/llm/config` 200，version5、profiles/routes/presets 为空。
- `/api/llm/local-vision/status` 200，missing、installed=false、size_bytes=0、runtime_installed=false。
- `/api/tag-translation/dictionary/status` 200，missing、installed=false、row_count=0。
- `/api/tagger/status` 200，idle。
- 无 profile 的 connection-test 502，错误码 llm_not_ready、可操作提示，无凭据或 provider envelope；浏览器 console 的唯一错误为该主动触发的预期 HTTP 502。
- 自然语言页生成/预览按钮 disabled，本地模型安装入口、共享 profile 管理、提示词/预设、隐私提示可见；本地兜底默认未勾选。共享配置解释翻译与打标能力限制和凭据重启边界。
- 390px 与 1440px 均无水平溢出；共享对话框打开/取消与 Tab 操作可用。

真实启动时检测到 CPU torch，输出已有训练 GPU 不可用提示，未阻止 WebUI。实际启动还执行版本检查，故不宣称零外网请求；未触发词库或模型安装。自建进程已停止，浏览器 about:blank。

## 完整回归失败与修复

指定 Python3.11 测试 venv 补充 diffusers0.32.2、einops0.8.1、imagesize1.4.1 后，主 tests 正常收集 1503 项。首次完整运行出现失败且在 DiffSynth fixture 扩展巨大的占位文件时停滞；已停止该测试进程，不报告为通过。py-spy 实际栈定位到 test_diffsynth_engine.py 的 truncate。

Windows 修复：按 [Microsoft FSCTL_SET_SPARSE 说明](https://learn.microsoft.com/windows/win32/api/winioctl/ni-winioctl-fsctl_set_sparse) 设置稀疏标志，再 seek 至最后一个字节并写零；Windows CRT truncate 会填充间隙，单独 sparse 标志不足。原有 shape/header/offset/逻辑长度与断言均保留，无假通过或跳过。修复后该组 13 passed / 4 warnings / 2.80 秒。完整矩阵重新运行中，Windows symlink 等失败未豁免。

自动审批审查拒绝删除首次生成的临时模型目录，理由只有 blocked by policy。该目录保留，未复用；此清理未完成，最终需核销。

## 矩阵后续复验

完整分区运行：1467 passed / 11 failed / 25 skipped / 1 deselected / 77 subtests，308.42 秒。唯一 deselected 是实际尝试后卡在整仓模型下载的 ModelScope tokenizer 测试；此时不计为通过。11 failed 中6个来自 test_task_maintenance_api.py 在收集阶段向 sys.modules 泄漏 Tagger 替身，1个来自 GUI-only 环境没有可选 LyCORIS 工厂属性，另4个仍为 WinError1314。

移除测试全局替身泄漏，并仅向 LyCORIS 单元测试注入 fake 工厂（create=True），保留原有逐权重/倍率/merge 断言。灰度测试补充终态和总图片数断言，避免任务级失败计数为零导致误读。相关五文件55 passed / 4 warnings / 7.50秒；全分区再次复验中。

ModelScope 测试根据已安装 patcher 的 allow_file_pattern 参数，仅真实下载 tokenizer 的 JSON/TXT 文件，继续调用实际 patched CLIPTokenizer.from_pretrained 并验证 vocab_size=49408。代理下 `python -m pytest tests/test_china_hub.py -q -ra -o faulthandler_timeout=90` 实际7 passed / 7.39秒，关闭该单项资源问题；并未把真实测试改成假 tokenizer 或跳过。完整组合运行尚待最终复验。

最新分区复验命令：`python -m pytest tests -q -ra -o faulthandler_timeout=90 -k "not test_enable_china_hub_patches_transformers_download"`，实际1474 passed / 4 failed / 25 skipped / 1 deselected / 4 warnings / 77 subtests / 306.54秒。4个失败均为原Windows符号链接权限场景，未豁免；排除项已在独立真实7项组中通过，但仍需完整组合复验。所有自建进程已结束，整体验收未完成。
