"""Per-map counting stats for fantasy scoring, read from the kill timeline.

Plain data with row references, in the style of `src/features/queries.py`. Nothing here
knows what a stat is worth; that belongs to `scoring.py` and its rules file.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from src.features.queries import kills_by_round, player_roles, rounds_ordered, team_puuids
from src.riot.resolve import Role

Ref = dict[str, Any]


@dataclass
class PlayerMapStats:
    puuid: str
    side: str  # Red | Blue
    role: Role  # played on this map, from the agent
    won: bool = False
    kills: list[Ref] = field(default_factory=list)
    assists: list[Ref] = field(default_factory=list)
    deaths: list[Ref] = field(default_factory=list)
    first_kills: list[Ref] = field(default_factory=list)
    first_deaths: list[Ref] = field(default_factory=list)
    multikills: dict[int, list[Ref]] = field(default_factory=dict)  # kills in a round -> rounds
    clutches: dict[int, list[Ref]] = field(default_factory=dict)  # opponents faced -> rounds


def _round_ref(match_id: str, round_num: int) -> Ref:
    return {"table": "rounds", "match_id": match_id, "round_num": round_num}


def find_clutch(events: list, teams: dict[str, list[str]], winner: str) -> tuple[str, int] | None:
    """(player, opponents) if the winning side won from one player down against 2 or more.

    The opponent count is taken when the player became the last alive. They must also
    survive: a last player who dies before the spike goes off hasn't clutched.
    """
    alive = {side: set(members) for side, members in teams.items()}
    found: tuple[str, int] | None = None
    for event in events:
        for side, members in alive.items():
            if event.victim in members:
                members.discard(event.victim)
                if side == winner and len(members) == 1 and found is None:
                    opponents = sum(len(m) for s, m in alive.items() if s != side)
                    found = (next(iter(members)), opponents)
                break
    if found is None or found[1] < 2 or found[0] not in alive.get(winner, set()):
        return None
    return found


def map_stats(conn: sqlite3.Connection, match_id: str) -> dict[str, PlayerMapStats]:
    timeline = kills_by_round(conn, match_id)
    teams = team_puuids(conn, match_id)
    roles = player_roles(conn, match_id)
    rounds = rounds_ordered(conn, match_id)

    stats = {
        puuid: PlayerMapStats(puuid=puuid, side=side, role=roles[puuid])
        for side, members in teams.items() for puuid in members
    }

    round_wins: dict[str, int] = {}
    for r in rounds:
        round_num, winner = r["round_num"], r["winning_team"]
        round_wins[winner] = round_wins.get(winner, 0) + 1
        events = timeline.get(round_num, [])
        kills_this_round: dict[str, list] = {}

        for event in events:
            stats[event.killer].kills.append(event.ref(match_id))
            stats[event.victim].deaths.append(event.ref(match_id))
            kills_this_round.setdefault(event.killer, []).append(event)
            for assistant in event.assistants:
                stats[assistant].assists.append({
                    "table": "round_kill_assists", "match_id": match_id,
                    "round_num": round_num, "kill_ordinal": event.kill_ordinal,
                    "assistant_puuid": assistant,
                })

        if events:
            first = events[0]
            stats[first.killer].first_kills.append(first.ref(match_id))
            stats[first.victim].first_deaths.append(first.ref(match_id))

        for puuid, own in kills_this_round.items():
            if len(own) >= 3:
                stats[puuid].multikills.setdefault(min(len(own), 5), []).extend(
                    e.ref(match_id) for e in own)

        clutch = find_clutch(events, teams, winner)
        if clutch:
            player, opponents = clutch
            stats[player].clutches.setdefault(min(opponents, 5), []).append(
                _round_ref(match_id, round_num))

    winning_side = max(round_wins, key=lambda side: round_wins[side]) if round_wins else None
    for s in stats.values():
        s.won = s.side == winning_side
    return stats
