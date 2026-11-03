"""Squad rules and weekly squad scoring, as pure functions.

No database here. F4 ports these to the browser and F5 to Postgres, with shared test cases
keeping all three in agreement. Chips and transfers arrive with the game in F4.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Squad:
    starters: tuple[str, ...]
    subs: tuple[str, ...]  # bench order
    coaches: tuple[str, ...]
    captain: str
    vice: str


def validate_squad(squad: Squad, prices: dict[str, dict[str, Any]], rules: dict[str, Any],
                   event_kind: str = "regional") -> list[str]:
    """Reasons a squad is illegal, or an empty list. `prices` is one event's price rows,
    already limited to the entities allowed in this bracket. International events have a
    bigger budget because their fields are made up of the season's best-priced teams."""
    r = rules["squad"]
    errors: list[str] = []
    players = (*squad.starters, *squad.subs)

    if len(squad.starters) != r["starters"]:
        errors.append(f"needs {r['starters']} starters")
    if len(squad.subs) != r["subs"]:
        errors.append(f"needs {r['subs']} subs")
    if len(squad.coaches) != r["coaches"]:
        errors.append(f"needs {r['coaches']} coaches")
    if len({*players, *squad.coaches}) != len(players) + len(squad.coaches):
        errors.append("the same person is picked twice")

    unknown = [e for e in (*players, *squad.coaches) if e not in prices]
    if unknown:
        errors.append(f"not available in this bracket: {', '.join(sorted(unknown))}")
        return errors

    if any(prices[p]["kind"] != "player" for p in players):
        errors.append("a coach is in a player slot")
    if any(prices[c]["kind"] != "coach" for c in squad.coaches):
        errors.append("a player is in a coach slot")

    missing = set(r["required_roles"]) - {prices[p]["listed_role"] for p in squad.starters}
    if missing:
        errors.append(f"starters are missing: {', '.join(sorted(missing))}")

    teams = Counter(prices[p]["team_id"] for p in players)
    if any(n > r["max_players_per_team"] for n in teams.values()):
        errors.append(f"more than {r['max_players_per_team']} players from one team")
    coach_teams = Counter(prices[c]["team_id"] for c in squad.coaches)
    if any(n > r["max_coaches_per_team"] for n in coach_teams.values()):
        errors.append(f"more than {r['max_coaches_per_team']} coach from one team")

    cost = sum(prices[e]["price"] for e in (*players, *squad.coaches))
    budget = r["budget"][event_kind]
    if cost > budget:
        errors.append(f"costs {cost:g}, budget is {budget:g}")

    if squad.captain not in squad.starters or squad.vice not in squad.starters:
        errors.append("captain and vice-captain must be starters")
    elif squad.captain == squad.vice:
        errors.append("captain and vice-captain must be different players")
    return errors


def score_week(squad: Squad, points: dict[str, float], rules: dict[str, Any]) -> dict[str, float]:
    """One match week. `points` holds only people who played, so absence means no map.

    A starter who plays no map is replaced by the first unused sub who did. The captain's
    points double; if the captain played nothing, the vice-captain's double instead. The
    extra goes to whoever actually played, and only a starter can hold the armband.
    """
    fielded = [p for p in squad.starters if p in points]
    bench = [p for p in squad.subs if p in points]
    missing = sum(1 for p in squad.starters if p not in points)
    fielded += bench[:missing]

    players = sum(points[p] for p in fielded)
    armband = squad.captain if squad.captain in points else squad.vice if squad.vice in points else None
    bonus = points[armband] * (rules["squad"]["captain_multiplier"] - 1) if armband else 0.0
    coaches = sum(points.get(c, 0.0) for c in squad.coaches)
    return {
        "players": players,
        "captain_bonus": bonus,
        "coaches": coaches,
        "total": players + bonus + coaches,
    }
