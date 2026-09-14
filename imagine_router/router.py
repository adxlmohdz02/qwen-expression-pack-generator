"""
Imagine Router — the function Sprite Engineer and Dagger call.

Routing rule (MASTER_PIPELINE_PLAN v1.2 + issue #3):
  safe prompt     → grok-imagine-image-2.0
  filtered/NSFW   → Qwen HF Space, tag source=fallback
  no RunPod
"""

from __future__ import annotations

import logging
from typing import Optional

from .aspect import inspect_image
from .imagine_client import ImagineClient, ImagineFiltered, ImagineTransient
from .moderation import prefilter
from .rate_pool import RatePool
from .types import Aspect, GenerationResult, Quality, Resolution

logger = logging.getLogger("imagine_router")


class ImagineRouter:
    def __init__(
        self,
        imagine: Optional[ImagineClient] = None,
        qwen_client=None,
        pool: Optional[RatePool] = None,
        quality: Quality = "medium",
        resolution: Resolution = "1k",
    ):
        self.pool = pool
        self.imagine = imagine or ImagineClient(
            pool=pool, quality=quality, resolution=resolution
        )
        self.qwen = qwen_client
        self.quality = quality
        self.resolution = resolution

    async def close(self) -> None:
        await self.imagine.close()
        closer = getattr(self.qwen, "close", None)
        if closer:
            await closer()

    async def generate_expression(
        self,
        reference_bytes: bytes,
        prompt: str,
        *,
        expression_name: Optional[str] = None,
        aspect_ratio: Optional[Aspect] = None,
        force_fallback: bool = False,
        qwen_steps: int = 4,
        qwen_guidance: float = 1.0,
    ) -> GenerationResult:
        _, _, detected = inspect_image(reference_bytes)
        aspect: Aspect = aspect_ratio or detected

        reason = "forced" if force_fallback else prefilter(prompt, expression_name)
        if reason:
            logger.info("Prefilter → Qwen (%s)", reason)
            return await self._fallback(
                reference_bytes, prompt, aspect,
                reason=reason,
                expression_name=expression_name,
                steps=qwen_steps,
                guidance=qwen_guidance,
            )

        try:
            image, meta = await self.imagine.edit(
                reference_bytes,
                prompt,
                aspect_ratio=aspect,
                quality=self.quality,
                resolution=self.resolution,
            )
            return GenerationResult(
                image_bytes=image,
                source="imagine",
                prompt=prompt,
                aspect_ratio=meta.get("aspect_ratio") or aspect,
                model=meta.get("model") or "grok-imagine-image-2.0",
                quality=meta.get("quality"),
                resolution=meta.get("resolution"),
                revised_prompt=meta.get("revised_prompt") or "",
                respect_moderation=meta.get("respect_moderation"),
                account_id=meta.get("account_id"),
                cost_usd_estimate=self.imagine.estimate_cost(
                    meta.get("quality"), meta.get("resolution")
                ),
                extra={"input_size": meta.get("input_size"), "usage": meta.get("usage")},
            )
        except ImagineFiltered as exc:
            logger.info("Imagine filtered (%s) → Qwen", exc.reason)
            return await self._fallback(
                reference_bytes, prompt, aspect,
                reason=exc.reason,
                expression_name=expression_name,
                steps=qwen_steps,
                guidance=qwen_guidance,
            )
        except ImagineTransient as exc:
            logger.warning("Imagine transient after retries (%s) → Qwen", exc)
            return await self._fallback(
                reference_bytes, prompt, aspect,
                reason=f"transient:{exc}",
                expression_name=expression_name,
                steps=qwen_steps,
                guidance=qwen_guidance,
            )

    async def generate_pack(
        self,
        reference_bytes: bytes,
        expressions: dict,
        *,
        max_concurrent: int = 2,
    ) -> dict:
        import asyncio

        sem = asyncio.Semaphore(max_concurrent)
        out: dict = {}

        async def _one(name: str, prompt: str):
            async with sem:
                try:
                    out[name] = await self.generate_expression(
                        reference_bytes, prompt, expression_name=name
                    )
                except Exception as exc:
                    logger.error("✗ %s: %s", name, exc)
                    out[name] = GenerationResult(
                        image_bytes=b"",
                        source="fallback",
                        prompt=prompt,
                        aspect_ratio="1:1",
                        model="none",
                        fallback_reason=str(exc),
                    )

        await asyncio.gather(*[_one(n, p) for n, p in expressions.items()])
        return out

    async def _fallback(
        self,
        reference_bytes: bytes,
        prompt: str,
        aspect: Aspect,
        *,
        reason: str,
        expression_name: Optional[str],
        steps: int,
        guidance: float,
    ) -> GenerationResult:
        if self.qwen is None:
            raise RuntimeError(
                f"Imagine filtered ({reason}) but no Qwen client was wired. "
                "Pass qwen_client=QwenImageEditClient(...) to ImagineRouter."
            )
        logger.info("Qwen fallback expression=%s reason=%s", expression_name, reason)
        image, seed = await self.qwen.edit(
            image_bytes=reference_bytes,
            prompt=prompt,
            num_inference_steps=steps,
            true_guidance_scale=guidance,
            randomize_seed=True,
        )
        return GenerationResult(
            image_bytes=image,
            source="fallback",
            prompt=prompt,
            aspect_ratio=aspect,
            model="qwen-image-edit-nsfw",
            fallback_reason=reason,
            extra={"seed": seed, "source": "fallback"},
        )


_default: Optional[ImagineRouter] = None


def configure(router: ImagineRouter) -> ImagineRouter:
    global _default
    _default = router
    return router


async def generate_expression(
    reference_bytes: bytes,
    prompt: str,
    **kwargs,
) -> GenerationResult:
    if _default is None:
        raise RuntimeError("Call imagine_router.configure(ImagineRouter(...)) first.")
    return await _default.generate_expression(reference_bytes, prompt, **kwargs)
