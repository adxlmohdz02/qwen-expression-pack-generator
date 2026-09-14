"""FastAPI handlers for gallery-first /api/generate (issue #1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from gallery import DEFAULT_GALLERY_DIR, read_manifest
from pipeline.generate import generate_run

router = APIRouter()
GALLERY_DIR = Path(os.getenv("GALLERY_DIR") or DEFAULT_GALLERY_DIR)


@router.post("/api/generate")
async def api_generate(
    file: UploadFile = File(...),
    preset: str = Form("standard_28"),
    character_name: str = Form("character"),
    count: int = Form(6),
    backend: str = Form("auto"),
    export_st: bool = Form(False),
    export_lumiverse: bool = Form(False),
    steps: int = Form(4),
    guidance: float = Form(1.0),
):
    del steps, guidance
    ref_bytes = await file.read()
    if not ref_bytes:
        return JSONResponse({"error": "Empty image"}, status_code=400)
    if backend not in {"auto", "imagine", "qwen", "mock"}:
        return JSONResponse({"error": f"unknown backend {backend}"}, status_code=400)

    run_dir = await generate_run(
        ref_bytes,
        character=character_name,
        preset=preset,
        count=count if count > 0 else None,
        backend=backend,
        gallery_dir=GALLERY_DIR,
        export_st=export_st,
        export_lumiverse=export_lumiverse,
    )
    manifest = read_manifest(run_dir)
    payload = {
        "character": manifest["character"],
        "run_dir": str(run_dir),
        "manifest_url": f"/api/gallery/file?path={run_dir / 'manifest.json'}",
        "count": manifest["count"],
        "ok": manifest["ok"],
        "sources": manifest["sources"],
        "backend": manifest["backend"],
        "assets": manifest["assets"],
        "post": manifest["post"],
    }
    if export_st:
        payload["sillytavern_filename"] = f"{character_name}_ST_expressions.zip"
    if export_lumiverse:
        payload["lumiverse_filename"] = f"{character_name}_Lumiverse.charx"
    return payload


@router.get("/api/gallery/manifest")
async def latest_hint(character: Optional[str] = None):
    index = GALLERY_DIR / "_index.json"
    if not index.exists():
        return {"runs": []}
    import json

    catalog = json.loads(index.read_text())
    runs = catalog.get("runs") or []
    if character:
        runs = [r for r in runs if r.get("character") == character]
    return {"runs": runs[-20:], "gallery_dir": str(GALLERY_DIR)}


@router.get("/api/gallery/file")
async def gallery_file(path: str):
    target = Path(path).resolve()
    root = GALLERY_DIR.resolve()
    if root not in target.parents and target != root:
        return JSONResponse({"error": "path outside gallery"}, status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(target)
