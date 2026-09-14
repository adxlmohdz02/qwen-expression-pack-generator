"""Smart aspect-ratio picker for 16:9 / 9:16 / 1:1."""

from __future__ import annotations

import io
from typing import Tuple

from PIL import Image

from .types import Aspect

_TARGETS: Tuple[Tuple[Aspect, float], ...] = (
    ("16:9", 16 / 9),
    ("9:16", 9 / 16),
    ("1:1", 1.0),
)


def ratio_of(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 1.0
    return width / height


def pick_aspect(width: int, height: int) -> Aspect:
    """Return the nearest of 16:9, 9:16, 1:1."""
    r = ratio_of(width, height)
    best: Aspect = "1:1"
    best_err = float("inf")
    for name, target in _TARGETS:
        err = abs(r - target)
        if err < best_err:
            best_err = err
            best = name
    return best


def inspect_image(image_bytes: bytes) -> Tuple[int, int, Aspect]:
    with Image.open(io.BytesIO(image_bytes)) as im:
        w, h = im.size
    return w, h, pick_aspect(w, h)


def maybe_letterbox_to_aspect(
    image_bytes: bytes,
    aspect: Aspect,
    fill: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """Pad (do not stretch) the reference to the chosen aspect."""
    target_map = {"1:1": (1, 1), "16:9": (16, 9), "9:16": (9, 16)}
    tw, th = target_map[aspect]
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("RGB")
        w, h = im.size
        current = w / h
        target = tw / th
        if abs(current - target) < 0.02:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
        if current > target:
            new_h = w * th // tw
            canvas = Image.new("RGB", (w, new_h), fill)
            canvas.paste(im, (0, (new_h - h) // 2))
        else:
            new_w = h * tw // th
            canvas = Image.new("RGB", (new_w, h), fill)
            canvas.paste(im, ((new_w - w) // 2, 0))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()
