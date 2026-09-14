"""Decide whether a prompt should skip Imagine and go straight to Qwen."""

from __future__ import annotations

import re
from typing import Optional

NSFW_EXPRESSION_KEYS = {
    "desire",
    "arousal",
    "flirty",
    "seductive",
    "teasing",
    "lustful",
    "bliss",
    "needy",
    "dominant",
    "submissive",
    "ahegao_soft",
    "afterglow",
}

_KEYWORD_RE = re.compile(
    r"\b("
    r"nsfw|nude|naked|topless|bottomless|explicit|porn|"
    r"ahegao|afterglow|orgasm|cum|sex|sexual|erotic|"
    r"fellatio|blowjob|handjob|penetration|genitals?|"
    r"penis|vagina|pussy|cock|tits|boobs|breasts? exposed"
    r")\b",
    re.IGNORECASE,
)

_POLICY_HINTS = (
    "content policy",
    "safety",
    "moderat",
    "filtered",
    "not allowed",
    "disallowed",
    "violat",
    "refused",
    "blocked",
    "nsfw",
    "adult content",
    "sexual content",
)


def prefilter(prompt: str, expression_name: Optional[str] = None) -> Optional[str]:
    if expression_name and expression_name.lower() in NSFW_EXPRESSION_KEYS:
        return f"expression:{expression_name.lower()}"
    if prompt and _KEYWORD_RE.search(prompt):
        return "keyword"
    return None


def imagine_response_was_filtered(payload: dict) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or err.get("code") or "").lower()
        if any(h in msg for h in _POLICY_HINTS):
            return f"api_error:{err.get('code') or 'policy'}"
    if isinstance(err, str) and any(h in err.lower() for h in _POLICY_HINTS):
        return "api_error:policy"
    data = payload.get("data") or []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("respect_moderation") is False:
                return "respect_moderation=false"
            if not item.get("url") and not item.get("b64_json") and not item.get("base64"):
                note = str(item.get("revised_prompt") or item.get("error") or "").lower()
                if any(h in note for h in _POLICY_HINTS):
                    return "empty_image:moderated"
    return None


def http_status_looks_filtered(status: int, body_text: str) -> bool:
    if status in (400, 403, 422):
        low = (body_text or "").lower()
        return any(h in low for h in _POLICY_HINTS)
    return False
