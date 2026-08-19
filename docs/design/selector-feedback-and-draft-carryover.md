# 设计计划 — 选择器反馈补强 + 换模型草稿随行

> **来源**：产品定稿审计缺口（关联 Issue #215；阶段：工作台肌肉记忆）
> **范围**：主控选择器三处缺口补齐；后端零改动。
> **前置审计**：`docs/design` 系列已定稿的交互（模型优先、灰置过滤、默认 Kohya/LoRA、自动兜底）均符合，本计划只补审计出的 3 个缺口。

---

## 1. 缺口清单

| # | 定稿规则 | 现状缺口 |
| --- | --- | --- |
| A | 不兼容自动落默认组合时**短 toast 提示（勿静默）** | `TrainingWorkbenchPage.vue` watch 静默纠正 |
| B | 灰掉引擎/目标**可附「该模型暂不支持」** | 仅灰置，无提示 |
| C | 换模型/换引擎**草稿保留，能映射的字段尽量留下** | 各模块草稿独立保留（切回不丢），但切换时不做跨模块字段映射 |

## 2. 方案 A：自动纠正 toast(`TrainingWorkbenchPage.vue`)

- 在现有 watch 中，引擎或目标被兜底改写时，`ElMessage.info` 提示一次（同一次变更只提示一条）。
- 仅在真实发生纠正时触发；初始化（`initFromQuery`）不在 watch 内，不受影响。
- 新增 i18n:`training.selector.autoAdjusted` = 「当前组合与该模型不兼容，已切换为默认可用组合」/ "The previous combination is unavailable for this model; switched to the default supported combination."

## 3. 方案 B：不支持提示（`TrainingSelector.vue`)

- 原生 `<select>` 的 `<option>` 挂 `title` 提示跨浏览器不可靠，改为**选择器下方一行说明文字**:
  - 引擎区：当前模型存在不可用引擎时显示，如「Musubi-Tuner：该模型暂不支持」;`TRAINING_ENGINES.filter(e => !isEngineSupported(model, e))` 计算，全部可用则不渲染。
  - 目标区：同理，`TRAINING_TARGETS.filter(t => !isTargetSupported(model, engine, t))`。
- 样式：`.selector-hint`,`text-faint` 11px，不抢视觉。
- 新增 i18n:`training.selector.unsupportedForModel` = 「{list}：该模型暂不支持」/ "{list}: not available for this model"(list 用现有引擎/目标文案拼接）。

## 4. 方案 C：换模型草稿随行（`TrainingPage.vue`)

现状链路：换模型/引擎/目标 → `resolved` 变化 → `:key="storageKey || schemaName"` 重挂载 → `load()` 用 `defaults + 本模块 autosave`。补齐「随行」层：

1. **卸载时写随行快照**:`onBeforeUnmount` 除现有 autosave 外，把当前表单 model 写入 `sessionStorage["mikazuki-carry-over"]`(session 级，不污染长期存储；连同来源模块标识）。
2. **加载时三层合并**:`createDefaultModel(loaded)` + `props.fieldDefaults` + **随行快照（按 key 过滤）** + 本模块 autosave。优先级：本模块 autosave 最高（用户在该模块的显式草稿优先），随行只填充目标模块尚无草稿时的可映射字段。
   - 过滤规则：仅保留存在于新 Schema 默认模型中的 key(`createDefaultModel(loaded)` 的 key 集合），类型/选项不匹配的字段由条件字段与序列化自然消化。
   - 应用一次后即清除随行快照，避免陈旧值回流。
3. 「重置」行为不变：仍只清当前模块 autosave 并恢复默认。
4. 典型收益：Anima → SDXL 切换后，`train_data_dir`、`resolution`、`learning_rate`、`output_name` 等同名字段直接带入，用户不重填。

边界说明：

- 不同 Schema 的枚举值差异（如 `lora_type` 选项集不同）由字段条件渲染兜底，最坏情况是回落默认，不会产出非法 TOML（提交前后端双重校验仍在）。
- `gpu_ids` 注入字段在 key 集合内，随行自然覆盖。

## 5. 实施步骤

1. `TrainingWorkbenchPage.vue`:watch 纠正时 ElMessage 提示（方案 A)。
2. `TrainingSelector.vue`：引擎/目标下方 `.selector-hint`（方案 B)。
3. i18n：双语新增 `autoAdjusted`、`unsupportedForModel`。
4. `TrainingPage.vue`：随行快照写入/读取/清除（方案 C)。
5. 验证：`npm run check`；手工——选 Flux（无 finetune）时目标灰置 + 提示行；从不兼容组合切模型出现 toast;Anima 填好数据路径后切 SDXL，同名字段带入；切回 Anima 原草稿仍在；重置行为不变。
6. dist 产物按惯例单独 `chore(frontend): publish built Vue frontend` 提交（先 `git add --renormalize frontend/dist`)。

## 6. 验收标准

- 自动落到默认组合必有 toast；不兼容引擎/目标灰置且下方有「该模型暂不支持」说明。
- 换模型/换引擎后可映射字段保留，目标模块已有草稿时以目标草稿为准；仅「重置」清空。
- 各项提示双语齐全，移动端布局不破坏。
