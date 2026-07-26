"""Shared raw-row assembly helpers used by more than one Phase 2b feature.

Kept separate from the `Feature` implementations themselves: these return
plain data (and the row references needed for lineage), they don't write to
the `features` table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass
class TeamRoundEconomy:
    round_num: int
    team_id: str
    bank: int  # sum of loadout_value across the team's 5 players (pre-buy)
    spend: int  # sum of spent
    puuids: list[str]

    def refs(self, match_id: str) -> list[dict[str, Any]]:
        return [
            {"table": "round_player_stats", "match_id": match_id, "round_num": self.round_num,
             "puuid": p}
            for p in self.puuids
        ]


def team_round_economy(conn: sqlite3.Connection, match_id: str) -> list[TeamRoundEconomy]:
    rows = conn.execute(
        """SELECT rps.round_num, mp.team_id,
                  SUM(rps.loadout_value) bank, SUM(rps.spent) spend,
                  GROUP_CONCAT(rps.puuid) puuids
           FROM round_player_stats rps
           JOIN match_players mp ON mp.match_id = rps.match_id AND mp.puuid = rps.puuid
           WHERE rps.match_id = ?
           GROUP BY rps.round_num, mp.team_id
           ORDER BY rps.round_num""",
        (match_id,),
    ).fetchall()
    return [
        TeamRoundEconomy(
            round_num=r["round_num"], team_id=r["team_id"],
            bank=r["bank"] or 0, spend=r["spend"] or 0,
            puuids=(r["puuids"] or "").split(","),
        )
        for r in rows
    ]


def rounds_ordered(conn: sqlite3.Connection, match_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT round_num, winning_team, round_result, plant_site
           FROM rounds WHERE match_id = ? ORDER BY round_num""",
        (match_id,),
    ).fetchall()


def team_puuids(conn: sqlite3.Connection, match_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT team_id, puuid FROM match_players WHERE match_id = ?", (match_id,)
    ).fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["team_id"], []).append(r["puuid"])
    return out


def team_round_kills(conn: sqlite3.Connection, match_id: str) -> dict[tuple[int, str], int]:
    """kills scored by each team's players, per round."""
    rows = conn.execute(
        """SELECT rps.round_num, mp.team_id, SUM(rps.kills) kills
           FROM round_player_stats rps
           JOIN match_players mp ON mp.match_id = rps.match_id AND mp.puuid = rps.puuid
           WHERE rps.match_id = ?
           GROUP BY rps.round_num, mp.team_id""",
        (match_id,),
    ).fetchall()
    return {(r["round_num"], r["team_id"]): r["kills"] or 0 for r in rows}
