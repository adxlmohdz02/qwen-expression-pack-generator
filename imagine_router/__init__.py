"""
Imagine Router (issue #3)

    from imagine_router import ImagineRouter, generate_expression, configure
"""

from .types import GenerationResult


def __getattr__(name):
    if name in {"ImagineRouter", "configure", "generate_expression"}:
        from . import router as _router
        return getattr(_router, name)
    if name in {"ImagineClient", "ImagineFiltered", "ImagineTransient"}:
        from . import imagine_client as _client
        return getattr(_client, name)
    raise AttributeError(name)


__all__ = [
    "ImagineRouter",
    "ImagineClient",
    "ImagineFiltered",
    "ImagineTransient",
    "GenerationResult",
    "configure",
    "generate_expression",
]
