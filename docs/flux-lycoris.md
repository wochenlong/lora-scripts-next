# Flux LoKr / LoHa（LyCORIS）

Flux（Kohya）训练页提供 LoRA、LoKr、LoHa 和自定义四种适配器入口。默认仍是普通 LoRA，使用 `networks.lora_flux`；LoKr 和 LoHa 通过外置 `lycoris.kohya` 训练。

## 适配器类型

| 类型 | 实际网络模块 | 主要参数 |
| --- | --- | --- |
| LoRA | `networks.lora_flux` | `network_dim`、`network_alpha` |
| LoKr | `lycoris.kohya` + `algo=lokr` | `network_dim`、`network_alpha`、`factor` |
| LoHa | `lycoris.kohya` + `algo=loha` | `network_dim`、`network_alpha` |
| 自定义 | 保留高级网络模块选择 | OFT 及其他 LyCORIS 算法与高级参数 |

自定义入口继续支持 `networks.oft_flux`，以及 LoCon、(IA)³、DyLoRA、GLoRA、Diag-OFT、BOFT 等现有 LyCORIS 算法。旧版没有 `lora_type` 的高级配置会进入自定义入口，避免丢失原有参数。

## 起始参数

以下仅作为小数据集的起始尝试，需要根据底模、数据集和训练结果调整：

| 参数 | LoKr | LoHa |
| --- | --- | --- |
| `network_dim` | 4 | 4 |
| `network_alpha` | 1 | 1 |
| `factor` | -1 | 不适用 |
| Dropout | 0 | 0 |

LoKr 的 `factor` 控制 Kronecker 分解。`-1` 表示自动/无穷分解，也可在自定义入口尝试其他正整数。LoKr 的维度含义与普通 LoRA rank 不完全相同，不要直接套用大 rank。

普通 `network_dropout` 与 LyCORIS 不兼容。需要 LyCORIS 自带的 dropout 或其他高级参数时，请使用自定义入口；一等 LoKr / LoHa 入口默认使用 0。

自定义 `network_args` 仍按一行一个 `key=value` 填写。同名参数会覆盖前面生成的值，请避免无意中覆盖 `algo` 或 `factor`。

## 配置导入与导出

- 页面右侧的训练 TOML 不包含 UI 专用的 `lora_type`，实际训练使用 `network_module` 和 `network_args`。
- 下载的 GUI 配置会保留可恢复的适配器标识，可重新导入 Flux 页面继续训练。
- 新版 LoKr / LoHa 配置往返导入后仍回到对应入口。
- 旧版高级 LyCORIS、OFT 和其他算法配置进入自定义入口，原网络模块和参数保持不变。

## 实验性与推理兼容性

Flux LoKr / LoHa 使用项目 Kohya 环境安装的 `lycoris-lora==3.3.0`，不代表 sd-scripts 内置 `networks.lokr` 或 `networks.loha` 已声明支持 Flux。该路径相对普通 Flux LoRA 属于实验性/兼容性能力。

LoKr 权重通常包含 `lokr_*` 张量，LoHa 权重通常包含 `hada_*` 张量。推理器必须支持相应 LyCORIS 权重格式；仅凭 `.safetensors` 扩展名或 `lora_unet` 前缀，不能推断所有普通 LoRA 加载器都能使用。部署前应在目标推理路径上加载保存后的权重进行验证。

本入口不改变 Anima 的适配器实现，也不适用于 Anima Fast、Musubi 或 AI-Toolkit。
