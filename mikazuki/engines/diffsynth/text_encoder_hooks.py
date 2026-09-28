"""Contain the temporary capture hook leak in pinned DiffSynth Qwen 2.1.

Only the upstream forward's capture callback is removed. Offload/debug hooks,
including ones added during forward, are left intact. No upstream source edits.
"""
from contextlib import contextmanager
from functools import wraps
from types import MethodType


@contextmanager
def cleanup_text_encoder_hooks(encoder):
    norm = encoder.model.model.language_model.norm
    baseline = set(norm._forward_hooks)
    try:
        yield
    finally:
        for key in set(norm._forward_hooks) - baseline:
            callback = norm._forward_hooks[key]
            if (getattr(callback, '__module__', None) == 'diffsynth.models.qwen_image_21_text_encoder'
                    and getattr(callback, '__qualname__', None) == 'QwenImage21TextEncoder.forward.<locals>.hook_fn'):
                # The pinned upstream registers a plain hook (no kwargs/always_call).
                del norm._forward_hooks[key]


def install_text_encoder_hook_cleanup(encoder):
    if encoder is None or getattr(encoder, '_qwen_capture_cleanup', False):
        return
    forward = encoder.forward

    @wraps(forward)
    def guarded(self, *args, **kwargs):
        with cleanup_text_encoder_hooks(self):
            return forward(*args, **kwargs)

    encoder.forward = MethodType(guarded, encoder)
    encoder._qwen_capture_cleanup = True
