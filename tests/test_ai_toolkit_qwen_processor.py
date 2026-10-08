from types import SimpleNamespace

from mikazuki.engines.ai_toolkit.driver import preserve_qwen_reference_size


def test_qwen_processor_keeps_already_prepared_reference_dimensions():
    calls = []

    class Encoder:
        @classmethod
        def load_processor(cls, path, **kwargs):
            calls.append((path, kwargs))
            return SimpleNamespace(image_processor=SimpleNamespace(do_resize=True))

    class OtherEncoder(Encoder):
        pass

    preserve_qwen_reference_size(OtherEncoder)
    processor = OtherEncoder.load_processor("local/config", local_files_only=True)

    assert processor.image_processor.do_resize is False
    assert calls == [("local/config", {"local_files_only": True})]
    assert Encoder.load_processor("local/config").image_processor.do_resize is True
