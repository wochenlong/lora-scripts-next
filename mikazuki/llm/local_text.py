"""旧纯文本构造兼容代理，不再安装或启动第二个模型。"""
from .model_manifest import ASSET_ID


class LocalTextModelService:
    def __new__(cls, *_args, **_kwargs):
        from .runtime import get_local_vision_service
        return get_local_vision_service()
