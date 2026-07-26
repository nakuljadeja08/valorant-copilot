"""Pivotal round detection: the round with the largest swing in a win-probability
proxy built from score state (entering the round) and that round's economy
differential. This is the round the Analyst narrates in Phase 3.

The proxy is not a calibrated probability -- it's a bounded momentum index used
only to rank rounds against each other within one match.
"""

from __future__ import annotations

import math
import sqlite3

from src.features.base import FeatureRow
from src.features.queries import rounds_ordered, team_round_economy

SCORE_WEIGHT = 0.35
ECON_WEIGHT = 1.0 / 4000.0  # spend_diff is on a ~thousands-of-credits scale


def _proxy(score_diff: int, econ_diff: int) -> float:
    return 1.0 / (1.0 + math.exp(-(SCORE_WEIGHT * score_diff + ECON_WEIGHT * econ_diff)))


class PivotalRoundFeature:
    name = "pivotal_round"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        if not rounds:
            return []

        teams = sorted({r["winning_team"] for r in rounds if r["winning_team"]})
        if len(teams) != 2:
            return []
        ref_team, other = teams

        spend_diff = {}
        for te in team_round_economy(conn, match_id):
            sign = 1 if te.team_id == ref_team else -1
            spend_diff[te.round_num] = spend_diff.get(te.round_num, 0) + sign * te.spend

        wins = {ref_team: 0, other: 0}
        prev_p = 0.5
        best_round, best_swing = rounds[0]["round_num"], 0.0
        for r in rounds:
            round_num = r["round_num"]
            score_diff = wins[ref_team] - wins[other]
            p = _proxy(score_diff, spend_diff.get(round_num, 0))
            swing = abs(p - prev_p)
            if swing > best_swing:
                best_swing, best_round = swing, round_num
            prev_p = p
            if r["winning_team"]:
                wins[r["winning_team"]] += 1

        refs = [
            {"table": "rounds", "match_id": match_id, "round_num": rn}
            for rn in (max(best_round - 1, rounds[0]["round_num"]), best_round)
        ]
        return [
            FeatureRow(match_id=match_id, scope="match", name="pivotal_round",
                       value=float(best_round), inputs=refs),
            FeatureRow(match_id=match_id, scope="match", name="pivotal_round_swing",
                       value=best_swing, inputs=refs),
        ]
