"""Round-robin key pool across the three X / xAI accounts."""

from __future__ import annotations

import itertools
import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("imagine_router.rate_pool")


@dataclass
class Account:
    id: str
    key: str
    cooldown_until: float = 0.0
    failures: int = 0

    @property
    def available(self) -> bool:
        return time.time() >= self.cooldown_until


class RatePool:
    def __init__(self, keys: Optional[List[str]] = None, cooldown_seconds: float = 8.0):
        resolved = keys if keys is not None else _load_keys_from_env()
        if not resolved:
            raise RuntimeError(
                "No xAI keys found. Set XAI_API_KEY (and optionally "
                "XAI_API_KEY_2 / XAI_API_KEY_3 or XAI_API_KEYS)."
            )
        self.accounts = [Account(id=f"acct-{i+1}", key=k) for i, k in enumerate(resolved)]
        self._cycle = itertools.cycle(self.accounts)
        self.cooldown_seconds = cooldown_seconds

    def next(self) -> Account:
        n = len(self.accounts)
        first_available: Optional[Account] = None
        soonest: Optional[Account] = None
        for _ in range(n * 2):
            acct = next(self._cycle)
            if soonest is None or acct.cooldown_until < soonest.cooldown_until:
                soonest = acct
            if acct.available:
                first_available = acct
                break
        if first_available:
            return first_available
        assert soonest is not None
        wait = max(0.0, soonest.cooldown_until - time.time())
        logger.warning("All %d Imagine keys cooling down (%.1fs)", n, wait)
        return soonest

    def mark_rate_limited(self, acct: Account, retry_after: Optional[float] = None) -> None:
        wait = self.cooldown_seconds if retry_after is None else max(retry_after, 1.0)
        acct.cooldown_until = time.time() + wait
        acct.failures += 1
        logger.info("%s rate-limited, cooldown %.1fs", acct.id, wait)

    def mark_ok(self, acct: Account) -> None:
        acct.failures = 0
        acct.cooldown_until = 0.0


def _load_keys_from_env() -> List[str]:
    keys: List[str] = []
    blob = os.getenv("XAI_API_KEYS", "")
    if blob.strip():
        keys.extend(k.strip() for k in blob.split(",") if k.strip())
    for name in ("XAI_API_KEY", "XAI_API_KEY_2", "XAI_API_KEY_3"):
        val = (os.getenv(name) or "").strip()
        if val:
            keys.append(val)
    seen = set()
    unique: List[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique
