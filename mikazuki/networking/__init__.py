"""产品下载网络边界；业务模块从此处获取策略，不更改全局代理。"""
from .policy import NetworkPolicy, resolve_policy, redact

__all__ = ["NetworkPolicy", "resolve_policy", "redact"]
