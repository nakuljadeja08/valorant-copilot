"""Buy classification + economy curve.

Both read the same team-round bank/spend aggregation, so they live together.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.constants import BUY_CODES, classify_buy
from src.features.queries import team_round_economy

TREND_WINDOW = 3


class BuyClassificationFeature:
    """Per team-round: eco / force / half / full, from bank vs spend thresholds."""

    name = "buy_type"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rows = []
        for te in team_round_economy(conn, match_id):
            label = classify_buy(te.bank)
            rows.append(FeatureRow(
                match_id=match_id, scope="team_round", round_num=te.round_num,
                name=f"buy_type:{te.team_id}", value=BUY_CODES[label],
                inputs=te.refs(match_id),
            ))
        return rows


class EconomyCurveFeature:
    """Per-round team spend/bank, cross-team differential, rolling 3-round trend."""

    name = "economy_curve"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        team_rounds = team_round_economy(conn, match_id)
        rows: list[FeatureRow] = []

        by_team: dict[str, list] = {}
        for te in team_rounds:
            by_team.setdefault(te.team_id, []).append(te)
            rows.append(FeatureRow(
                match_id=match_id, scope="team_round", round_num=te.round_num,
                name=f"spend:{te.team_id}", value=float(te.spend), inputs=te.refs(match_id),
            ))
            rows.append(FeatureRow(
                match_id=match_id, scope="team_round", round_num=te.round_num,
                name=f"bank:{te.team_id}", value=float(te.bank), inputs=te.refs(match_id),
            ))

        for team, tes in by_team.items():
            tes.sort(key=lambda t: t.round_num)
            for i, te in enumerate(tes):
                window = tes[max(0, i - TREND_WINDOW + 1): i + 1]
                trend = sum(t.spend for t in window) / len(window)
                refs = [ref for t in window for ref in t.refs(match_id)]
                rows.append(FeatureRow(
                    match_id=match_id, scope="team_round", round_num=te.round_num,
                    name=f"spend_trend3:{team}", value=trend, inputs=refs,
                ))

        by_round: dict[int, dict[str, "object"]] = {}
        for te in team_rounds:
            by_round.setdefault(te.round_num, {})[te.team_id] = te
        for round_num, teams in by_round.items():
            if len(teams) != 2:
                continue
            (t1, te1), (t2, te2) = sorted(teams.items())
            diff = te1.spend - te2.spend
            rows.append(FeatureRow(
                match_id=match_id, scope="round", round_num=round_num,
                name="spend_diff", value=float(diff),
                inputs=te1.refs(match_id) + te2.refs(match_id),
            ))

        return rows
