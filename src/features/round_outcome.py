"""Round outcome as a feature row.

Added in Phase 3, not 2b. The Phase 3 rules need to say things like "Blue lost
R14" -- and the architecture's whole point is that *every* claim cites a feature
row, which in turn carries lineage to the raw rows. Letting rules read
`rounds.winning_team` directly would give the Watchdog two verification paths and
the decision trace two shapes. One extra feature keeps it to one of each.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.queries import rounds_ordered


class RoundOutcomeFeature:
    name = "round_won"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        teams = sorted({r["winning_team"] for r in rounds if r["winning_team"]})

        rows: list[FeatureRow] = []
        for r in rounds:
            refs = [{"table": "rounds", "match_id": match_id, "round_num": r["round_num"]}]
            for team in teams:
                rows.append(FeatureRow(
                    match_id=match_id, scope="team_round", round_num=r["round_num"],
                    name=f"round_won:{team}",
                    value=1.0 if r["winning_team"] == team else 0.0,
                    inputs=refs,
                ))
        return rows
