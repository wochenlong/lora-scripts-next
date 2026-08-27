"""extension_state.py stub — 安装状态机。

职责：定义 ExtensionLayout（extensions/<id>/ 下的 source/.venv/state 文件）、
状态枚举（not_installed/installing/installed_unverified/ready/broken）、
read/write_install_state（JSON 持久化，含 facts/audit/message）。
输入：项目根 Path；输出：ExtensionLayout + status dataclass（as_dict）。
完成判据：状态读写往返一致；status 路由能原样返回。
参考：mikazuki/engines/anima_fast/extension_state.py。
"""
