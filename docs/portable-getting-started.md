# 整合包补充说明

面向 **Next Trainer 便携整合包**（归档名 `Next-Trainer-v*.7z`；包内目录仍为 `SD-Trainer/`）用户的进阶说明。快速上手只需 README 中的三步：下载 → 双击 `run_gui.bat` → 浏览器开练。

当前最新版：**v2.8.2**（[Releases](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.8.2)）。

---

## 系统要求

- Windows 10/11 64 位
- NVIDIA 显卡（建议 RTX 20 系列及以上）
- 约 7 GB 磁盘空间（不含模型与输出）
- 首次启动需联网下载 PyTorch 等依赖（约 3 GB）

---

## 打标模型

整合包已内置默认 WD 打标模型 **wd14-convnextv2-v2**（约 400 MB），路径：

```text
tagger-models/wd14/wd14-convnextv2-v2/
  model.onnx
  selected_tags.csv
```

WebUI **「工具与调试 → 数据集打标」** 开箱即用，无需首次联网下载。

若在线拉取失败，可手动将上述两个文件放入该目录。更多模型与目录约定见 [`tagger-models.md`](tagger-models.md)。

---

## 命令行 / 云平台训练

WebUI 整合包以 **Windows 双击启动** 为主。若你在 Linux、AutoDL 或纯终端环境训练：

| 场景 | 入口 |
|------|------|
| SD / SDXL / Flux（旧式） | `train.sh` |
| Anima 标准 LoRA | `bash train_anima_by_toml.sh docs/examples/anima-lora-benchmark-kohya.toml` |
| Anima Fast 插件 | 先 `bash scripts/cli/install_anima_fast.sh`，再 `bash train_anima_fast_by_toml.sh docs/examples/anima-lora-benchmark-fast.toml` |
| **Krea 2 多卡（Linux / `dev` / Musubi）** | WebUI 显卡多选；教程见 [`krea2-linux-multigpu.md`](krea2-linux-multigpu.md) |

Anima Fast 在整合包内也可通过侧栏 **Anima LoRA → Fast 模式** 页内安装，详见 [`anima-fast.md`](anima-fast.md)。

---

## v2.8.2 整合包更新要点

相对 v2.7.0 及更早整合包，**v2.8.2** 主要修复：

### SDXL 训练修复

- 修正 WebUI `sdxl-lora` 训练路由
- 预置 `tokenizer-cache/`，SDXL / Flux 离线训练无需首次联网拉 tokenizer
- 整合包环境下训练子进程启动修复（避免误报「训练接口网络请求失败」）

### 打标修复

- 默认 WD 模型随包预置，`tagger-models/wd14/` 开箱即用
- 打标加载超时保护、ONNX / CUDA 诊断与 CPU 回退

### 预览图修复

- 导入旧 autosave / TOML 缺少 `enable_preview` 时自动推断预览字段
- Anima Fast 开启预览后默认出首张样图
- Fast 环境安装完成后自动刷新，不再遮挡右侧参数预览

### 训练配置导入修复

- 全量导入时保留数值类型（整数 / 浮点）
- 参数预览与「下载配置文件」序列化修复

完整记录见仓库根目录 [`CHANGELOG.md`](../CHANGELOG.md)。

---

## 从旧版整合包升级

| 方式 | 脚本 | 说明 |
|------|------|------|
| Release 合并（推荐） | `Update-SD-Trainer-Release.bat` | 下载最新 Release 7z 并合并 |
| Git 快进 | `Update-SD-Trainer.bat` | 需 `SD-Trainer/.git` 存在 |

用户数据（`sd-models/`、`output/`、`logs/`、`config/autosave/`）不会被覆盖。

若你仍在 **v2.5.2**，可先参考 [`portable-upgrade-2.5.2-to-2.5.3.md`](portable-upgrade-2.5.2-to-2.5.3.md)，再整包更新到 v2.8.2。

更多打包与更新契约见 [`portable-packaging-git-update.md`](portable-packaging-git-update.md)。
