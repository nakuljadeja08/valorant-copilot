"""Trade efficiency (sim-approx).

Real trade detection needs death timestamps to check whether a kill was
answered within a short window -- the sim only records aggregate kills per
player per round, not event timing. As a reduced-fidelity substitute this
computes each team's share of the round's total kills (kills_for / total
kills), which proxies "did this team trade evenly" without claiming to detect
actual trade windows. Labeled `sim-approx` throughout; do not present this as
real trade-window detection.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.constants import other_team
from src.features.queries import rounds_ordered, team_puuids, team_round_kills

NAME = "trade_efficiency_sim_approx"


class TradeEfficiencyFeature:
    name = NAME

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        kills = team_round_kills(conn, match_id)
        puuids = team_puuids(conn, match_id)
        teams = sorted({r["winning_team"] for r in rounds if r["winning_team"]})
        if len(teams) != 2:
            return []

        def refs(round_num: int, team: str) -> list[dict]:
            return [
                {"table": "round_player_stats", "match_id": match_id,
                 "round_num": round_num, "puuid": p}
                for p in puuids.get(team, [])
            ]

        rows: list[FeatureRow] = []
        for r in rounds:
            round_num = r["round_num"]
            for team in teams:
                kills_for = kills.get((round_num, team), 0)
                kills_against = kills.get((round_num, other_team(team)), 0)
                total = kills_for + kills_against
                share = (kills_for / total) if total else 0.5
                rows.append(FeatureRow(
                    match_id=match_id, scope="team_round", round_num=round_num,
                    name=f"{NAME}:{team}", value=share,
                    inputs=refs(round_num, team) + refs(round_num, other_team(team)),
                ))
        return rows
