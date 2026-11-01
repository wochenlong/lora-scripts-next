# 受控第三方 wheel 构建

此目录保存发行方需要显式修订源码依赖时的最小构建输入。构建产物放在 `desktop-launcher/catalog/engine-wheels/`，由正式配方解析器重新生成依赖闭包和完整文件清单；脚本不安装训练环境，也不修改安装后 METADATA。

`invisible-watermark 0.2.0` 的官方依赖要求 `opencv-python`，与 AI Toolkit 其他包要求的 `opencv-python-headless` 同时安装会覆盖同一个 `cv2` 命名空间。两个包二进制不同，无法同时通过固定原件摘要验证。因此从官方固定提交构建明确的发行方版本 `0.2.0+nexttrainer.1`，只将 `setup.py` 的版本与依赖声明改为 headless；水印运行源码、模型数据及 MIT 许可字节保持不变。

源仓库与提交、原归档大小/SHA、上游 setup.py/许可 SHA 记录在 `invisible-watermark-source.json`。唯一补丁为 `invisible-watermark-headless.patch`。构建依赖固定为既有 M2 使用的 `setuptools==80.9.0`、`wheel==0.45.1`；通过 uv 正常隔离构建，设置固定 `SOURCE_DATE_EPOCH` 和 `PYTHONHASHSEED`。不构建 OpenCV，不下载训练模型，不运行训练。

在仓库根使用既有 Python 和 uv，可执行：

```powershell
python desktop-launcher/scripts/engine-wheels/build_invisible_watermark.py `
  --work-dir E:/临时构建/watermark-build-01 `
  --uv C:/Users/25454/.local/bin/uv.exe `
  --python C:/Python314/python.exe `
  --proxy http://127.0.0.1:11809 `
  --output-dir desktop-launcher/catalog/engine-wheels
```

`--work-dir` 必须不存在，避免覆盖历史证据。可用 `--source-archive` 复用已下载原归档，仍核对固定摘要；可用 `--cache-dir` 复用构建工具缓存。下载只接受固定 URL 及大小/SHA，不接受任意轮换上游。正式输出存在不同字节同名 wheel 时拒绝覆盖。

每次构建生成 `provenance.json` 和 stdout/stderr 日志，记录源文件/补丁/构建依赖/工具及产物身份；逐字节核对 wheel 中每个上游 `imwatermark/` 文件与原源码一致，保留原 LICENSE，并重算整个 wheel RECORD。`invisible-watermark-provenance.json` 保存当前登记产物的实际构建记录。重新构建后必须比较产物摘要；不能因版本相同自动接受不同字节。

当前登记的 `invisible_watermark-0.2.0+nexttrainer.1-py3-none-any.whl` 大小为 1,632,289 字节，SHA256 为 `5f376371aa1d93a4d699ab5b2e5b495a6a658d21cb2aef8625a3ad636872a8f2`；两个全新源码构建目录的产物逐字节相同。脚本会强制验证此固定大小与摘要，同时核对 7 个上游运行源码/模型文件及原 MIT 许可；不修改构建完成的 wheel 元数据。

新 wheel 是 NextTrainer 发行方依赖修订产物，不代表上游发布了该本地版本；上游来源为 [ShieldMnt/invisible-watermark](https://github.com/ShieldMnt/invisible-watermark)，保留原作者及 MIT 许可。依赖锁和完整安装验收由配方生成流程负责；单独构建成功不等于 AI Toolkit 完整安装通过。
