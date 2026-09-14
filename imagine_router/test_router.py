"""Offline unit tests — no API keys, no network."""

from __future__ import annotations

import io
import unittest

from PIL import Image

from imagine_router.aspect import inspect_image, pick_aspect
from imagine_router.moderation import imagine_response_was_filtered, prefilter
from imagine_router.types import GenerationResult


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 80, 120)).save(buf, format="PNG")
    return buf.getvalue()


class AspectTests(unittest.TestCase):
    def test_square(self):
        self.assertEqual(pick_aspect(1024, 1024), "1:1")

    def test_landscape(self):
        self.assertEqual(pick_aspect(1920, 1080), "16:9")

    def test_portrait(self):
        self.assertEqual(pick_aspect(1080, 1920), "9:16")

    def test_inspect(self):
        w, h, aspect = inspect_image(_png(1600, 900))
        self.assertEqual((w, h, aspect), (1600, 900, "16:9"))


class PrefilterTests(unittest.TestCase):
    def test_safe_expression(self):
        self.assertIsNone(prefilter("Change her expression to a warm smile", "joy"))

    def test_nsfw_key_skips_imagine(self):
        self.assertEqual(prefilter("soft look", "ahegao_soft"), "expression:ahegao_soft")

    def test_keyword(self):
        self.assertEqual(prefilter("make her nude and smiling", "neutral"), "keyword")


class ResponseFilterTests(unittest.TestCase):
    def test_respect_moderation_false(self):
        payload = {"data": [{"url": "https://imgen.x.ai/x", "respect_moderation": False}]}
        self.assertEqual(imagine_response_was_filtered(payload), "respect_moderation=false")

    def test_clean(self):
        payload = {"data": [{"url": "https://imgen.x.ai/x", "respect_moderation": True}]}
        self.assertIsNone(imagine_response_was_filtered(payload))


class ResultTagTests(unittest.TestCase):
    def test_fallback_tag(self):
        r = GenerationResult(
            image_bytes=b"x",
            source="fallback",
            prompt="p",
            aspect_ratio="1:1",
            model="qwen-image-edit-nsfw",
            fallback_reason="keyword",
        )
        self.assertEqual(r.tagged_source, "fallback")


if __name__ == "__main__":
    unittest.main()
