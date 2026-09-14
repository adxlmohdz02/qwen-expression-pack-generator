# Imagine Router (issue #3)

Grok Imagine client + moderation fallback. No RunPod.

## Routing

1. Local prefilter skips Imagine for known NSFW pack keys.
2. Safe prompts call `grok-imagine-image-2.0` (`quality=medium`, `resolution=1k`).
3. Filtered / policy / `respect_moderation=false` fall through to Qwen HF Space with `source=fallback`.
4. Three xAI keys rotate on 429 (`XAI_API_KEY`, `_2`, `_3`).

```python
from qwen_client import QwenImageEditClient
from imagine_router import ImagineRouter

router = ImagineRouter(qwen_client=QwenImageEditClient(hf_token=HF_TOKEN))
result = await router.generate_expression(ref_bytes, prompt, expression_name="joy")
# result.source == "imagine" | "fallback"
```
