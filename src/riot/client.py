"""Rate-limited, cached, retry-aware Riot API client.

Riot enforces limits *per routing value* (na1, euw1, americas...), so buckets are
keyed by host rather than shared globally. Development-key limits:

    20 requests / 1 second
    100 requests / 120 seconds

The 100/2min bucket is the real ceiling; the burst bucket rarely binds. Both are
enforced here so that promoting a development key to a production key is a matter
of changing the limit table, not the call sites.
"""

from __future__ import annotations

import os
import time
import json
import hashlib
import logging
import threading
from pathlib import Path
from collections import deque
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEV_LIMITS = [(20, 1.0), (100, 120.0)]  # (requests, window_seconds)
CACHE_DIR = Path("data/cache")


class SlidingWindowLimiter:
    """Multi-bucket sliding-window limiter. Blocks until every bucket has room."""

    def __init__(self, limits: list[tuple[int, float]]):
        self._limits = limits
        self._hits: list[deque[float]] = [deque() for _ in limits]
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                wait = 0.0
                for (cap, window), hits in zip(self._limits, self._hits):
                    while hits and now - hits[0] >= window:
                        hits.popleft()
                    if len(hits) >= cap:
                        wait = max(wait, window - (now - hits[0]))
                if wait <= 0:
                    for hits in self._hits:
                        hits.append(now)
                    return
            log.debug("rate limit: sleeping %.2fs", wait)
            time.sleep(wait + 0.01)


class RiotClient:
    """Thin HTTP wrapper. One limiter per routing host."""

    def __init__(self, api_key: str | None = None, cache: bool = True):
        self.api_key = api_key or os.environ["RIOT_API_KEY"]
        self.cache = cache
        self._limiters: dict[str, SlidingWindowLimiter] = {}
        self._http = httpx.Client(timeout=15.0)
        if cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _limiter(self, host: str) -> SlidingWindowLimiter:
        if host not in self._limiters:
            self._limiters[host] = SlidingWindowLimiter(DEV_LIMITS)
        return self._limiters[host]

    def _cache_path(self, url: str) -> Path:
        return CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"

    def get(self, host: str, path: str, *, params: dict | None = None) -> Any:
        """GET https://{host}.api.riotgames.com{path}, rate-limited and cached.

        Raises httpx.HTTPStatusError on 4xx after retries are exhausted. A 403 on
        any val-match-v1 path is expected on a development key — see README.
        """
        url = f"https://{host}.api.riotgames.com{path}"
        cache_key = url + json.dumps(params or {}, sort_keys=True)

        if self.cache:
            cp = self._cache_path(cache_key)
            if cp.exists():
                return json.loads(cp.read_text())

        backoff = 1.0
        for attempt in range(5):
            self._limiter(host).acquire()
            r = self._http.get(url, params=params, headers={"X-Riot-Token": self.api_key})

            if r.status_code == 429:
                retry_after = float(r.headers.get("Retry-After", backoff))
                log.warning("429 on %s — sleeping %.1fs", path, retry_after)
                time.sleep(retry_after)
                backoff *= 2
                continue

            if r.status_code >= 500:
                log.warning("%s on %s — retry %d", r.status_code, path, attempt + 1)
                time.sleep(backoff)
                backoff *= 2
                continue

            if r.status_code == 403:
                raise PermissionError(
                    f"403 on {path}. Development keys cannot access val-match-v1; "
                    "this endpoint requires an approved production key."
                )

            r.raise_for_status()
            data = r.json()
            if self.cache:
                self._cache_path(cache_key).write_text(json.dumps(data))
            return data

        raise RuntimeError(f"exhausted retries for {url}")

    def close(self) -> None:
        self._http.close()
