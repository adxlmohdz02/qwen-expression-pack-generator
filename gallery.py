"""Simple local gallery (issue #1 / #2)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _default_gallery_root() -> str:
    for candidate in ("/data/gallery", "/tmp/gallery"):
        parent = Path(candidate).parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if os.access(parent, os.W_OK):
                return candidate
        except OSError:
            continue
    return str(Path(tempfile.gettempdir()) / "gallery")


DEFAULT_GALLERY_DIR = Path(os.getenv("GALLERY_DIR") or _default_gallery_root())


def safe_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "character").strip())
    return slug.strip("._") or "character"


def new_run_dir(character: str, gallery_dir: Optional[Path] = None) -> Path:
    root = Path(gallery_dir or DEFAULT_GALLERY_DIR)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / safe_slug(character) / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_png(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def write_run(
    *,
    character: str,
    assets: Iterable[Dict[str, Any]],
    reference_bytes: Optional[bytes] = None,
    preset: str = "full_pack",
    backend: str = "auto",
    extra: Optional[Dict[str, Any]] = None,
    gallery_dir: Optional[Path] = None,
) -> Path:
    run_dir = new_run_dir(character, gallery_dir)
    written: List[Dict[str, Any]] = []

    if reference_bytes:
        write_png(run_dir / "reference.png", reference_bytes)

    for asset in assets:
        name = safe_slug(str(asset.get("name") or "asset")).lower()
        blob = asset.get("image_bytes") or b""
        filename = f"{name}.png"
        if blob:
            write_png(run_dir / filename, blob)
        written.append(
            {
                "name": name,
                "file": filename if blob else None,
                "source": asset.get("source") or "unknown",
                "prompt": asset.get("prompt") or "",
                "aspect_ratio": asset.get("aspect_ratio"),
                "model": asset.get("model"),
                "fallback_reason": asset.get("fallback_reason"),
                "cost_usd_estimate": asset.get("cost_usd_estimate"),
                "bytes": len(blob),
            }
        )

    manifest = {
        "character": character,
        "preset": preset,
        "backend": backend,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "count": len(written),
        "ok": sum(1 for a in written if a["bytes"] > 0),
        "sources": _count_sources(written),
        "assets": written,
        "post": {
            "caption_draft": "",
            "status": "pending",
            "note": "basic post data placeholder — copywriter / Eliza later",
        },
        "extra": extra or {},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _update_index(Path(gallery_dir or DEFAULT_GALLERY_DIR), manifest)
    return run_dir


def read_manifest(run_dir: Path) -> Dict[str, Any]:
    return json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))


def _count_sources(assets: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for a in assets:
        src = a.get("source") or "unknown"
        out[src] = out.get(src, 0) + 1
    return out


def _update_index(root: Path, manifest: Dict[str, Any]) -> None:
    index_path = root / "_index.json"
    try:
        catalog = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"runs": []}
    except json.JSONDecodeError:
        catalog = {"runs": []}
    catalog.setdefault("runs", []).append(
        {
            "character": manifest["character"],
            "created_at": manifest["created_at"],
            "run_dir": manifest["run_dir"],
            "count": manifest["count"],
            "ok": manifest["ok"],
            "sources": manifest["sources"],
            "backend": manifest["backend"],
        }
    )
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
