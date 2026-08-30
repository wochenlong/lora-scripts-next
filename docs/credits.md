# 开源引用与致谢 / Credits

本页面向用户说明 **Next Trainer**（仓库 [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)）依赖与改编的主要开源项目。  
**完整法律声明与引用细节以仓库根目录 [NOTICE.md](../NOTICE.md) 为准。**

界面内也可查看：**设置 → 关于**。

[← 返回中文 README](../README-zh.md) · [English README](../README.md)

---

## 致谢 Akegarasu

Next Trainer 向 **Akegarasu** 及其开源项目 **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)**（社区常称 **SD-Trainer** / **秋叶一键训练包**）致以感谢。

我们感谢 Akegarasu 长期公开维护本地训练 WebUI、整合包体验，以及与训练后端对接的实践。许多用户熟悉的操作路径，正是在这一谱系中形成的。Next Trainer 在此基础上继续演进，并保留对上游的公开致谢。

项目链接：https://github.com/Akegarasu/lora-scripts

再分发源码或整合包时，请保留 [NOTICE.md](../NOTICE.md)、[LICENSE](../LICENSE) 及各上游要求的声明。

---

## Acknowledgements to Akegarasu

Next Trainer gratefully acknowledges **Akegarasu** and **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)** (often known in the community as **SD-Trainer**).

We thank that project for years of open work on local training WebUI workflows, portable packaging, and practical integration with training backends. Much of the familiar operator path that users recognize grew in that lineage. Next Trainer continues from that foundation and keeps this credit public.

Upstream project: https://github.com/Akegarasu/lora-scripts

When redistributing source or portable builds, please keep [NOTICE.md](../NOTICE.md), [LICENSE](../LICENSE), and upstream-required notices intact.

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

## 历史参考：早期 Anima 接入

当前 Anima 训练后端是 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)。

在更早的 Anima 接入阶段（旧 `main` 线、尚未以 Kohya 路径作为持续维护后端之前），本仓库**曾参考并改编**：

- [WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts)（**SD-reScripts**，AGPL-3.0）

仓库历史中有自该项目的合并记录，以及随后迁到 Kohya 的提交；迁移前 NOTICE 亦写明 Anima 支持改编自该项目。感谢该项目的公开工作。它不是 Next Trainer 当前的 Anima 运行后端，也不是本仓库上游。完整法律说明见 [NOTICE.md](../NOTICE.md) 的 Anima LoRA 节。

### Historical note: early Anima integration

Current Anima training is maintained against [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts).

During an earlier Anima integration stage (before the Kohya-backed path became the maintained backend), this repository **referenced and adapted** work from:

- [WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts) (**SD-reScripts**, AGPL-3.0)

History includes a merge from that project and a later migration onto Kohya; pre-migration notices also described Anima support as adapted from SD-reScripts. We thank that project for the open work referenced and adapted then. It is not the current Anima backend for Next Trainer, and it is not an upstream of this repository. Full notice: [NOTICE.md](../NOTICE.md).

---

## 本仓库许可

见根目录 [LICENSE](../LICENSE)。再分发整合包或源码时，请同时保留 **NOTICE** 与各上游许可要求。

---

## English summary

Next Trainer gratefully acknowledges Akegarasu/lora-scripts as part of its UX and packaging lineage, and continues to rely on kohya-ss/sd-scripts for major training backends (including current Anima). Early Anima integration historically referenced and adapted [WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts); that is not the current backend. Optional Anima Fast uses [sorryhyun/anima_lora](https://github.com/sorryhyun/anima_lora) (MIT). LoKr/LoHa via LyCORIS; default tagger from SmilingWolf WD models; forms powered by schemastery. Full notices: [NOTICE.md](../NOTICE.md).
