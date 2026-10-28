# Anima LoKr / sd-scripts 注意事项

## 不加 caption dropout，高 CFG 下适配器会近乎失效

kohya/sd-scripts 系训练只在"有条件"（CFG=1）状态下进行，**cond−uncond 方向从未被训练，
完全继承底模**。CFG>1 推理时的有效引导为：

```
eps = (s·f_cond − (s−1)·f_uncond) + (s·Δ_cond − (s−1)·Δ_uncond)
```

适配器的 Δ 只学过 cond 一侧，`Δ_uncond` 是训练分布外的随机行为；CFG 放大后
`s·Δ_cond − (s−1)·Δ_uncond` 方向被污染，同时底模项被放大、内容 tag 越多占比越大。
表现：CFG=1 画风满格，CFG=4 + 多 tag 时 LoKr 几乎完全无效。

对策（dataset toml 的 `[general]`）：

```toml
caption_dropout_rate = 0.1   # 整条 caption 随机丢弃，让适配器学习 uncond 方向
```

- 与 `caption_tag_dropout_rate`（tag 级丢弃，治 prompt 长短敏感）是两个不同参数，都可配 0.1
- rate 超过 0.2 时小数据集上条件侧有效步数打折明显，触发词响应会变钝，0.1 为推荐值
- 同理：**质量类负面词（worst quality / low quality 等）构造的射线方向可能与目标画风语义对冲**，
  画风类适配器建议空负面或仅留纯质量项（lowres / jpeg artifacts）

## 其他要点

- 训练时 LoKr/LoHa 的文本编码器默认不训（`network_train_unet_only=true`），产物中的
  `lora_te1_*` 权重是未训练的初始化骨架，推理端 clip 强度滑块无效果属预期
- `lokr_factor=-1`（无穷）是容量最小形态；factor 4 约 2.7 倍参数。
  实测对画风类目标收益不显著，优先排查 conditioning 配置而非加容量
- 单作者/单风格数据集建议加专属触发词置于 caption 行首，配合 `shuffle_caption=true` +
  `keep_tokens=1`；训练预览的 prompt 也要带上触发词，否则预览无法反映训练效果
- flow-matching 训练的 loss 存在固有噪声地板，loss 曲线只能用于排查发散/NaN，
  不能用于判断拟合程度；以预览图和同 seed 推理对照为准
