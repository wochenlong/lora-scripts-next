# 开源引用与致谢 / Credits

本页面向用户说明 **Next Trainer**（仓库 [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)）依赖与改编的主要开源项目。  
**完整法律声明与引用细节以仓库根目录 [NOTICE.md](../NOTICE.md) 为准。**

界面内也可查看：**设置 → 关于**。

[← 返回中文 README](../README-zh.md) · [English README](../README.md)

---

## 致谢秋叶（Akegarasu）

Next Trainer 向 **秋叶（Akegarasu）** 及其开源项目 **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)**（社区常称 **SD-Trainer** / **秋叶一键训练包**）致以感谢。

我们感谢秋叶项目长期公开维护本地训练 WebUI、整合包体验，以及与训练后端对接的实践。许多用户熟悉的操作路径，正是在这一谱系中形成的。Next Trainer 在此基础上继续演进，并保留对上游的公开致谢。

请同时理解以下边界，避免误读：

1. Next Trainer **不是** 秋叶官方版本，也 **不代表** 秋叶本人或其团队。  
2. Next Trainer **无意** 否定、贬低或「取代」上游；上游仓库仍按其自身节奏独立发展。  
3. 若你更偏好原版体验，请使用上游：https://github.com/Akegarasu/lora-scripts  
4. 本仓库以自有品牌 **Next Trainer** 发布功能与路线图，同时继续遵守 AGPL 等适用许可，并保留 NOTICE 中的谱系说明。  
5. 再分发源码或整合包时，请保留本页所指的 [NOTICE.md](../NOTICE.md)、[LICENSE](../LICENSE) 及各上游要求的声明。

秋叶项目链接：https://github.com/Akegarasu/lora-scripts

---

## Acknowledgements to Akegarasu

Next Trainer gratefully acknowledges **Akegarasu** and **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)** (often known in the community as **SD-Trainer**).

We thank that project for years of open work on local training WebUI workflows, portable packaging, and practical integration with training backends. Much of the familiar operator path that users recognize grew in that lineage. Next Trainer continues from that foundation and keeps this credit public.

Please read these boundaries carefully:

1. Next Trainer is **not** an official Akegarasu release and does **not** speak for Akegarasu or their team.  
2. Next Trainer does **not** claim to replace, diminish, or oppose upstream; upstream remains independent.  
3. If you prefer the original experience, use: https://github.com/Akegarasu/lora-scripts  
4. This repository ships under the **Next Trainer** product name and roadmap, while remaining bound by AGPL and the notices in [NOTICE.md](../NOTICE.md).  
5. When redistributing source or portable builds, keep NOTICE, LICENSE, and upstream-required notices intact.

---

## 上游与训练后端

| 项目 | 链接 | 本仓库中的角色 |
|------|------|----------------|
| Akegarasu / lora-scripts | https://github.com/Akegarasu/lora-scripts | 体验谱系与社区整合包实践来源（上游常称 SD-Trainer；本产品品牌为 Next Trainer）。详见上方专节致谢。 |
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

Next Trainer gratefully acknowledges Akegarasu/lora-scripts as part of its UX and packaging lineage, and continues to rely on kohya-ss/sd-scripts for major training backends. Optional Anima Fast uses [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora) (MIT). LoKr/LoHa via LyCORIS; default tagger from SmilingWolf WD models; forms powered by schemastery. Full notices: [NOTICE.md](../NOTICE.md).
