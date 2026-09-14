"""Shared types for the Imagine Router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Source = Literal["imagine", "fallback"]
Aspect = Literal["1:1", "16:9", "9:16"]
Quality = Literal["low", "medium", "auto"]
Resolution = Literal["1k", "2k"]


@dataclass
class GenerationResult:
    """What Sprite Engineer / Dagger get back from the router."""

    image_bytes: bytes
    source: Source
    prompt: str
    aspect_ratio: Aspect
    model: str
    quality: Optional[str] = None
    resolution: Optional[str] = None
    revised_prompt: str = ""
    respect_moderation: Optional[bool] = None
    fallback_reason: Optional[str] = None
    account_id: Optional[str] = None
    cost_usd_estimate: Optional[float] = None
    extra: dict = field(default_factory=dict)

    @property
    def tagged_source(self) -> str:
        return "fallback" if self.source == "fallback" else "imagine"
