# 设计约定 — 训练表单分区通用排序骨架

> **状态**：产品已拍板（2026-08-26），本 PR 仅落文档；各 `mikazuki/schema/*.ts` 落地改动另开实施 PR。  
> **范围**：训练工作台 Schema 表单的**分区顺序与字段归属心智**；适用于现有 Kohya / Anima Fast / Musubi，以及后续 AI Toolkit 等引擎接入的模型。  
> **关联**：产品 IA [#215](https://github.com/wochenlong/lora-scripts-next/issues/215)；跟踪 Issue [#297](https://github.com/wochenlong/lora-scripts-next/issues/297)。

---

## 1. 目标

培养统一用户心智：

1. **开头必定是「训练用模型」**（选底模 / 填路径）。
2. **结尾必定是「分布式训练」**（多卡 / 多机；引擎暂不支持也保留同名位，勿换别的结尾）。
3. **取消「×× 专用参数」分区**，字段拆进对应格子，禁止插在数据集前面。

操作主路径对齐：

```text
选模型 → 选类型 → 模型路径 → 数据集路径 → …… → 分布式
```

以现有 Kohya SDXL（`lora-master`）为参考骨架，向全站推广。

---

## 2. 全站固定顺序（硬规矩）

| 序 | 分区名 | 放什么 | 可空？ |
|----|--------|--------|--------|
| 1 | **训练用模型** | 底模及配套权重路径（VAE / TE / AE…）、resume | 否 |
| 2 | **训练模型类型** | 身份选择：预测类型、`lora_type`（lora/lokr…）、flux/chroma、`model_version` 等 | 可空（无类型开关时隐藏整段） |
| 3 | **数据集设置** | 目标图目录、分辨率/桶、caption 后缀；编辑能力时用 **`control_data_dirs[]`**（AI Toolkit 多目录同名格式，详见 [`image-edit-dataset-contract.md`](./image-edit-dataset-contract.md)） | 否 |
| 4 | **保存设置** | output 名/目录、保存频率与精度 | 否 |
| 5 | **训练过程** | epoch / steps / batch / seed；时间步与损失调度（原「专用」里的 timestep / shift / CFG / token 长度等） | 否 |
| 6 | **学习率与优化器** | lr、scheduler、optimizer | 否 |
| 7 | **网络设置** | dim / alpha / LyCORIS 细节、续训权重等 | 可空（全量微调无 LoRA 时隐藏） |
| 8 | **训练预览图设置** | enable_preview、sample prompts、间隔；编辑模型可挂预览用参考图 | 可空（引擎无采样时隐藏） |
| 9 | **省显存** | 梯度检查点、fp8、blocks_to_swap、attn、compile、cache 等 | 建议保留 |
| 10 | **日志 / caption / 噪声 / 数据增强**（若仍有独立用户任务） | 各自独立分区，顺序紧挨「其他」之前 | 可空 |
| 11 | **其他** | 收纳箱（见 §3） | 建议保留 |
| 12 | **分布式训练** | 多卡 / 多机；**永远最后一格** | 保留空位（不支持则灰掉说明） |

### 2.1 禁止

- 禁止再出现「Anima 专用参数 / Flux 专用参数 / Krea 2 专用参数」这类插在数据集前的整块分区。
- 禁止把预览、日志、caption 等已独立任务塞回「其他」却仍占独立标题空壳。
- 禁止用别的分区替换「分布式训练」作为表单结尾。

### 2.2 原「×× 专用参数」拆分归属

| 字段类型 | 落到 |
|----------|------|
| 类型开关（lokr、SDXL 预测类型、flux/chroma、klein `model_version`…） | **训练模型类型** |
| timestep / shift / sigmoid / weighting / CFG / token 长度 | **训练过程** |
| attn / compile / VAE chunk / offload / blocks_to_swap / fp8… | **省显存** |

---

## 3. 「其他」= 收纳箱

定位：暂时归不进前几格、又不够单独开板块的尾巴字段。

### 3.1 箱内排序（按对训练结果的影响从强到弱）

1. **数据怎么进模型** — caption shuffle / dropout、token 保留、clip_skip、加权 caption 等（若未升格独立分区）  
2. **噪声与目标扰动** — noise_offset、multires noise 等  
3. **数据增强** — flip、color aug 等  
4. **可复现与杂项训练开关** — 未进「训练过程」的 seed 等  
5. **日志与追踪** — TensorBoard / wandb（若未独立）  
6. **调试与实验** — profile、nan check、debug mode 等  
7. **纯 UI / 透传** — `ui_custom_params` 等  

规则：用户能说出「我要去调 XX」→ **单独分区**；说不清、很少动 → **其他**。某类长大后从「其他」**升格**为独立分区，插在「其他」前；「其他」本身不改名、不挪到分布式后。

---

## 4. 跨引擎适用性（通用）

本骨架不绑定单一引擎。后续模型只增减字段，**不改分区顺序**。

| 场景 | 字段落点 |
|------|----------|
| Klein / Kontext / Qwen-Edit 等 | 参考图 → **数据集** 的 `control_data_dirs[]`（与 AI Toolkit 目录格式对齐，见 [`image-edit-dataset-contract.md`](./image-edit-dataset-contract.md)）；预览 control → **训练预览**；不新开「编辑」大分区 |
| 视频（Wan 等） | `num_frames` / fps → **数据集** |
| 音频 | 路径与长度类 → **数据集** |
| 全量微调 | **网络设置**整段隐藏 |
| 引擎暂无分布式 | 最后一格保留并说明不支持 |

Musubi / AI Toolkit 的 CLI 或上游 UI 卡片顺序可以不同；**Next Trainer 工作台以本约定为准**（先模型路径与数据集，再训练过程，最后分布式）。

---

## 5. 落地范围（后续实施 PR，非本文）

按本约定调整（示例，以实施 PR 为准）：

- `mikazuki/schema/sd3-lora.ts`、`anima-lora-fast.ts`、`anima-finetune.ts`
- `mikazuki/schema/flux-lora.ts`、`lumina2-lora.ts`、`krea2-lora.ts`
- 对齐时顺带核对 `lora-master.ts` / `dreambooth.ts`（SDXL 大体已近标准；`gradient_checkpointing` 等应从「训练相关」挪到「省显存」）
- 前端 TOC / i18n 分区标题与 schema `.description()` 一致
- 无行为变更的纯顺序调整；默认值与校验语义保持不变

验收：打开各训练入口，分区 TOC 顺序与上表一致；数据集紧跟模型路径区；无「×× 专用参数」；末格为分布式。

---

## 6. 相关

- [`image-edit-dataset-contract.md`](./image-edit-dataset-contract.md) — 图像编辑数据集前端契约（AI Toolkit 多目录格式；Musubi 同格式消费）
- [`schema-form-single-column.md`](./schema-form-single-column.md) — 表单单列（布局，不改分区语义）
- [`selector-feedback-and-draft-carryover.md`](./selector-feedback-and-draft-carryover.md) — 选择器与草稿携带
- 团队分工：产品 IA [@wochenlong](https://github.com/wochenlong)；前端落地 [@IryNeko](https://github.com/IryNeko)；引擎侧字段映射 [@MikumikuDAIFans](https://github.com/MikumikuDAIFans)
