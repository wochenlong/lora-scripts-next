"""preflight.py stub — 提交前资产/环境检查。

职责：按 variant 列资产清单（DiT/VAE/TE/...），检查文件存在性、
路径合法性、互斥参数；返回 PreflightResult(ok, errors, warnings)。
输入：adapted values + RuntimeConfig；输出：PreflightResult（as_dict 可序列化）。
完成判据：缺资产时报错明确列出缺什么；误报为零。
参考：mikazuki/engines/musubi/preflight.py。
"""
