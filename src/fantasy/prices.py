"""Fantasy prices and listed roles, set once per event and fixed during it.

The first price comes from a noisy read of a player's rating, because a real game prices
from past results and past results are imperfect. After that, a price moves between events
on how the player scored against others in the same role, so roles aren't priced against
each other. Everything is deterministic: the noise is seeded from the entity's own id.
"""

from __future__ import annotations

import math
import random
import sqlite3
from collections import Counter
from typing import Any

from src.fantasy.league import PLAYER_SKILL_SD, TEAM_RATING_SD
from src.riot.resolve import role_of

PRESEASON_NOISE_SD = 0.6
TEAM_SHARE_OF_PLAYER_PRICE = 0.5


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _half_step(value: float) -> float:
    return round(value * 2) / 2


def _preseason_player_price(puuid: str, skill: float, team_rating: float, p: dict) -> float:
    noise = random.Random(f"price:{puuid}").gauss(0, PRESEASON_NOISE_SD)
    z = math.log(skill) / PLAYER_SKILL_SD + TEAM_SHARE_OF_PLAYER_PRICE * team_rating / TEAM_RATING_SD + noise
    z /= math.sqrt(1 + TEAM_SHARE_OF_PLAYER_PRICE ** 2 + PRESEASON_NOISE_SD ** 2)
    return _half_step(p["player_min"] + (p["player_max"] - p["player_min"]) * _phi(z))


def _preseason_coach_price(coach_id: str, team_rating: float, p: dict) -> float:
    noise = random.Random(f"price:{coach_id}").gauss(0, PRESEASON_NOISE_SD)
    z = (team_rating / TEAM_RATING_SD + noise) / math.sqrt(1 + PRESEASON_NOISE_SD ** 2)
    return _half_step(p["coach_min"] + (p["coach_max"] - p["coach_min"]) * _phi(z))


def _previous_event(conn: sqlite3.Connection, event_id: str) -> str | None:
    row = conn.execute(
        """SELECT event_id FROM events
           WHERE ordinal < (SELECT ordinal FROM events WHERE event_id = ?)
           ORDER BY ordinal DESC LIMIT 1""", (event_id,)).fetchone()
    return row["event_id"] if row else None


def _points_per_map(conn: sqlite3.Connection, event_id: str, prefix: str) -> dict[str, float]:
    rows = conn.execute(
        """SELECT f.name, AVG(f.value) AS points FROM features f
           JOIN series_maps sm ON sm.match_id = f.match_id
           JOIN series s ON s.series_id = sm.series_id
           WHERE s.event_id = ? AND f.scope = 'fantasy' AND f.name LIKE ?
           GROUP BY f.name""", (event_id, f"{prefix}:%")).fetchall()
    return {r["name"].partition(":")[2]: r["points"] for r in rows}


def _played_roles(conn: sqlite3.Connection, event_id: str) -> dict[str, Counter]:
    played: dict[str, Counter] = {}
    for r in conn.execute(
        """SELECT mp.puuid, mp.character_id FROM match_players mp
           JOIN series_maps sm ON sm.match_id = mp.match_id
           JOIN series s ON s.series_id = sm.series_id
           WHERE s.event_id = ?""", (event_id,)):
        played.setdefault(r["puuid"], Counter())[role_of(r["character_id"])] += 1
    return played


def _moved(price: float, points: float | None, peers: list[float], p: dict,
           low: float, high: float) -> float:
    """Shift a price by how far `points` sits from its peer group, within limits."""
    if points is None or len(peers) < 2:
        return price
    mean = sum(peers) / len(peers)
    sd = math.sqrt(sum((x - mean) ** 2 for x in peers) / len(peers))
    if sd == 0:
        return price
    move = max(-p["max_move"], min(p["max_move"], p["step_per_sd"] * (points - mean) / sd))
    return min(high, max(low, _half_step(price + move)))


def write_event_prices(conn: sqlite3.Connection, event_id: str, rules: dict[str, Any]) -> None:
    p = rules["prices"]
    previous = _previous_event(conn, event_id)

    last_price: dict[str, float] = {}
    last_role: dict[str, str] = {}
    for r in conn.execute(
        """SELECT ep.entity_id, ep.price, ep.listed_role FROM event_prices ep
           JOIN events e ON e.event_id = ep.event_id ORDER BY e.ordinal"""):
        last_price[r["entity_id"]] = r["price"]
        last_role[r["entity_id"]] = r["listed_role"]

    player_points = _points_per_map(conn, previous, "fp_total") if previous else {}
    coach_points = _points_per_map(conn, previous, "fp_coach_total") if previous else {}
    played = _played_roles(conn, previous) if previous else {}

    roster = conn.execute(
        """SELECT er.puuid, er.team_id, p.base_role, p.skill, t.rating
           FROM event_rosters er
           JOIN pro_players p USING (puuid) JOIN pro_teams t USING (team_id)
           WHERE er.event_id = ? ORDER BY er.puuid""", (event_id,)).fetchall()

    def listed_role(puuid: str, base: str) -> str:
        counts = played.get(puuid)
        if not counts:
            return last_role.get(puuid) or base
        top = max(counts.values())
        leaders = sorted(role for role, n in counts.items() if n == top)
        current = last_role.get(puuid) or base
        return current if current in leaders else leaders[0]

    roles = {r["puuid"]: listed_role(r["puuid"], r["base_role"]) for r in roster}
    peers_by_role: dict[str, list[float]] = {}
    for puuid, points in player_points.items():
        if puuid in played:
            peers_by_role.setdefault(played[puuid].most_common(1)[0][0], []).append(points)

    for r in roster:
        puuid = r["puuid"]
        if puuid in last_price:
            price = _moved(last_price[puuid], player_points.get(puuid),
                           peers_by_role.get(roles[puuid], []), p, p["player_min"], p["player_max"])
        else:
            price = _preseason_player_price(puuid, r["skill"], r["rating"], p)
        conn.execute(
            """INSERT INTO event_prices (event_id, entity_id, kind, team_id, price, listed_role)
               VALUES (?,?,?,?,?,?)""", (event_id, puuid, "player", r["team_id"], price, roles[puuid]))

    coaches = conn.execute(
        """SELECT c.coach_id, c.team_id, t.rating FROM event_teams et
           JOIN pro_coaches c ON c.team_id = et.team_id
           JOIN pro_teams t ON t.team_id = et.team_id
           WHERE et.event_id = ? ORDER BY c.coach_id""", (event_id,)).fetchall()
    coach_peers = list(coach_points.values())
    for c in coaches:
        cid = c["coach_id"]
        if cid in last_price:
            price = _moved(last_price[cid], coach_points.get(cid), coach_peers, p,
                           p["coach_min"], p["coach_max"])
        else:
            price = _preseason_coach_price(cid, c["rating"], p)
        conn.execute(
            """INSERT INTO event_prices (event_id, entity_id, kind, team_id, price, listed_role)
               VALUES (?,?,?,?,?,NULL)""", (event_id, cid, "coach", c["team_id"], price))


def team_price_totals(conn: sqlite3.Connection, event_id: str) -> dict[str, float]:
    """A team's five player prices added up. The coach's upset bonus compares these."""
    return {r["team_id"]: r["total"] for r in conn.execute(
        """SELECT team_id, SUM(price) AS total FROM event_prices
           WHERE event_id = ? AND kind = 'player' GROUP BY team_id""", (event_id,))}
