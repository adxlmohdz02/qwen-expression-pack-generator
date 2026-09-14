"""
Plain-Python client for grok-imagine-image-2.0.

Uses httpx + application/json (OpenAI SDK images.edit() is multipart and
is explicitly unsupported by xAI). No xai_sdk dependency, no RunPod.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional, Tuple

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .aspect import inspect_image
from .moderation import http_status_looks_filtered, imagine_response_was_filtered
from .rate_pool import RatePool
from .types import Aspect, Quality, Resolution

logger = logging.getLogger("imagine_router.client")

API_BASE = "https://api.x.ai/v1"
MODEL = "grok-imagine-image-2.0"

COST_1K_LOW_EDIT = 0.05
COST_1K_MED_EDIT = 0.07
COST_2K_LOW_EDIT = 0.07
COST_2K_MED_EDIT = 0.09


class ImagineFiltered(Exception):
    """Imagine refused or filtered the request. Router should fall back."""

    def __init__(self, reason: str, status: Optional[int] = None, body: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.body = body


class ImagineTransient(Exception):
    """429 / 5xx — retry or rotate keys."""


class ImagineClient:
    def __init__(
        self,
        pool: Optional[RatePool] = None,
        timeout: float = 120.0,
        model: str = MODEL,
        quality: Quality = "medium",
        resolution: Resolution = "1k",
    ):
        self.pool = pool if pool is not None else RatePool()
        self.timeout = timeout
        self.model = model
        self.quality = quality
        self.resolution = resolution
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=20.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._http.aclose()

    def estimate_cost(self, quality: Optional[str] = None, resolution: Optional[str] = None) -> float:
        q = (quality or self.quality or "medium").lower()
        r = (resolution or self.resolution or "1k").lower()
        if r == "2k" and q == "medium":
            return COST_2K_MED_EDIT
        if r == "2k":
            return COST_2K_LOW_EDIT
        if q == "medium":
            return COST_1K_MED_EDIT
        return COST_1K_LOW_EDIT

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=12),
        retry=retry_if_exception_type(ImagineTransient),
        reraise=True,
    )
    async def edit(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        aspect_ratio: Optional[Aspect] = None,
        quality: Optional[Quality] = None,
        resolution: Optional[Resolution] = None,
        mime: str = "image/png",
    ) -> Tuple[bytes, Dict[str, Any]]:
        if not image_bytes:
            raise ValueError("empty reference image")
        if not prompt or not prompt.strip():
            raise ValueError("empty prompt")

        w, h, detected = inspect_image(image_bytes)
        aspect = aspect_ratio or detected
        q = quality or self.quality
        res = resolution or self.resolution

        data_uri = _to_data_uri(image_bytes, mime)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "image": {"url": data_uri, "type": "image_url"},
            "aspect_ratio": aspect,
            "resolution": res,
            "quality": q,
            "n": 1,
            "response_format": "url",
        }

        acct = self.pool.next()
        headers = {
            "Authorization": f"Bearer {acct.key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "Imagine edit acct=%s aspect=%s (%dx%d) q=%s res=%s",
            acct.id, aspect, w, h, q, res,
        )

        try:
            resp = await self._http.post(
                f"{API_BASE}/images/edits",
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ImagineTransient(str(exc)) from exc

        if resp.status_code == 429:
            retry_after = _retry_after(resp)
            self.pool.mark_rate_limited(acct, retry_after)
            raise ImagineTransient(f"{acct.id} 429")

        if http_status_looks_filtered(resp.status_code, resp.text):
            raise ImagineFiltered(
                f"http_{resp.status_code}:policy",
                status=resp.status_code,
                body=resp.text[:500],
            )

        if resp.status_code >= 500:
            raise ImagineTransient(f"http_{resp.status_code}")

        if resp.status_code >= 400:
            raise RuntimeError(f"Imagine HTTP {resp.status_code}: {resp.text[:400]}")

        body = resp.json()
        filtered = imagine_response_was_filtered(body)
        if filtered:
            raise ImagineFiltered(filtered, status=resp.status_code, body=resp.text[:500])

        image_bytes_out, item = await self._download_first(body)
        self.pool.mark_ok(acct)

        meta = {
            "account_id": acct.id,
            "aspect_ratio": aspect,
            "quality": q,
            "resolution": res,
            "model": self.model,
            "input_size": (w, h),
            "respect_moderation": item.get("respect_moderation"),
            "revised_prompt": item.get("revised_prompt") or "",
            "usage": body.get("usage") or {},
            "source_url": item.get("url"),
        }
        return image_bytes_out, meta

    async def _download_first(self, body: dict) -> Tuple[bytes, dict]:
        data = body.get("data") or []
        if not data:
            raise RuntimeError(f"Imagine returned no data: {body!r}"[:400])
        item = data[0] if isinstance(data[0], dict) else {}
        b64 = item.get("b64_json") or item.get("base64")
        if b64:
            return base64.b64decode(b64), item
        url = item.get("url")
        if not url:
            raise ImagineFiltered("empty_image", body=str(item)[:400])
        img = await self._http.get(url)
        img.raise_for_status()
        return img.content, item


def _to_data_uri(image_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _retry_after(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
