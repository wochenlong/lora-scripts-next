# Anima Edit — 双参考·多人融合文档例图

面向模型**真正擅长**的任务：两张 AI 参考图 + **Fuse … into a pair …** 式 caption + ImagePulse **双参考 LoRA**（`imagepulse-30e-000020`）。

与 [`anima-edit-showcase-curated/`](../anima-edit-showcase-curated/)（单参考 + Place 场景）对比使用。

**文档选型结论（人工验收）**：双参考例图能稳定呈现「两人同框 + 可辨认角色」，明显优于单参考 `Place` 路线；常见瑕疵是 **服装细节略漂**（领口、褶边、配色），发型与大体造型一般可对上。门面图优先用本目录。

| Case | ref1 | ref2 | 融合场景 |
|------|------|------|----------|
| dual01 | 黑长直水手服 | 金双马尾水手服 | 樱花小径并肩行走 |
| dual02 | 巫女 | 羽织少年 | 夕照鸟居石阶 |
| dual03 | 女仆 | 银发毛衣少女 | 雨夜喫茶店吧台 |

文件：`dualNN-ref1.png`、`dualNN-ref2.png`、`dualNN-out.png`。

权重：`output/anima-edit-imagepulse-30epoch/imagepulse-30e-000020.safetensors`  
采样：512×50 步，`scale=4.5`，`reference_count=2`。

数据与 caption：`data/anima-edit-showcase-dual-curated/`  
命令见 [anima-edit-showcase-workflow.md](../../design/anima-edit-showcase-workflow.md)「双参考多人例图」一节。
