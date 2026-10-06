# P1 视觉模型可行性探针报告

## 元数据

- Plan ID: DATASET-NL-TAGGING-20261006
- Probe ID: NL-CAPTION-P1-20261006
- Date: 2026-10-06 Asia/Shanghai
- Isolated worktree: E:\OpenSourceTeamWork\workspace\sandboxes\nl-caption-p1-20261006
- Source commit: fc193789c46f6724bfcc92e203644ba3f77db995
- Probe script: script/ops/vision_probe.py
- Credential persistence: false；API Key 从标准输入传入，未写入脚本、报告或环境文件
- Sample source: scikit-image v0.19.3 official sample assets: chelsea.png, coffee.png, rocket.jpg

## 硬件和运行约束

- CPU: Intel Core i5-12600KF，10 核 / 16 线程
- Memory: 32 GiB
- GPU: NVIDIA GeForce RTX 4060 Ti，16 GiB；本地探针强制 CPU-only
- llama.cpp runtime: release b11327
- Runtime archive: llama-b11327-bin-win-cpu-x64.zip
- Runtime size: 19,275,534 B
- Runtime SHA-256: 4ac11772e7f9a313346ff2f4212b0608dd181130df81b9070cef377102faba8f
- Local server parameters: -t 4 -tb 4 -ngl 0 --no-mmproj-offload --parallel 1 --slots -c 4096

## 候选模型资产

### 选定探针模型：SmolVLM-256M-Instruct Q8_0

| 资产 | 来源 revision | 大小 | SHA-256 |
| --- | --- | ---: | --- |
| SmolVLM-256M-Instruct-Q8_0.gguf | ggml-org/SmolVLM-256M-Instruct-GGUF@b9e4379657e1450d04d02eec8e345667265b0a00 | 175,054,528 B | 2a31195d3769c0b0fd0a4906201666108834848db768af11de1d2cef7cd35e65 |
| mmproj-SmolVLM-256M-Instruct-Q8_0.gguf | 同上 | 103,769,856 B | 7e943f7c53f0382a6fc41b6ee0c2def63ba4fded9ab8ed039cc9e2ab905e0edd |

