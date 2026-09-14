#!/usr/bin/env python3
"""
Missy / Character Expression Pack Generator
===========================================
Powered by jblast94/Qwen-Image-Edit-NSFW

Gallery-first output (issue #1) with Grok Imagine + Qwen fallback (issue #3).
SillyTavern / Lumiverse packs remain available at /api/generate/packs.

Run:
  uvicorn app:app --host 0.0.0.0 --port 7865
  or
  python app.py
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

import gradio as gr
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from expressions import ALL_PRESETS
from packager import create_both_packs
from qwen_client import QwenImageEditClient
from api_gallery import router as gallery_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("expression_pack")

HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
MAX_CONCURRENT = 2

app = FastAPI(
    title="Expression Pack Generator",
    description="Gallery-first expression generator. Imagine primary, Qwen fallback.",
    version="1.1.0",
)

client = QwenImageEditClient(hf_token=HF_TOKEN)
app.include_router(gallery_router)


@app.on_event("shutdown")
async def shutdown():
    await client.close()


class GenerateRequest(BaseModel):
    preset: str = "full_pack"
    steps: int = 4
    guidance: float = 1.0
    character_name: str = "character"
    custom_expressions: Optional[List[str]] = None


OUTPUT_DIR = Path(tempfile.gettempdir()) / "expression_packs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/generate/packs")
async def api_generate_packs(
    file: UploadFile = File(...),
    preset: str = Form("full_pack"),
    steps: int = Form(4),
    guidance: float = Form(1.0),
    character_name: str = Form("character"),
):
    """Optional ST + Lumiverse ZIP export. Default generate path is gallery."""
    ref_bytes = await file.read()
    if not ref_bytes:
        return JSONResponse({"error": "Empty image"}, status_code=400)

    safe_name = "".join(c for c in character_name if c.isalnum() or c in (" ", "-", "_")).strip() or "character"
    safe_name = safe_name.replace(" ", "_")

    mapping = ALL_PRESETS.get(preset, ALL_PRESETS["full_pack"])
    logger.info(f"Pack export {len(mapping)} expressions for '{safe_name}' (preset={preset})")

    results = await client.generate_pack(
        reference_bytes=ref_bytes,
        expressions=mapping,
        steps=steps,
        guidance=guidance,
        max_concurrent=MAX_CONCURRENT,
    )

    packs = create_both_packs(results, character_name=safe_name)
    st_filename = f"{safe_name}_ST_expressions.zip"
    lv_filename = f"{safe_name}_Lumiverse.charx"
    (OUTPUT_DIR / st_filename).write_bytes(packs["sillytavern.zip"])
    (OUTPUT_DIR / lv_filename).write_bytes(packs["lumiverse.charx"])

    return {
        "character": safe_name,
        "expressions_generated": list(results.keys()),
        "count": len([v for v in results.values() if v]),
        "sillytavern_url": f"/api/download/{st_filename}",
        "lumiverse_url": f"/api/download/{lv_filename}",
        "sillytavern_filename": st_filename,
        "lumiverse_filename": lv_filename,
    }


@app.get("/api/download/{filename}")
async def download_pack(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    path = OUTPUT_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    media_type = "application/zip" if filename.endswith(".zip") else "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/presets")
async def list_presets():
    return {name: list(mapping.keys()) for name, mapping in ALL_PRESETS.items()}


async def generate_ui(
    image,
    preset: str,
    character_name: str,
    steps: int,
    guidance: float,
    progress=gr.Progress(track_tqdm=True),
):
    if image is None:
        raise gr.Error("Please upload a reference image first.")

    if hasattr(image, "read"):
        ref_bytes = image.read()
    elif isinstance(image, str):
        ref_bytes = Path(image).read_bytes()
    else:
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.fromarray(image).save(buf, format="PNG")
        ref_bytes = buf.getvalue()

    mapping = ALL_PRESETS.get(preset, ALL_PRESETS["full_pack"])
    total = len(mapping)
    progress(0, desc=f"Starting {total} expressions…")

    results = await client.generate_pack(
        reference_bytes=ref_bytes,
        expressions=mapping,
        steps=int(steps),
        guidance=float(guidance),
        max_concurrent=MAX_CONCURRENT,
    )
    packs = create_both_packs(results, character_name=character_name or "character")

    tmp = Path(tempfile.mkdtemp())
    st_file = tmp / f"{character_name or 'character'}_ST_expressions.zip"
    lv_file = tmp / f"{character_name or 'character'}_Lumiverse.charx"
    st_file.write_bytes(packs["sillytavern.zip"])
    lv_file.write_bytes(packs["lumiverse.charx"])

    success = len([v for v in results.values() if v])
    gallery = [(data, name) for name, data in results.items() if data]
    return gallery, str(st_file), str(lv_file), f"✅ Generated {success}/{total} expressions"


def build_ui():
    with gr.Blocks(
        title="Expression Pack Generator · Qwen-Edit-NSFW",
        theme=gr.themes.Soft(primary_hue="purple"),
        css=".gradio-container {max-width: 1100px !important}",
    ) as demo:
        gr.Markdown(
            """
# Expression Pack Generator
**Powered by** [`jblast94/Qwen-Image-Edit-NSFW`](https://huggingface.co/spaces/jblast94/Qwen-Image-Edit-NSFW)

Default API is gallery-first (`POST /api/generate`). This UI still exports ST + Lumiverse packs.
            """
        )
        with gr.Row():
            with gr.Column(scale=1):
                image_in = gr.Image(label="Reference Image", type="filepath", height=380)
                character_name = gr.Textbox(label="Character Name", value="Missy")
                preset = gr.Dropdown(choices=list(ALL_PRESETS.keys()), value="full_pack", label="Expression Preset")
                with gr.Row():
                    steps = gr.Slider(1, 12, value=4, step=1, label="Inference Steps (4 = fast)")
                    guidance = gr.Slider(0.5, 3.0, value=1.0, step=0.1, label="True Guidance Scale")
                btn = gr.Button("Generate Expression Pack", variant="primary", size="lg")
            with gr.Column(scale=1):
                gallery = gr.Gallery(label="Generated Expressions", columns=4, height=420, object_fit="contain")
                status = gr.Textbox(label="Status", interactive=False)
                st_download = gr.File(label="SillyTavern ZIP (Upload sprite pack)")
                lv_download = gr.File(label="Lumiverse CHARX")
        btn.click(
            fn=generate_ui,
            inputs=[image_in, preset, character_name, steps, guidance],
            outputs=[gallery, st_download, lv_download, status],
        )
    return demo


demo = build_ui()
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7865)
