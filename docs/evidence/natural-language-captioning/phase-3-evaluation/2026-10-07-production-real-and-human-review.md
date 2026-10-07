# 生产链路真实模型与人工评测

## 范围与结论

生产模块源码基线为 `776c082`。实际执行 `tools/verify_caption_production.py`，使用冻结的三张公开图片，调用 UnifiedLLMService、CaptionJobManager、CaptionCache、原子写回和来源记录。该验证属于 Phase 3；本地模型复用 P1 锁定资产，不属于从零重建。

| 路径 | 三图写回 | 批量耗时 | 本地峰值 RSS | 额外验证 |
| --- | --- | --- | --- | --- |
| SiliconFlow Qwen/Qwen3.6-27B | 3/3 | 41.700 秒 | 无本地推理 | 严格 JSON、缓存 3 次命中且零请求、预览不写盘 |
| Qwen3-VL-2B Q4_K_M + Q8 mmproj，修正后的隔离 root | 3/3 | 13.894 秒 | 3,070,423,040 字节 | 启动 2.952 秒；同上；结束停止模型 |
| 远程与本地同时可用 | 3/3，全部远程 | 53.561 秒 | 2,896,371,712 字节 | 远程优先；关闭兜底时失败；显式兜底时真实本地成功 |

请求预算为每次验证最多 8 次、每次 90 秒、最多 512 输出 token。远程单组实际 4 次，路由组 7 次（其中两次为受控失败）。所有图片请求检查为受限 JPEG data URL，提示词不含公开样本文件名。凭据通过后端终端隐藏输入，配置掩码并检查真实 Key 未落盘；报告仅保留处理后描述的哈希和规则结果，不保存原始响应。

路由故障使用仅回环的 401 服务，未将真实 Key 发往该服务。这证明客户端故障路由，不代表远程供应商实际宕机。远程可用且本地已启动时，三图都由远程生成。

## 人工验收

评审包中的 A 组为最初远程结果，B 组为最初本地结果。当前用户回复“全部部合格。”及“4分 all”；六条描述的主体、可见事实、中文、训练效用、精简五维均为 4 分，各条总分 20/20，各组平均 20/20。满足冻结阈值（组平均至少 16，主体和可见事实每条至少 3），未调整 rubric。

精确描述 SHA 和用户原话见 [human-evaluation-approval.json](human-evaluation-approval.json)。本地修正隔离后的三条描述与 B 组文本 SHA 相同。后续路由验证生成了不同文本，仅用于机械路由验收，未将本次评分扩展到这些文本。用户未提供逐项理由，记录保留这一事实。

## 执行与证据定位

以下 root 均位于工作区 `workspace/sandboxes/`，未提交图片、配置、数据库、模型和原始响应：

- `nl-caption-production-remote-20261007/report.json`、`captions-for-review.json`：A 组。
- `nl-caption-production-local-20261007/report.json`、`captions-for-review.json`：B 组。
- `nl-caption-production-local-20261007-r3/report.json`：修正导入隔离后重新验证。
- `nl-caption-production-routing-20261007/report.json`：同时启动远程与本地后的路由验证。
- `nl-caption-eval-20261007/human-review.md`：人工评审包。

实际命令结构（Python 3.11 隔离环境；凭据不出现在命令中）：

```powershell
python tools/verify_caption_production.py --root <fresh-root> --samples <frozen-samples> --manifest docs/evidence/natural-language-captioning/phase-3-evaluation/frozen-eval-manifest.json --commit 776c082 --remote
python tools/verify_caption_production.py --root <fresh-root> --samples <frozen-samples> --manifest docs/evidence/natural-language-captioning/phase-3-evaluation/frozen-eval-manifest.json --commit 776c082 --local --assets <locked-probe-assets> --runtime <locked-runtime>
python tools/verify_caption_production.py --root <fresh-root> --samples <frozen-samples> --manifest docs/evidence/natural-language-captioning/phase-3-evaluation/frozen-eval-manifest.json --commit 776c082 --remote --local --assets <locked-probe-assets> --runtime <locked-runtime>
```

## 失败记录与边界

初次非交互输入在读取凭据时 EOF，未进行模型请求。验证器改为必须交互终端且使用 getpass，实际确认输入不回显。

本地 r2 在导入生产单例后重复创建 root，引发 FileExistsError，尚未启动模型。已把隔离环境变量移到生产导入之前，并容许生产导入创建 root；全新 r3 验证通过，未复用失败 root 的配置或数据库。

尚未完成真实 ONNX Tag/组合模式、正式 lifespan 空配置启动、完整测试矩阵、发布/隐私收尾和 Phase 4 全新重建。人工评分通过不能代替这些门禁。
