"""Offline tests for issue #1 gallery mode. No API keys."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gallery import read_manifest, write_run
from pipeline.generate import generate_run


def _png(w: int = 64, h: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


class GalleryWriteTests(unittest.IsolatedAsyncioTestCase):
    def test_write_run_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = write_run(
                character="Missy",
                assets=[
                    {
                        "name": "joy",
                        "image_bytes": _png(),
                        "source": "imagine",
                        "prompt": "smile",
                        "aspect_ratio": "1:1",
                        "model": "grok-imagine-image-2.0",
                    },
                    {
                        "name": "ahegao_soft",
                        "image_bytes": _png(),
                        "source": "fallback",
                        "prompt": "nsfw",
                        "fallback_reason": "expression:ahegao_soft",
                    },
                ],
                reference_bytes=_png(),
                preset="full_pack",
                backend="auto",
                gallery_dir=root,
            )
            self.assertTrue((run / "reference.png").exists())
            self.assertTrue((run / "joy.png").exists())
            man = read_manifest(run)
            self.assertEqual(man["ok"], 2)
            self.assertEqual(man["sources"]["imagine"], 1)
            self.assertEqual(man["sources"]["fallback"], 1)
            self.assertEqual(json.loads((root / "_index.json").read_text())["runs"].__len__(), 1)

    async def test_mock_cli_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = await generate_run(
                _png(128, 128),
                character="Missy",
                preset="full_pack",
                count=3,
                backend="mock",
                gallery_dir=Path(tmp),
            )
            man = read_manifest(run)
            self.assertEqual(man["ok"], 3)
            self.assertTrue((run / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
