"""Loss-streak state machine + broken-buy flag.

Streak is reconstructed purely from `rounds.winning_team` -- the sim never
serializes its internal streak counter, so this must hold structurally: streak
entering round r = consecutive prior rounds lost by that team, capped at the
sim's own bonus ceiling (two consecutive losses is the max escalation tier).

A "broken buy" flags a round where the loss-bonus mechanic should have put a
team back on their feet (streak entering the round >= max escalation) but the
team's reconstructed bank still classifies as eco/force -- i.e. the escalation
didn't do its job, or the team never recovered.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.constants import classify_buy
from src.features.queries import rounds_ordered, team_round_economy

MAX_STREAK = 2  # matches the sim's LOSS_BONUS escalation cap


class LossStreakFeature:
    name = "loss_streak"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        banks = {(te.round_num, te.team_id): te for te in team_round_economy(conn, match_id)}

        teams = sorted({r["winning_team"] for r in rounds if r["winning_team"]})
        streak = {t: 0 for t in teams}
        loss_rounds: dict[str, list[int]] = {t: [] for t in teams}

        rows: list[FeatureRow] = []
        for r in rounds:
            round_num = r["round_num"]
            for team in teams:
                entering_streak = streak[team]
                streak_refs = [
                    {"table": "rounds", "match_id": match_id, "round_num": rn}
                    for rn in loss_rounds[team]
                ]
                rows.append(FeatureRow(
                    match_id=match_id, scope="team_round", round_num=round_num,
                    name=f"loss_streak:{team}", value=float(entering_streak),
                    inputs=streak_refs,
                ))

                te = banks.get((round_num, team))
                broken = 0.0
                broken_refs = list(streak_refs)
                if te is not None:
                    broken_refs = broken_refs + te.refs(match_id)
                    if entering_streak >= MAX_STREAK and classify_buy(te.bank) in ("eco", "force"):
                        broken = 1.0
                rows.append(FeatureRow(
                    match_id=match_id, scope="team_round", round_num=round_num,
                    name=f"broken_buy:{team}", value=broken, inputs=broken_refs,
                ))

            winner = r["winning_team"]
            if winner:
                for team in teams:
                    if team == winner:
                        streak[team] = 0
                        loss_rounds[team] = []
                    else:
                        streak[team] = min(streak[team] + 1, MAX_STREAK)
                        loss_rounds[team] = loss_rounds[team] + [round_num]

        return rows
