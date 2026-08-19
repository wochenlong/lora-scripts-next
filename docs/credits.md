# 开源引用与致谢 / Credits

本页面向用户说明 **Next Trainer**（仓库 [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)）依赖与改编的主要开源项目。  
**完整法律声明与引用细节以仓库根目录 [NOTICE.md](../NOTICE.md) 为准。**

界面内也可查看：**设置 → 关于**。

[← 返回中文 README](../README-zh.md) · [English README](../README.md)

---

## 上游与训练后端

| 项目 | 链接 | 本仓库中的角色 |
|------|------|----------------|
| Akegarasu / lora-scripts | https://github.com/Akegarasu/lora-scripts | 秋叶一键训练包生态与 GUI 体验来源（上游常称 SD-Trainer；本产品品牌为 Next Trainer） |
| kohya-ss / sd-scripts | https://github.com/kohya-ss/sd-scripts | Anima / Flux / SD 系列训练脚本与后端（AGPL-3.0） |

## Anima Fast（可选引擎）

| 项目 | 链接 | 许可 |
|------|------|------|
| sorryhyun / anima_lora | https://github.com/sorryhyun/anima_lora | MIT |

以可选插件形式集成（`extensions/anima_lora/`）。说明见 [docs/anima-fast.md](anima-fast.md)。

## 网络模块与其它组件

| 项目 | 链接 | 说明 |
|------|------|------|
| KohakuBlueleaf / LyCORIS | https://github.com/KohakuBlueleaf/LyCORIS | LoKr / LoHa 等（Apache-2.0） |
| ControlGenAI / T-LoRA | https://github.com/ControlGenAI/T-LoRA | 时间步相关 LoRA（MIT） |
| muooon / EmoSens | https://github.com/muooon/EmoSens | 优化器相关（Apache-2.0） |
| bluvoll / Akegarasu-lora-scripts-RF | https://github.com/bluvoll/Akegarasu-lora-scripts-RF | SDXL Rectified Flow 思路参考（AGPL-3.0） |
| SmilingWolf / WD Tagger | https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2 | 默认离线打标模型与标签表 |
| shigma / schemastery | https://github.com/shigma/schemastery | Vue3 动态表单 Schema 运行时 |

历史参考（非当前主后端）：[WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts) — 详见 [NOTICE.md](../NOTICE.md)。

---

## 本仓库许可

见根目录 [LICENSE](../LICENSE)。再分发整合包或源码时，请同时保留 **NOTICE** 与各上游许可要求。

---

## English summary

Next Trainer builds on the Akegarasu lora-scripts ecosystem and kohya-ss/sd-scripts. Optional Anima Fast uses [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora) (MIT). LoKr/LoHa via LyCORIS; default tagger from SmilingWolf WD models; forms powered by schemastery. Full notices: [NOTICE.md](../NOTICE.md).
