# Expression Pack Generator – multi-stage, uv-based
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache -r requirements.txt

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GALLERY_DIR=/data/gallery

COPY app.py expressions.py packager.py qwen_client.py gallery.py api_gallery.py ./
COPY imagine_router ./imagine_router
COPY pipeline ./pipeline

EXPOSE 7865

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:7865/api/presets || exit 1

CMD ["python", "app.py"]
