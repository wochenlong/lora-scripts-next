"""验证固定 GUI 环境的解释器、依赖闭包与关键导入；由受控子进程执行。"""
import importlib
import json
import pathlib
import re
import sys
from importlib.metadata import distributions


base = pathlib.Path(sys.argv[1]).resolve()
environment = pathlib.Path(sys.argv[2]).resolve()
expected = json.loads(sys.argv[3])
assert sys.version.split()[0] == "3.10.19", sys.version
assert pathlib.Path(sys.base_prefix).resolve() == base.parent, sys.base_prefix
assert pathlib.Path(sys._base_executable).resolve() == base, sys._base_executable
assert pathlib.Path(sys.prefix).resolve() == environment, sys.prefix
installed = list(distributions())
assert all(
    pathlib.Path(distribution.locate_file("")).resolve().is_relative_to(environment)
    for distribution in installed
), "发现环境之外的包"
actual = {
    re.sub("[-_.]+", "-", distribution.metadata["Name"]).lower(): distribution.version
    for distribution in installed
}
assert len(installed) == len(actual) and actual == expected, (actual, expected)
for name in (
    "pip", "fastapi", "uvicorn", "toml", "numpy", "onnxruntime", "psutil",
    "pandas", "PIL", "cv2", "tensorboard", "rich", "requests", "httpx",
    "aiohttp", "websockets", "multipart", "modelscope", "cryptography",
    "huggingface_hub", "pynvml",
):
    importlib.import_module(name)
print("GUI fixed recipe import/ownership passed")
