# Qwen Expression Pack Generator

Standalone **expression-pack** service + SillyTavern extension.

- **Backend**: containerized FastAPI/Gradio — deploy on any Dockhand/Hawser node
- **Frontend**: pure ST extension, installable by **Git URL**
- Reachable over **Tailscale / Docktail** (no localhost coupling to ST)

Powered by [`jblast94/Qwen-Image-Edit-NSFW`](https://huggingface.co/spaces/jblast94/Qwen-Image-Edit-NSFW).

---

## Gallery-first generate (issues #1 / #3)

Default `POST /api/generate` writes a local gallery folder + `manifest.json`.
SillyTavern / Lumiverse packs moved to `POST /api/generate/packs`.

```bash
# QA smoke — no API keys
python -m pipeline.generate --ref photo.png --character Missy --count 6 --backend mock

# Live path (Imagine → Qwen fallback)
export XAI_API_KEY=...
export HF_TOKEN=...          # optional, Qwen fallback
python -m pipeline.generate --ref photo.png --character Missy --count 6 --backend auto
```

Env: `GALLERY_DIR` (default `/data/gallery`), `XAI_API_KEY` / `XAI_API_KEY_2` / `XAI_API_KEY_3`, `HF_TOKEN`.

Backends: `auto` (default) | `imagine` | `qwen` | `mock`.

---

## 1. Deploy the service (any node)

On the machine that should run the generator (`ai1` or a worker):

```bash
git clone https://github.com/Jblast94/qwen-expression-pack-generator.git
cd qwen-expression-pack-generator

export HF_TOKEN=hf_xxxxxxxx   # optional, recommended
export XAI_API_KEY=xai-...    # Imagine primary path

# Standalone stack — does NOT touch SillyTavern
docker compose -f docker-compose.service.yml up -d --build
```

Or import `docker-compose.service.yml` as a stack in **Dockhand** on `ai1` and let Hawser deploy it.

Listens on **7865**. Docktail labels are included:

```yaml
docktail.service.enable=true
docktail.service.name=expression-pack
docktail.service.port=7865
```

---

## 2. Install the SillyTavern extension (Git URL)

In SillyTavern:

**Extensions → Install Extension → Git URL**

```
https://github.com/Jblast94/qwen-expression-pack-generator
```

**Branch: `extension`**

That branch has `manifest.json`, `index.js`, and `style.css` at the **repo root**, so ST installs it like any other third-party extension.

---

## 3. Point the extension at the service

The extension runs **in the browser**. Set **Backend URL** to whatever reaches the container from that browser:

| From | Backend URL |
|------|-------------|
| Same machine as the container | `http://localhost:7865` |
| Another node on Tailscale | `http://<magicdns-or-tailnet-ip>:7865` |
| Via Docktail | `https://expression-pack.<your-docktail-host>` |

Do **not** use `http://expression-pack:7865` — that name only exists on the Docker network, not in the browser.

The ST extension should call `POST /api/generate/packs` if it still wants a ZIP.

---

## API (agents / n8n / Dagger)

```bash
# Gallery (default)
curl -X POST http://<host>:7865/api/generate \
  -F "file=@reference.png" \
  -F "preset=standard_28" \
  -F "character_name=Missy" \
  -F "count=6" \
  -F "backend=auto"

# Old ST + Lumiverse packs
curl -X POST http://<host>:7865/api/generate/packs \
  -F "file=@reference.png" \
  -F "preset=full_pack" \
  -F "character_name=Missy"
```

Presets: `standard_28` | `nsfw_extra` | `full_pack`

---

## Repo layout

```
main branch
├── app.py, qwen_client.py, expressions.py, packager.py, gallery.py, api_gallery.py
├── imagine_router/           ← issue #3
├── pipeline/generate.py      ← issue #1 CLI
├── Dockerfile
├── docker-compose.service.yml
└── st-extension/
```

---

## License

MIT
