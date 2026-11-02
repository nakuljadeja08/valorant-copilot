"""The seam between a season's data source and everything downstream.

Mirrors `src/riot/adapter.py`: downstream code sees teams, players and finished events,
and never knows whether they were simulated. F7 adds a licensed source here, once the
rights are settled, with no other code change.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Iterator

from src.fantasy.league import Player, Team
from src.fantasy.schedule import EventRecord, SeasonSimulator


class ProSeasonSource(ABC):
    """Contract: league entities, then finished events in calendar order."""

    # Written to matches.source, so provenance is never lost.
    provenance: str

    @abstractmethod
    def config(self) -> dict[str, Any]:
        """The season calendar, including which details are assumed."""

    @abstractmethod
    def teams(self) -> list[Team]:
        """Every team in the season."""

    @abstractmethod
    def players(self) -> list[Player]:
        """Every player who may appear in the season."""

    @abstractmethod
    def events(self) -> Iterator[EventRecord]:
        """Finished events, in calendar order."""


class SimProSeasonSource(ProSeasonSource):
    """A fictional season: invented teams and players on the real 2027 structure."""

    provenance = "sim"

    def __init__(self, seed: int):
        self.sim = SeasonSimulator(seed)

    def config(self) -> dict[str, Any]:
        return self.sim.config

    def teams(self) -> list[Team]:
        return self.sim.league.teams

    def players(self) -> list[Player]:
        return self.sim.league.every_player

    def events(self) -> Iterator[EventRecord]:
        return self.sim.events()


def get_pro_source(seed: int, source: str | None = None) -> ProSeasonSource:
    """Factory driven by FANTASY_DATA_SOURCE. Only the simulator exists until F7."""
    source = source or os.getenv("FANTASY_DATA_SOURCE", "sim")

    if source == "sim":
        return SimProSeasonSource(seed)

    raise ValueError(f"unknown FANTASY_DATA_SOURCE: {source!r} (expected 'sim')")
