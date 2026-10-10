"""兼容既有视觉入口：安装、翻译、打标共享 Qwen3.5-2B。"""
from .managed_model import ManagedModelService, asset_digest
from .model_manifest import ASSET_ID, FILES, REPOSITORY, REVISION, manifest


class LocalVisionService(ManagedModelService):
    def __init__(self, translation_root, legacy_config_store=None, unified_config_store=None):
        # 接受旧签名，绝不消费旧 local 配置或写其 runtime_path。
        if unified_config_store is None:
            unified_config_store = legacy_config_store
        super().__init__(translation_root, unified_config_store, files=FILES)
