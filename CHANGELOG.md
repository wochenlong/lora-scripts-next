# 更新日志

本文件记录 **wochenlong/lora-scripts-next** 面向镜像与 AutoDL 的发行说明；上游 kohya-ss/sd-scripts 的变更请见其仓库。

---

## v2.1 — 2026-05-09

### 训练与启动（必看）

- **AutoDL 共享盘 hash 命名 `.safetensors`**：修复通过软链指向无后缀哈希路径时，训练脚本误判为 ckpt 并 `torch.load` 导致 `_pickle.UnpicklingError` / PyTorch 2.6+ `weights_only` 报错。覆盖 SDXL / SD 1.x 训练与 `gen_img` 推理路径（stable + dev）。
- **传统 `.ckpt`（pickle）**：`torch.load` 显式 `weights_only=False`，兼容 PyTorch 2.6+。
- **xformers 缺失环境**：`apply_lora_next_anima_defaults.py` 在启动时探测 `xformers`，自动改写 `mikazuki/schema/shared.ts` 默认项（缺则关 xformers、开 SDPA），避免 WebUI 默认勾选后训练即崩。

### 训练监控页（端口 6008）

- **Loss 趋势图**：参考 Weights & Biases 风格——16:10 比例、`preserveAspectRatio` 保持比例、网格与坐标轴刻度、100% 基线强调、曲线末端数值标注。
- **指标侧栏**：当前 / 最低（含 step 提示）/ 初始 / 累计下降 / 最近 Δ（着色）/ 趋势 pill；与曲线底部对齐，宽屏下主体仍为左侧曲线。
- **响应式**：窄屏（约 820px 以下）单列堆叠。

### 运维文档（姊妹仓库）

- **Cloud-All-in-one**：`lora-scripts-next-maintenance` skill 与 `lora-scripts-next.toml` 增补「AutoDL 共享盘兼容性补丁」说明，便于拉上游后回归检查。

---

## 更早版本

未在此文件逐条归档的变更，请使用 `git log` 查看。
