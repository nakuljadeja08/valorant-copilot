"""Read-side view over one match's feature rows.

Rules never touch raw tables and never write. They read through this view, which
hands back `FeatureRef`s -- a value plus the lineage it was computed from. A
conclusion cites `FeatureRef`s; the Watchdog re-reads the same rows straight from
SQL and compares. That separation is what makes verification meaningful: the view
is the rules' copy, the store is the source of truth.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from src.features.base import MATCH_SCOPE_ROUND


@dataclass
class FeatureRef:
    """One feature row, as a rule sees it."""

    round_num: int
    scope: str
    name: str
    value: float
    inputs: list[dict[str, Any]]

    @property
    def team(self) -> str | None:
        """`buy_type:Blue` -> `Blue`; unsuffixed names -> None."""
        return self.name.split(":", 1)[1] if ":" in self.name else None


class FeatureView:
    def __init__(self, conn: sqlite3.Connection, match_id: str):
        self.match_id = match_id
        self._by_key: dict[tuple[str, int], FeatureRef] = {}
        self._by_name: dict[str, list[FeatureRef]] = {}

        rows = conn.execute(
            """SELECT round_num, scope, name, value, inputs_json
               FROM features WHERE match_id = ?
               ORDER BY name, round_num""",
            (match_id,),
        ).fetchall()
        for r in rows:
            ref = FeatureRef(
                round_num=r["round_num"], scope=r["scope"], name=r["name"],
                value=r["value"], inputs=json.loads(r["inputs_json"]),
            )
            self._by_key[(ref.name, ref.round_num)] = ref
            self._by_name.setdefault(ref.name, []).append(ref)

    def __bool__(self) -> bool:
        return bool(self._by_key)

    @property
    def teams(self) -> list[str]:
        """Team ids present in the feature names, e.g. ['Blue', 'Red']."""
        return sorted({
            ref.team for ref in self._by_key.values() if ref.team is not None
        })

    def match_value(self, name: str) -> FeatureRef | None:
        """A match-scoped feature (round_num sentinel -1)."""
        return self._by_key.get((name, MATCH_SCOPE_ROUND))

    def at(self, name: str, round_num: int) -> FeatureRef | None:
        return self._by_key.get((name, round_num))

    def series(self, name: str) -> list[FeatureRef]:
        """Every per-round row for a name, ordered by round."""
        return sorted(
            (r for r in self._by_name.get(name, []) if r.round_num != MATCH_SCOPE_ROUND),
            key=lambda r: r.round_num,
        )
