"""Shared raw-row assembly helpers used by more than one Phase 2b feature.

Kept separate from the `Feature` implementations themselves: these return
plain data (and the row references needed for lineage), they don't write to
the `features` table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from src.riot.resolve import Role, role_of


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


def player_roles(conn: sqlite3.Connection, match_id: str) -> dict[str, Role]:
    """puuid -> role for every player in the match, resolved once from the agent.

    The single place role is derived for feature computation, so features scope
    by role without each re-deriving it (R1's `role_of` is the source of truth).
    """
    rows = conn.execute(
        "SELECT puuid, character_id FROM match_players WHERE match_id = ?", (match_id,)
    ).fetchall()
    return {r["puuid"]: role_of(r["character_id"]) for r in rows}


@dataclass
class KillEvent:
    round_num: int
    kill_ordinal: int
    killer: str
    victim: str
    round_time_ms: int | None
    traded: bool
    assistants: list[str] = field(default_factory=list)

    def ref(self, match_id: str) -> dict[str, Any]:
        return {"table": "round_kills", "match_id": match_id,
                "round_num": self.round_num, "kill_ordinal": self.kill_ordinal}

    def assist_refs(self, match_id: str) -> list[dict[str, Any]]:
        return [
            {"table": "round_kill_assists", "match_id": match_id,
             "round_num": self.round_num, "kill_ordinal": self.kill_ordinal,
             "assistant_puuid": a}
            for a in self.assistants
        ]


def kills_by_round(conn: sqlite3.Connection, match_id: str) -> dict[int, list[KillEvent]]:
    """The kill timeline grouped by round, each round ordered by kill_ordinal."""
    kills = conn.execute(
        """SELECT round_num, kill_ordinal, killer_puuid, victim_puuid,
                  round_time_ms, traded
           FROM round_kills WHERE match_id = ?
           ORDER BY round_num, kill_ordinal""",
        (match_id,),
    ).fetchall()
    assists: dict[tuple[int, int], list[str]] = {}
    for a in conn.execute(
        "SELECT round_num, kill_ordinal, assistant_puuid FROM round_kill_assists WHERE match_id = ?",
        (match_id,),
    ):
        assists.setdefault((a["round_num"], a["kill_ordinal"]), []).append(a["assistant_puuid"])

    out: dict[int, list[KillEvent]] = {}
    for k in kills:
        ev = KillEvent(
            round_num=k["round_num"], kill_ordinal=k["kill_ordinal"],
            killer=k["killer_puuid"], victim=k["victim_puuid"],
            round_time_ms=k["round_time_ms"], traded=bool(k["traded"]),
            assistants=assists.get((k["round_num"], k["kill_ordinal"]), []),
        )
        out.setdefault(ev.round_num, []).append(ev)
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
