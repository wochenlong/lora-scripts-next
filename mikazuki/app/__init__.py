"""Load the ASGI application only when requested by the launcher.

Importing config or response models must not initialize all API routers; that
created import cycles when shared LLM jobs checked the dataset in-use guard.
"""


def __getattr__(name):
    if name == "app":
        from .application import app
        return app
    raise AttributeError(name)