总模型资产约 279 MiB。官方模型卡说明它是图文多模态模型，可用于 image captioning；GGUF 页面提供 llama.cpp server 启动方式。[SmolVLM-256M 模型卡](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct)、[SmolVLM-256M GGUF](https://huggingface.co/ggml-org/SmolVLM-256M-Instruct-GGUF)

### 备选模型：SmolVLM-500M-Instruct Q8_0

| 资产 | revision | 大小 | SHA-256 |
| --- | --- | ---: | --- |
| SmolVLM-500M-Instruct-Q8_0.gguf | ggml-org/SmolVLM-500M-Instruct-GGUF@72e986006ef53e37cdd3f6d4241c90b0f01df376 | 436,806,912 B | 9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4 |
| mmproj-SmolVLM-500M-Instruct-Q8_0.gguf | 同上 | 108,783,360 B | d1eb8b6b23979205fdf63703ed10f788131a3f812c7b1f72e0119d5d81295150 |

500M 模型本体下载过程中发生一次远端连接中断，临时文件未被当作有效资产使用，本轮没有启动 500M 服务。官方资料显示 500M 版本约需 1.23 GB GPU RAM，适合后续作为质量升级选项，而不是个人电脑的默认下载项。[SmolVLM-500M 模型卡](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct)

## 本地 CPU 结果

服务启动成功：

- health ready: 1.394 s
- idle RSS: 386,707,456 B（约 369 MiB）
- peak RSS: 473,128,960 B（约 451 MiB）
- peak private bytes: 560,209,920 B（约 534 MiB）
- measured process CPU time: 51.27 s
- shutdown: 0.039 s
- process stopped: true

三张图片均返回 HTTP 200、严格 JSON 和 finish_reason=stop：

| 样本 | 语言 | 延迟 | 结果 |
| --- | --- | ---: | --- |
| chelsea.png | English | 2.635 s | cat's eyes are green and yellow, the nose is orange, and the ears are pink. |
| coffee.png | English | 2.642 s | red |
| rocket.jpg | English | 2.465 s | a space rocket |

结构化输出约束有效。移除 response_format 后模型仍能返回文本，但不是严格 JSON，后端必须保留 schema 校验。

### 中文能力结论

向本地模型发送 language=zh-CN 后，返回值为：

    {"caption":"he looks like a cat","language":"zh-CN"}

它没有产生中文字符，因此本地 256M 模型可以作为低资源视觉连通性、英文 caption 或无网络兜底模型，不能作为当前项目的中文自然语言打标推荐模型。UI 应显示模型支持语言，并在中文模式下给出降级提示。

### 本地取消结果

- 流式请求收到首个内容：2.277 s
- 客户端取消读取：成功
- 取消后的客户端任务状态：已取消
- 取消后重新请求：HTTP 200、严格 JSON、0.661 s
- 本地 slot 在约 0.233 s 内恢复空闲
- llama.cpp 日志显示任务释放和 stop processing

## SiliconFlow 远程结果

配置：

- Endpoint: https://api.siliconflow.cn/v1/chat/completions
- Model: Qwen/Qwen3.6-27B
- 请求类型：OpenAI-compatible vision chat completion
- 图片传输：JPEG data URL，未发送本地路径
- response_format: JSON schema
- temperature: 0
- enable_thinking: false

SiliconFlow 文档明确支持 Bearer Authorization、VLM 消息、image_url 内容、JSON Schema 和 JSON Object 响应格式。[SiliconFlow Chat Completions API](https://api-docs.siliconflow.cn/docs/api/chat-completions-post)

| 样本 | HTTP | 延迟 | 严格 JSON | 中文结果摘要 |
| --- | ---: | ---: | --- | --- |
| chelsea.png | 200 | 3.472 s | 是 | 棕色虎斑猫脸部特写、绿色眼睛、粉色鼻子 |
| coffee.png | 200 | 5.668 s | 是 | 红褐色碟子上的咖啡和勺子 |
| rocket.jpg | 200 | 1.986 s | 是 | 夜幕下白色火箭、发射台、金属塔架和灯光 |

三次请求总 token 分别为 227、273、279；trace id 已记录在隔离探针原始报告中，便于服务端排查。API Key 没有写入原始 JSON 报告，探针结束后也没有保存到工作区。

### 远程取消结果

- 流式请求首个内容：0.818 s
- 客户端取消任务：成功
- 取消读取延迟：0.0002 s
- 已收到流式片段：5
- 取消后新请求：HTTP 200、严格 JSON、1.931 s
- 上游推理是否在客户端断开后立即停止：API 外部不可观测，产品报告应标记为 upstream_compute_stop=unknown

## 结论与决策

### P1 门禁结论：pass-with-boundary

通过项：

- 本地视觉服务可在 Windows CPU-only 环境启动；
- 本地模型和 mmproj 可以通过统一 llama.cpp OpenAI-compatible server 提供视觉请求；
- 本地三张样本全部返回可解析 JSON；
- 本地峰值内存约 534 MiB private bytes，适合普通个人电脑的低资源安装档；
- SiliconFlow Qwen3.6-27B 三张中文图片全部返回严格 JSON；
- data URL、取消、取消后恢复请求路径均可验证；
- JSON schema 对远程和本地请求均有价值，不能取消。
- Qwen3-VL-2B 本地 CPU-only 能生成中文严格 JSON，已达到中文本地兜底候选门槛。

边界：

- SmolVLM-256M 主要支持 English；不作为中文默认模型；
- Qwen3-VL-2B 的 CPU 延迟和约 3.1 GB 峰值内存需要在 UI 中明确展示；
- Qwen2.5-VL-3B 本轮不再优先探测，除非 Qwen3-VL-2B 在真实动漫数据集上的质量不足；
- 本探针没有评估动漫人物、复杂多人构图和训练 caption 质量；
- 远程 API 上游取消成本不可观测；
- 当前测试使用通用样本，不能替代项目真实数据集评测。

### 推荐默认策略

1. 远程中文 profile：使用用户提供的 SiliconFlow Qwen3.6-27B，初始配置 temperature=0、enable_thinking=false、JSON Schema、单图串行或低并发。
2. 本地中文兜底：登记 Qwen3-VL-2B Q4_K_M + Q8 mmproj，标记约 1.55 GB 下载、约 3.1 GB 峰值内存和 CPU 慢速；
3. 本地低资源选项：保留 SmolVLM-256M 作为英文/低资源 profile，不宣称中文质量；
4. 产品接口：profile 必须声明 capabilities 和 languages；选择 zh-CN 时优先远程 profile，只有 Qwen3-VL-2B 等声明中文能力的本地 profile 才可作为兜底。

## Qwen3-VL-2B 本地补充探针

应用户偏好，补充探测 Qwen3-VL-2B Instruct Q4_K_M。官方 GGUF 组合为：

| 资产 | 来源 revision | 大小 | SHA-256 |
| --- | --- | ---: | --- |
| Qwen3VL-2B-Instruct-Q4_K_M.gguf | Qwen/Qwen3-VL-2B-Instruct-GGUF@52d6c8ffea26cc873ac5ad116f8631268d7eb503 | 1,107,409,952 B | 089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae |
| mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf | 同上 | 445,053,216 B | f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82 |

总资产约 1.55 GB。CPU-only 结果：启动 health ready 为 2.889 s，idle RSS 为 2,772,779,008 B，peak RSS 为 3,097,571,328 B，CPU process time 为 97.88 s。

三张样本均返回严格 JSON 和中文 caption：

| 样本 | 延迟 | 结果 |
| --- | ---: | --- |
| chelsea.png | 4.565 s | 猫脸特写、明亮的黄绿色眼睛 |
| coffee.png | 6.767 s | 红色碟子中的咖啡和勺子 |
| rocket.jpg | 7.296 s | 夜幕下发射台上的白色火箭和金属支架 |

流式取消测试中，首个内容约 5.96 s，收到 3 个 chunk 后关闭读取耗时约 0.0436 s；取消后的恢复请求 HTTP 200，约 1.952 s。终端显示的替换字符是 Windows 控制台编码现象，保存的 JSON code point 已确认是有效中文字符。

Qwen3-VL-2B 满足本地中文 caption 的最低可行性要求，质量和语言能力优于 SmolVLM-256M，但需要约 3.1 GB 峰值内存和较长 CPU 延迟。它应作为本地中文兜底候选；默认远程 profile 仍优先。[Qwen3-VL 官方仓库](https://github.com/QwenLM/Qwen3-VL)、[Qwen3-VL-2B GGUF](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF)

## 证据路径与清理

原始结果位于隔离目录：

- .sandbox-data/vision-probe/local-256M.json
- .sandbox-data/vision-probe/remote.json
- .sandbox-logs/server-256M.log
- .sandbox-data/vision-probe/models/
- .sandbox-data/vision-probe/runtime/

这些文件不应进入 Git。报告只保留模型元数据、hash、统计和错误摘要；远程 API 原始报告不复制到公开仓库。完成评审后，按工作区脚本删除 sandboxes/nl-caption-p1-20261006，同时清理本地模型和运行时资产。

## 后续动作

更新主设计书 P1 状态为 done with boundary，进入 P2：实现统一 LLM facade、profile capability/language 字段和 fake OpenAI-compatible vision contract，并落实“远程优先、本地兜底”路由后，再把 SiliconFlow 和 Qwen3-VL-2B profile 接入 TaggerPage。
