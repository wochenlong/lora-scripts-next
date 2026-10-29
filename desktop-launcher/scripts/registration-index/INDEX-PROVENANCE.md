# GUI 补登记可信索引

本索引用于 wheel 缓存丢失时的只读文件证明，不授权下载、重新安装、任意目录收养或历史健康恢复。它从固定原始归档生成，从未从待恢复的安装树追认文件身份。

- `gui-cp310-installed-files-v2.json`：2,218,268 字节，SHA256 `6ef8a9b844b1dd7e9294be5ae30b70420e703127fc0d999a7eb8096c114ffd90`。
- 固定配方 `gui-cp310-win-x64-v1.json`：SHA256 `8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090`。
- Python 原文件清单 `gui-cp310-python-v1.json`：SHA256 `9172037fe65f76c9fe9373bf3240887889d480a569bfd785d6832e086ab96e06`。
- CPython 原始 tar.gz：22,569,949 字节，SHA256 `b892f2c7eb0a04611688d6df7567a2745a204aac694d6d1c56c75b0717dab2d6`。
- uv 0.11.16 Windows x64 EXE：SHA256 `c5a583d5f1f6d055fc1c32c87d8eceee90edc69a5b9af5da70811befdfc04880`。
- synthetic wheel：SHA256 `34e31a61f350a3e883b7cbff9020842a21c478c3496b0ba69ce84292a1f87795`；完整内容、ZIP 时间、权限与 RECORD 均由 `generate_entrypoint_fixture.py` 确定，无第三方 Python 代码执行。
- 入口 PE 样本：SHA256 `159fbd3f813f417e5718fd8ecaf7a4973925b7b4dca08815f2f225bd06f47632`。全部 27 个固定入口由该模板按受限资源布局重建，并与隔离生成物逐字节核对。

索引含 81 个 wheel 的 12,738 个原文件及每包 license 摘要。许可名称、声明文本身份、许可文件路径/长度/摘要均原样来自已固定配方的 `licenses`；各包许可继续以原 wheel 中的许可文件为准。本索引是身份清单，不重新许可第三方组件。

生产验证对 wheel 原文件逐摘要、uv 固定控制逐摘要、activation 逐模板、pyvenv.cfg 逐归属、入口 EXE 逐字节重建；本地 RECORD 只能记账，不可扩写信任闭包。未知执行文件、`.pth`、派生 `.pyc`、链接和大小写别名均被拒绝，原文件保留。INSTALLER 必须等于 `uv`，REQUESTED 必须为空；可选 direct_url/uv_cache 只允许限额 JSON 对象，不作为代码或身份依据。

## 可重复生成

使用一份新的 Windows 隔离工作目录，准备全部按配方 SHA 固定的 81 wheel 原归档、上述 CPython 原 tar.gz 和 uv EXE。脚本默认控制路径与首次审查保持一致，若路径已存在会拒绝覆盖，请先在独立机器/快照复现；不要删除既有安装内容。

1. 执行 `generate_trusted_index.py`。参数 `--recipe`、`--python-manifest`、`--python-archive`、`--uv`、`--wheelhouse` 指向固定原素材；`--control-base E:\NTRegCtrl\a5-20261029-ctrl1\base`、`--control E:\NTRegCtrl\a5-20261029-ctrl1\g0000000000000000`；`--output` 指向脚本同目录的 `gui-cp310-installed-files-v1.json`。脚本逐 tar/wheel 原文件读取核验，只运行固定 uv 的 offline venv，不运行实际 GUI 依赖。
2. `generate_entrypoint_fixture.py` 中 UV 路径可改为同 SHA EXE 的位置；CONTROL 保持上述固定短路径。运行脚本，只安装完全指定的 synthetic 小 wheel，固定 uv 全程 offline，所有入口均不执行。日志与 fixture 保留。
3. 运行 `extract_entrypoint_controls.py`。固定核对 v1 输入、固定 PE 样本、固定 ZIP 封套、全部 27 个入口重建。输出应逐字节等于生产 v2 索引，其 SHA 为本文开头固定值。

若更换了控制 fixture 的绝对路径，v1 的示例字节长度/摘要和 v2 内 PE 样本也随之改变，不能直接以新 SHA 替换生产信任根；须按同一审查流程重建、核对完整内容与更新 Rust 固定 SHA。生产模板验证会将已安装环境路径替换进去，不要求用户安装在示例 E 路径。

本轮只证明索引构建与程序逻辑；完整真实安装恢复仍由主流程按独立原生案例验收。首次旧 E Python 全树验证失败、深路径提取失败、旧尾部 shebang 解析失败均保留在外部证据目录，未转写为成功。

## uv 首次安装生成的运行时锁

登记恢复的首个原生案例因环境根 `.lock` 未列入空 venv 的控制索引而安全拒绝，原失败回执保留。随后使用相同固定 uv EXE、经 4,184 个原文件验证的 CPython，以及上述固定 synthetic wheel，在新的隔离 E 目录离线复现：`uv venv` 后锁不存在；首次离线 `uv pip install` 后生成普通、无 reparse、0 字节的环境根 `.lock`，SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；离线 `pip check` 后原字节保持。

固定 v2 原索引不改。Rust 验证器单独接受**可选、精确环境根路径的空 `.lock` 普通文件**，将其纳入本次完整闭包摘要；非空、目录、链接、嵌套锁、其他隐藏文件和大小写别名均不扩展授信。独立复现证据 `uv-lock-reproduction-evidence.json` SHA256 为 `825dae0fc878b9e6b1c478f8fdb97c1b89b18444a56bb75a43557e02c9b4100e`，保存在当前运行的外部 `M1/recipe/gui-registration-working/`；生产安装树只作失败诊断，没有被用作控制文件的信任来源。
