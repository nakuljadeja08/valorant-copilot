"""Post-plant conversion: plant rate and win-after-plant rate per team per side.

Match-scoped (not per-round): these are rates over every round a team spent on
attack, per the `attacking_team` side convention in constants.py.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.constants import attacking_team
from src.features.queries import rounds_ordered


class PostPlantConversionFeature:
    name = "post_plant_conversion"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        teams = sorted({r["winning_team"] for r in rounds if r["winning_team"]})

        rows: list[FeatureRow] = []
        for team in teams:
            attack_rounds = [r for r in rounds if attacking_team(r["round_num"]) == team]
            planted = [r for r in attack_rounds if r["plant_site"]]

            attack_refs = [
                {"table": "rounds", "match_id": match_id, "round_num": r["round_num"]}
                for r in attack_rounds
            ]
            plant_refs = [
                {"table": "rounds", "match_id": match_id, "round_num": r["round_num"]}
                for r in planted
            ]

            plant_rate = len(planted) / len(attack_rounds) if attack_rounds else 0.0
            rows.append(FeatureRow(
                match_id=match_id, scope="match", name=f"plant_rate:{team}",
                value=plant_rate, inputs=attack_refs,
            ))

            won_after_plant = sum(1 for r in planted if r["winning_team"] == team)
            win_after_plant = won_after_plant / len(planted) if planted else 0.0
            rows.append(FeatureRow(
                match_id=match_id, scope="match", name=f"win_after_plant:{team}",
                value=win_after_plant, inputs=plant_refs,
            ))

        return rows
