"""
CLI + library for issue #1.

    python -m pipeline.generate --ref photo.png --character Missy --count 6

Writes {GALLERY_DIR}/{character}/{stamp}/ + manifest.json.
Default backend is `auto` (Imagine → Qwen fallback). No RunPod.
ST / Lumiverse packs are opt-in via --export-st / --export-lumiverse.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from gallery import write_run  # noqa: E402
from imagine_router.types import GenerationResult  # noqa: E402

logger = logging.getLogger("pipeline.generate")


def _load_expressions(preset: str, count: Optional[int]) -> Dict[str, str]:
    try:
        from expressions import ALL_PRESETS
    except ImportError:
        ALL_PRESETS = _builtin_preview_preset()
    mapping = dict(
        ALL_PRESETS.get(preset)
        or ALL_PRESETS.get("full_pack")
        or next(iter(ALL_PRESETS.values()))
    )
    if count is not None and count > 0:
        mapping = dict(list(mapping.items())[:count])
    return mapping


def _builtin_preview_preset() -> Dict[str, Dict[str, str]]:
    return {
        "standard_28": {
            "joy": "Change her expression to a genuine happy smile with bright eyes, keep everything else identical",
            "sadness": "Change expression to soft sadness, slightly downturned eyes and mouth, preserve identity",
            "neutral": "Change to a completely neutral relaxed expression, keep identity",
            "surprise": "Change expression to wide-eyed surprise with slightly open mouth, keep everything else the same",
            "anger": "Change to an angry expression with furrowed brows and intense stare, keep identity identical",
            "calm": "Make her look calm and peaceful with soft eyes and relaxed mouth",
        },
        "full_pack": {
            "joy": "Change her expression to a genuine happy smile with bright eyes, keep everything else identical",
            "neutral": "Change to a completely neutral relaxed expression, keep identity",
            "ahegao_soft": "Change to a soft ahegao-style expression: eyes rolled up slightly, tongue tip out, flushed, keep realistic",
        },
    }


def _mock_result(name: str, prompt: str, ref_bytes: bytes) -> GenerationResult:
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    img = img.resize((512, 512))
    draw = ImageDraw.Draw(img)
    draw.rectangle((8, 8, 504, 56), fill=(20, 20, 20))
    draw.text((16, 18), name, fill=(255, 220, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    source = "fallback" if name in {"ahegao_soft", "afterglow", "lustful"} else "imagine"
    return GenerationResult(
        image_bytes=buf.getvalue(),
        source=source,  # type: ignore[arg-type]
        prompt=prompt,
        aspect_ratio="1:1",
        model="mock",
        fallback_reason="prefilter" if source == "fallback" else None,
        cost_usd_estimate=0.0,
    )


async def generate_run(
    reference_bytes: bytes,
    *,
    character: str = "character",
    preset: str = "standard_28",
    count: Optional[int] = None,
    backend: str = "auto",
    gallery_dir: Optional[Path] = None,
    export_st: bool = False,
    export_lumiverse: bool = False,
    qwen_client=None,
) -> Path:
    mapping = _load_expressions(preset, count)
    results: Dict[str, GenerationResult] = {}

    if backend == "mock":
        for name, prompt in mapping.items():
            results[name] = _mock_result(name, prompt, reference_bytes)
    else:
        from imagine_router import ImagineRouter
        from imagine_router.router import ImagineRouter as Router

        if backend == "qwen":
            if qwen_client is None:
                from qwen_client import QwenImageEditClient

                qwen_client = QwenImageEditClient(hf_token=os.getenv("HF_TOKEN"))
            router = Router(qwen_client=qwen_client)
            for name, prompt in mapping.items():
                results[name] = await router.generate_expression(
                    reference_bytes, prompt, expression_name=name, force_fallback=True
                )
        else:
            if qwen_client is None:
                try:
                    from qwen_client import QwenImageEditClient

                    qwen_client = QwenImageEditClient(hf_token=os.getenv("HF_TOKEN"))
                except Exception as exc:
                    logger.warning("Qwen client unavailable (%s); Imagine-only", exc)
            router = ImagineRouter(qwen_client=qwen_client)
            results = await router.generate_pack(reference_bytes, mapping)

    assets = []
    for name, result in results.items():
        assets.append(
            {
                "name": name,
                "image_bytes": result.image_bytes,
                "source": result.tagged_source,
                "prompt": result.prompt,
                "aspect_ratio": result.aspect_ratio,
                "model": result.model,
                "fallback_reason": result.fallback_reason,
                "cost_usd_estimate": result.cost_usd_estimate,
            }
        )

    extra: Dict[str, object] = {}
    if export_st or export_lumiverse:
        try:
            from packager import create_both_packs, create_lumiverse_charx, create_sillytavern_zip

            img_map = {n: r.image_bytes for n, r in results.items() if r.image_bytes}
            if export_st:
                extra["sillytavern_zip_bytes"] = len(create_sillytavern_zip(img_map, character))
            if export_lumiverse:
                extra["lumiverse_charx_bytes"] = len(create_lumiverse_charx(img_map, character))
            extra["optional_export"] = (
                create_both_packs(img_map, character) if (export_st and export_lumiverse) else None
            )
        except ImportError:
            extra["export_note"] = "packager.py not on path; skipped optional ST/Lumiverse"

    run_dir = write_run(
        character=character,
        assets=assets,
        reference_bytes=reference_bytes,
        preset=preset,
        backend=backend,
        extra={k: v for k, v in extra.items() if k != "optional_export"},
        gallery_dir=gallery_dir,
    )

    if extra.get("optional_export"):
        packs = extra["optional_export"]
        if export_st:
            (run_dir / f"{character}_ST_expressions.zip").write_bytes(packs["sillytavern.zip"])
        if export_lumiverse:
            (run_dir / f"{character}_Lumiverse.charx").write_bytes(packs["lumiverse.charx"])

    return run_dir


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Gallery-first expression run (issue #1)")
    p.add_argument("--ref", required=True, help="Path to the reference image")
    p.add_argument("--character", default="character")
    p.add_argument("--preset", default="standard_28")
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--backend", default="auto", choices=("auto", "imagine", "qwen", "mock"))
    p.add_argument("--gallery-dir", default=None)
    p.add_argument("--export-st", action="store_true")
    p.add_argument("--export-lumiverse", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    ref = Path(args.ref)
    if not ref.exists():
        p.error(f"reference image not found: {ref}")

    run_dir = asyncio.run(
        generate_run(
            ref.read_bytes(),
            character=args.character,
            preset=args.preset,
            count=args.count,
            backend=args.backend,
            gallery_dir=Path(args.gallery_dir) if args.gallery_dir else None,
            export_st=args.export_st,
            export_lumiverse=args.export_lumiverse,
        )
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "ok": manifest["ok"],
                "count": manifest["count"],
                "sources": manifest["sources"],
            },
            indent=2,
        )
    )
    return 0 if manifest["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
