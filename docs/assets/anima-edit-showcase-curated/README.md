# Anima Edit — 精选文档例图（非训练集）

例图与 **ImagePulse 训练数据分离**：参考图由 AI 文生图（`banana-pro`）生成，编辑结果由单图参考 LoRA **`anima-single-12e`** + 完整 edit caption、512×50 步 sample-only 推理得到。

| Case | 参考（AI） | 编辑结果（LoRA） | 场景 |
|------|------------|------------------|------|
| case01 | 银发贵族半身像 | 哥特花房 + 圆桌古书 | 欧式奇幻 |
| case02 | 水手服短发少女 | 樱花校园小径 | 日式校园春景 |
| case03 | 巫女持御神签 | 夕照鸟居石阶 | 神社和风 |
| case04 | 女仆咖啡厅制服 | 雨夜复古喫茶店 | 日常系室内 |

文件命名：`caseNN-ref.png`（输入参考）、`caseNN-out.png`（模型输出）。

流程与命令见 [anima-edit-showcase-workflow.md](../../design/anima-edit-showcase-workflow.md)。  
登记与 caption：`data/anima-edit-showcase-curated/manifest.json`、`prompts/case*.txt`。

**两人同框 / 融合**请用 [`../anima-edit-showcase-dual-curated/`](../anima-edit-showcase-dual-curated/)（双参考 + `imagepulse-30e-000020` + Fuse caption）。

AI 参考图批量下载：`python script/ops/fetch_aisp_showcase_refs.py case02 case03 case04`
