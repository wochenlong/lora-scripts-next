# Issue #215 计划 — 主控层移除 LoKr 训练目标

> **关联 Issue**：#215
> **范围**：仅前端主控层（模型 / 引擎 / 训练目标选择器）。Schema 表单层与后端 LoKr 训练能力保持不变。

---

## 1. 需求意义

当前训练工作台主控层「训练目标」提供 **LoRA / LoKr / 全量微调** 三个选项，但：

1. **LoKr 永远不可选**。`TRAINING_MODULES` 中没有任何 `target: "lokr"` 的模块，`TrainingSelector` 按 `isTargetSupported()` 禁用按钮，LoKr 在所有 模型×引擎 组合下都是灰色死选项（`modules.test.ts` 甚至有专门测试固化这一状态）。
2. **与表单字段职责重复**。适配器类型在 Schema 表单里已有独立入口：
   - Anima（`sd3-lora`）：`lora_type` 枚举 `lora / lokr / tlora / lora_fa / vera / loha`（`mikazuki/schema/sd3-lora.ts:4`）。
   - SD 1.5 / SDXL / Flux / Lumina（`lora-master`、`flux-lora`、`lumina2-lora`）：通过 `network_module=lycoris.kohya` + `lycoris_algo=lokr` 选择（`mikazuki/schema/shared.ts:46-64`）。
3. **两处选择会互相打架的隐患**。主控层选「目标」决定加载哪个 Schema；如果未来给 LoKr 建独立模块，用户可能在主控选 LoKr、又在表单里选 `lora_type=lora`（或反过来），产出自相矛盾的配置。映射层目前也无法为 LoKr 预设字段，主控层放这个选项没有落地路径。

结论：**「训练目标」只表达训练范式（适配器训练 vs 全量微调），适配器具体类型（LoRA / LoKr / LoHa / …）一律由表单字段决定**。主控层收敛为 LoRA | 全量微调两项。

## 2. 现状清点

| 位置 | 内容 | 处置 |
| --- | --- | --- |
| `frontend/src/training/modules.ts:5` | `TrainingTarget = "lora" \| "lokr" \| "finetune"` | 移除 `"lokr"` |
| `frontend/src/training/modules.ts:22` | `TRAINING_TARGETS = ["lora", "lokr", "finetune"]` | 移除 `"lokr"` |
| `frontend/src/components/TrainingSelector.vue:40` | 按 `TRAINING_TARGETS` 渲染分段按钮 | 无需改，数据源收敛后 LoKr 按钮自然消失 |
| `frontend/src/pages/TrainingWorkbenchPage.vue:42,56` | `isTarget()` 校验 query、解析 `target` | 无需改逻辑；`target=lokr` 旧链接将落到默认值，watch 兜底回 `lora` |
| `frontend/src/i18n/messages/zh-CN.ts:38`、`en-US.ts:38` | `training.selector.targets.lokr` 文案 | 删除 |
| `frontend/src/training/modules.test.ts:66,76-81` | 「lokr 对所有组合不支持」的固化测试 | 改写为「target 集合仅含 lora/finetune」类断言 |
| `frontend/src/router.ts` | 旧 URL redirect 均使用 `target: "lora"/"finetune"` | 无需改 |

明确**不动**的部分：

- Schema 层：`sd3-lora.ts` 的 `lora_type` 枚举、`shared.ts` 的 `LYCORIS_MAIN` / `LYCORIS_LOKR` 分支全部保留，LoKr 训练照常可用。
- 前端参数转换：`training/params.ts` 的 `lokr_factor`、`lycoris_algo` 处理及对应测试保留。
- 后端：`mikazuki/app/api.py` 的 `_anima_lokr_*` 警告、`anima_backend/adapter.py` 的 LoKr 预设注入、`lycoris_patch.py` 的 bf16 patch 全部保留。
- 导入/导出：`config_import.py` 的 `factor→lokr_factor`、`lokr→lokr` 映射保留；导入含 LoKr 的配置仍按 `model_train_type` 路由到对应 LoRA 模块，表单内恢复 `lora_type=lokr`。

## 3. 实施步骤

1. `modules.ts`：`TrainingTarget` 类型与 `TRAINING_TARGETS` 移除 `"lokr"`。
2. i18n：删除 `zh-CN.ts` / `en-US.ts` 中 `training.selector.targets.lokr`。
3. `modules.test.ts`：
   - 删除/改写 lokr 不支持的两个断言（`resolveModule("anima","kohya","lokr")`、`marks lokr as unsupported...`），改为断言 `TRAINING_TARGETS` 只包含 `["lora", "finetune"]`。
   - 保留其余映射测试不变。
4. 手工验证工作台：目标分段只显示 LoRA / 全量微调；切换模型×引擎行为不变；`?target=lokr` 旧链接进入后自动回退 LoRA。
5. 回归确认 LoKr 路径仍可用：Anima LoRA 页面表单内 `lora_type=lokr`，TOML 预览正确输出 `lokr_factor` / `algo=lokr`。
6. 运行 `npm run check`（typecheck + lint + vitest + build）。
7. 按 `frontend/AGENTS.md` 第 10 节评估是否在 `MIGRATION.md` 记录该行为变化。

## 4. 兼容性与风险

- **URL 兼容**：`?target=lokr` 不再是合法值，`initFromQuery()` 忽略后使用默认 `lora`；无 404、无死链。
- **本地存储**：草稿/history 按 storageKey 存储表单 model，不含 target 维度，不受影响。
- **风险极低**：改动集中在前端常量与文案；后端与 Schema 零改动。唯一行为差异是 LoKr 入口从「灰按钮 + 表单字段」变为「仅表单字段」。

## 5. 验收标准

- 主控「训练目标」仅显示 LoRA | 全量微调，任何 模型×引擎 组合下无 LoKr 选项。
- Anima LoRA 表单 `lora_type` 仍可选 `lokr` 并正确产出训练参数；SD/SDXL/Flux/Lumina 通过 LyCORIS `lokr` 算法训练的路径不变。
- `npm run check` 全绿。
