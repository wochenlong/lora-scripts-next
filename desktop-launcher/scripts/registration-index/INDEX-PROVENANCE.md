# GUI 补登记可信索引

本索引用于 wheel 缓存丢失时的只读文件证明，不授权下载、重新安装、任意目录收养或历史健康恢复。它从固定原始归档生成，从未从待恢复的安装树追认文件身份。

- `gui-cp310-installed-files-v2.json`：2,218,268 字节，SHA256 `c5272ed826983913749ff37c00624ec19ccff1d66bda56b0580ddb054879fc82`。
- 固定配方 `gui-cp310-win-x64-v1.json`：SHA256 `00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba`。
- 受管 venv 模板 `gui-cp310-managed-venv-v1.json`：92,079 字节，SHA256 `094072aab658eca999b31784050837afd8804620c776851f857bf2747b208f85`。
- Python 原文件清单 `gui-cp310-python-v1.json`：SHA256 `9172037fe65f76c9fe9373bf3240887889d480a569bfd785d6832e086ab96e06`。
- CPython 原始 tar.gz：22,569,949 字节，SHA256 `b892f2c7eb0a04611688d6df7567a2745a204aac694d6d1c56c75b0717dab2d6`。
- uv 0.11.16 Windows x64 EXE：SHA256 `c5a583d5f1f6d055fc1c32c87d8eceee90edc69a5b9af5da70811befdfc04880`。
- synthetic wheel：SHA256 `34e31a61f350a3e883b7cbff9020842a21c478c3496b0ba69ce84292a1f87795`；完整内容、ZIP 时间、权限与 RECORD 均由 `generate_entrypoint_fixture.py` 确定，无第三方 Python 代码执行。
- 入口 PE 样本：SHA256 `159fbd3f813f417e5718fd8ecaf7a4973925b7b4dca08815f2f225bd06f47632`。全部 27 个固定入口由该模板按受限资源布局重建，并与隔离生成物逐字节核对。

索引含 81 个 wheel 的 12,738 个原文件及每包 license 摘要。许可名称、声明文本身份、许可文件路径/长度/摘要均原样来自已固定配方的 `licenses`；各包许可继续以原 wheel 中的许可文件为准。本索引是身份清单，不重新许可第三方组件。

## 2026-10-30 候选源码身份更新

训练器源码来自已推送提交 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d` 的真实 GitHub codeload ZIP：57,465,913 字节，SHA256 `e53af2a77aa39c1f5e876c5cc73e78329c2cd5c616d0d5af7ac3eea637577022`。在新的构建目录内使用 Node 22.17.1，先尝试已有 npm 缓存离线安装，缺项后通过代理补齐固定 lockfile 对应依赖并编译前端；`frontend.zip` 为 2,446,848 字节，SHA256 `ae77496b39c5b59bb0d4f4ca5b4a3bd3043499818828c0eeeb7227c653996b9f`。完整源码与前端合并清单为 1,844 个文件、103,757,791 字节。

本次逐字节核对 `requirements.txt` 与原配方输入指纹一致，并证明配方中的 Python、uv、wheel、许可和依赖闭包全部保持一致。安装文件索引及受管 venv 模板仅将 `recipe_sha256` 更新为新的父配方摘要；文件列表、每文件长度/摘要、控制文件与模板内容均逐对象比较相同，没有重新生成索引或从安装树追认身份。生成脚本的固定父配方常量同步到本文所列新值。

候选回执、源码复用回执、原身份备份与前端构建日志位于本轮独立沙盒 `full-real-20261030/source-final-5/`。首次 npm 网络中断和离线缓存缺项均保留，首次源码归档逐字节复用，没有再次下载源码。已知源码 ZIP 下载载荷为 57,465,913 字节；npm 补齐包下载量、其他进程网络、TLS/HTTP 开销及实际计费未计量。

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

## 2026-10-30 最终修复源码重新冻结

本轮训练器源码固定到已推送提交 `89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d`，前端由独立新目录 `F:/NextTrainerLauncherSandbox/tb5` 的同一归档使用 Node 22.17.1 / npm 10.9.2 编译。GUI requirements、Python、uv、81 个 wheel 描述符、安装可信文件索引及受管 venv 模板 payload 均逐对象比较相同；仅更新 GUI 父配方与源码/前端身份。独立 Kohya 锁使用同一真实 codeload ZIP，576 个受管训练源码中只改变两个 CLIPImageProcessor 兼容导入文件；两枚固定 wheel 更新为 transformers 5.5.3 与 tokenizers 0.22.2，其余 120 枚 wheel、CPython 和 uv 均保留。外置兼容候选已完成真实 2 步 CUDA LoRA 训练和权重内容核验；本次冻结不是最终启动器安装训练验收，最终包仍须在新空根执行实际下载安装与训练。详细身份、依赖闭包与其他三引擎逐字节不变证明见 `full-real-20261030/source-final-5/freeze-verification.json`。

生成器的父配方常量和入口提取器的 v1 输入固定身份同步更新。原始受信 v1 索引先核对历史 SHA256 `3e0c861b6b4c7e2b9a1a5615193cca976a194e72100aaa1afc54a39065d8bea8`，只替换父配方摘要后得到 SHA256 `740a3a7d93cc04a5323f4805c0ca62963e2f66cb8d5a313464ffb0392bb2ea41`；将该索引与原固定入口控制和 PE 模板组合，按既定序列化逐字节重建当前 v2 索引成功。完整 payload 不变，未执行安装树或入口。

## 2026-10-31 CR-015 引擎冲突协议源码冻结

训练器固定到已推送提交 `4e68df240c63ab7cf2156ea7fafabf18df4671e8`；真实 codeload 源码 ZIP SHA256 `60490c2eceaccb4d59b22f17867b12e68c2a5041b995a3692a38adc6691c0cfd`，92918164 字节。Node 22.17.1 编译得到的前端 ZIP 与原固定前端逐字节相同；requirements、Python、uv、81 枚 wheel、完整安装索引与 venv 模板 payload 不变，仅更新源码及父配方身份。四个独立引擎锁逐字节不变，不从现有安装反向授权。原始 v1 控制索引仅替换父配方后摘要为 `65f615f66dc48da47fdd4a40ab785e4f37ac030d2ea3b63ab4ef4f67ecc18a7f`，生成器/入口提取器同步此身份。首次离线 npm 缺缓存的失败目录 source-v1/tb15 保留；source-v2/tb16 逐字节复用首次源码归档，通过代理补齐固定 npm lock 对应缓存。已知源码实际下载 92918164 字节；npm 补齐下载量与协议开销未计量。证据位于 workspace/tools/launcher-engine-conflicts-20261031/source-v2。本记录只证明构建身份，最终 EXE 安装及服务运行结果另列。
