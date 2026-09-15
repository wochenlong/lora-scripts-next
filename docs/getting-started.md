# 快速开始

[返回首页](../README-zh.md) · [文档目录](README.md) · [English](getting-started.en.md)

## 选择版本

3.1.0 源码已合入 `main`。当前正式整合包为 **v3.0.0**，不包含 3.1.0 更新；3.1.0 整合包以 [Releases](https://github.com/wochenlong/lora-scripts-next/releases) 实际发布为准。

## Windows 整合包

需要 Windows 10/11 64 位和 NVIDIA 显卡，建议 RTX 20 系列及以上。显存需求随模型、训练目标和配置变化，下载前请查阅对应[训练指南](README.md#training--训练)。

1. 从 [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases) 下载正式包，也可使用发布说明中的镜像。
2. 解压到不含中文和空格的路径；分卷归档需下载全部分卷后解压。
3. lite 包使用 `run_gui.bat`，其他包按包内说明使用启动脚本（如 `启动.bat`）。
4. 按终端提示完成环境准备，在浏览器打开终端显示的地址，默认是 `http://127.0.0.1:28000`。
5. 检查侧栏版本号是否与下载的 Release 一致，再准备模型和数据集。

### 怎么选包

| 包型 | 适用场景 |
| --- | --- |
| lite | 下载体积较小，首次启动需要联网准备依赖 |
| Kohya | 希望使用预装的 Kohya 训练环境 |
| Musubi / Kohya-Musubi | 需要 Musubi 或双引擎环境；以发布页实际提供的资产为准 |

Anima Fast 是可选独立环境，不随上述包默认预装。3.1.0 工作台中可在设置页安装引擎，详见 [Anima Fast](anima-fast.md)。旧包界面可能不同，请按对应版本说明操作。

为兼容旧安装，部分整合包仍保留 `SD-Trainer/` 目录和旧更新脚本名称，不要自行重命名。

## 从源码运行

需要 Git 和 Python 3.10。首次运行需联网安装依赖，训练还需要相应模型、数据集和引擎环境。

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
```

Windows：

```powershell
.\run_gui.bat
```

Linux：

```sh
bash run_gui.sh
```

启动地址以终端输出为准。前端开发、手动环境管理和命令行训练分别见[前端文档](../frontend/README.md)、[仓库布局](repo-layout.md)与 [TOML / CLI](cli-args.md)。

## 分支与更新

| 分支 | 用途 |
| --- | --- |
| `main` | 稳定源码发布线，3.1.0 已合入 |
| `dev` | 下一版本集成与验收，可能包含未发布改动 |
| `legacy/v2.9.1` | 旧 UI 基线 |

整合包用户以正式 Release 和包内更新说明为准，不必手动切换分支。

源码用户可用 `git branch --show-current` 查看分支，用 `git status` 检查本地修改。确认没有需要保留或处理的改动后，在稳定线执行：

```sh
git switch main
git pull --ff-only
```

参与下一版本开发时使用 `git fetch origin` 和 `git switch dev`。不要在未处理本地改动时强制重置工作区。

旧版 TOML 可通过训练页导入；导入后请检查模型、引擎、训练目标和生成配置，不要直接复用旧浏览器存储作为新版本配置。

## 下一步

[界面导览](interface-tour.md) · [模型与训练指南](README.md#training--训练) · [打标模型](tagger-models.md) · [问题反馈](README.md#help-and-credits--反馈与致谢)
