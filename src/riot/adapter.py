"""The single seam between data source and everything downstream.

Both implementations return payloads conforming to the documented `val-match-v1`
response shape. No module past this file knows or cares which one is active.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Iterator, Any


class MatchSource(ABC):
    """Contract: yield val-match-v1 shaped match payloads."""

    @abstractmethod
    def matchlist(self, puuid: str) -> list[str]:
        """Return match IDs for a player, newest first."""

    @abstractmethod
    def match(self, match_id: str) -> dict[str, Any]:
        """Return a full match payload."""

    def stream(self, puuid: str, limit: int | None = None) -> Iterator[dict[str, Any]]:
        ids = self.matchlist(puuid)
        if limit:
            ids = ids[:limit]
        for mid in ids:
            yield self.match(mid)


class LiveMatchSource(MatchSource):
    """Requires an approved production key. Will 403 on a development key.

    Note the matchlist ceiling: Riot returns a bounded window of recent matches,
    so the ingest pipeline treats the local store as an accumulating archive
    rather than assuming it can backfill arbitrarily far.
    """

    def __init__(self, client, region: str | None = None):
        self.client = client
        self.region = region or os.getenv("RIOT_REGION", "americas")

    def matchlist(self, puuid: str) -> list[str]:
        data = self.client.get(self.region, f"/val/match/v1/matchlists/by-puuid/{puuid}")
        return [m["matchId"] for m in data.get("history", [])]

    def match(self, match_id: str) -> dict[str, Any]:
        return self.client.get(self.region, f"/val/match/v1/matches/{match_id}")


class SimMatchSource(MatchSource):
    """Schema-faithful simulator. Grounded in real agent/map IDs from val-content-v1."""

    def __init__(self, generator):
        self.gen = generator
        self._cache: dict[str, dict] = {}
        self._puuid: str | None = None

    def matchlist(self, puuid: str) -> list[str]:
        # Remembered so match() can seat the same player. Without this the
        # generator falls back to its default hero and a caller passing
        # --puuid gets rosters that never contain the player they asked for.
        self._puuid = puuid
        return self.gen.matchlist_for(puuid)

    def match(self, match_id: str) -> dict[str, Any]:
        if match_id not in self._cache:
            kwargs = {"hero_puuid": self._puuid} if self._puuid else {}
            self._cache[match_id] = self.gen.build_match(match_id, **kwargs)
        return self._cache[match_id]


def get_source(source: str | None = None) -> MatchSource:
    """Factory driven by RIOT_DATA_SOURCE. This is the flip."""
    source = source or os.getenv("RIOT_DATA_SOURCE", "sim")

    if source == "live":
        from src.riot.client import RiotClient
        return LiveMatchSource(RiotClient())

    if source == "sim":
        from src.sim.generator import MatchGenerator
        return SimMatchSource(MatchGenerator())

    raise ValueError(f"unknown RIOT_DATA_SOURCE: {source!r} (expected 'sim' or 'live')")
