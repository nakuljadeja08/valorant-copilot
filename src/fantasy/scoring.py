"""Fantasy points as feature rows, so every point carries its lineage.

Each component (kills, a clutch, a map win) is one row in `features` with
`scope='fantasy'`, named `fp_<rule>:<entity>`, and a `fp_total:<entity>` per map. The first
entry in `inputs_json` records the rule, its value and the rules version; the rest point at
the raw rows behind it. That gives point -> scoring rule -> feature row -> raw rounds.

Coach points are per series but `features` is keyed by map, so series-level points sit on
the deciding map and cite the series row.

Usage: `score_season` runs after a season is loaded. `src.fantasy.season` calls it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.features.base import FeatureRow
from src.fantasy.prices import team_price_totals, write_event_prices
from src.fantasy.stats import PlayerMapStats, Ref, map_stats

RULES_PATH = Path(__file__).with_name("rules_2027.json")
SCOPE = "fantasy"


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rules_version(rules: dict[str, Any]) -> str:
    """A content hash, so a trace can name the exact rules that produced its points."""
    return hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:12]


def _rule_ref(version: str, rule: str, each: float, count: int) -> Ref:
    return {"table": "fantasy_rules", "version": version, "rule": rule,
            "points_each": each, "count": count}


def _player_components(s: PlayerMapStats, rules: dict[str, Any]) -> list[tuple[str, float, int, list[Ref]]]:
    """(rule, points each, count, raw refs) for everything but the role bonus."""
    p = rules["player"]
    parts = [
        ("kill", p["kill"], len(s.kills), s.kills),
        # By played role, as FPL values a goal by position: Initiators collect assists
        # as part of the job, so each one is worth less than it is for anyone else.
        ("assist", p["assist"][s.role], len(s.assists), s.assists),
        ("death", p["death"], len(s.deaths), s.deaths),
        ("first_kill", p["first_kill"], len(s.first_kills), s.first_kills),
        ("first_death", p["first_death"], len(s.first_deaths), s.first_deaths),
    ]
    for size, refs in sorted(s.multikills.items()):
        # Refs list every kill in those rounds, so the count of rounds is kills / size.
        parts.append((f"multikill_{size}", p["multikill"][str(size)], len(refs) // size, refs))
    for opponents, refs in sorted(s.clutches.items()):
        parts.append((f"clutch_1v{opponents}", p["clutch"][str(opponents)], len(refs), refs))
    return [part for part in parts if part[2] > 0]


def _base_points(s: PlayerMapStats, rules: dict[str, Any]) -> float:
    points = sum(each * count for _, each, count, _ in _player_components(s, rules))
    return points + (rules["player"]["map_win"] if s.won else 0)


def role_bonuses(stats: dict[str, PlayerMapStats], rules: dict[str, Any]) -> dict[str, float]:
    """Bonus per player, ranked only against players in the same role on this map.

    A role with one player on the map has no peers, so it earns no bonus rather than a
    free first place. Ties fall to more kills, then puuid, so results stay repeatable.
    """
    by_role: dict[str, list[PlayerMapStats]] = {}
    for s in stats.values():
        by_role.setdefault(s.role, []).append(s)

    bonuses: dict[str, float] = {}
    table = rules["player"]["role_bonus"]
    for peers in by_role.values():
        if len(peers) < 2:
            continue
        ranked = sorted(peers, key=lambda s: (-_base_points(s, rules), -len(s.kills), s.puuid))
        for s, bonus in zip(ranked, table):
            if bonus:
                bonuses[s.puuid] = bonus
    return bonuses


def player_rows(match_id: str, stats: dict[str, PlayerMapStats], rules: dict[str, Any],
                version: str) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    bonuses = role_bonuses(stats, rules)
    map_win = rules["player"]["map_win"]

    for puuid in sorted(stats):
        s = stats[puuid]
        total = 0.0
        for rule, each, count, refs in _player_components(s, rules):
            value = each * count
            total += value
            rows.append(FeatureRow(match_id, SCOPE, f"fp_{rule}:{puuid}", value,
                                   [_rule_ref(version, rule, each, count), *refs]))
        if s.won:
            total += map_win
            rows.append(FeatureRow(match_id, SCOPE, f"fp_map_win:{puuid}", map_win, [
                _rule_ref(version, "map_win", map_win, 1),
                {"table": "matches", "match_id": match_id},
            ]))
        if puuid in bonuses:
            total += bonuses[puuid]
            rows.append(FeatureRow(match_id, SCOPE, f"fp_role_bonus:{puuid}", bonuses[puuid], [
                _rule_ref(version, "role_bonus", bonuses[puuid], 1),
                {"table": "match_players", "match_id": match_id, "played_role": s.role},
            ]))
        rows.append(FeatureRow(match_id, SCOPE, f"fp_total:{puuid}", total,
                               [{"table": "features", "match_id": match_id,
                                 "name_prefix": "fp_", "entity": puuid}]))
    return rows


def _round_totals(conn: sqlite3.Connection, match_id: str) -> dict[str, int]:
    return {r["winning_team"]: r["n"] for r in conn.execute(
        "SELECT winning_team, COUNT(*) AS n FROM rounds WHERE match_id = ? GROUP BY winning_team",
        (match_id,))}


def coach_rows(conn: sqlite3.Connection, series: sqlite3.Row, coaches: dict[str, str],
               team_prices: dict[str, float], rules: dict[str, Any], version: str) -> list[FeatureRow]:
    c = rules["coach"]
    maps = conn.execute(
        "SELECT * FROM series_maps WHERE series_id = ? ORDER BY map_num", (series["series_id"],)
    ).fetchall()
    series_ref = {"table": "series", "series_id": series["series_id"]}
    deciding = maps[-1]["match_id"]
    rows: list[FeatureRow] = []
    round_diff = {series["team_a"]: 0, series["team_b"]: 0}

    per_map_totals: dict[tuple[str, str], float] = {}
    for m in maps:
        wins = _round_totals(conn, m["match_id"])
        red, blue = wins.get("Red", 0), wins.get("Blue", 0)
        round_diff[m["red_team"]] += red - blue
        round_diff[m["blue_team"]] += blue - red
        for team in (series["team_a"], series["team_b"]):
            key = (m["match_id"], team)
            per_map_totals[key] = 0.0
            if m["winner"] == team:
                per_map_totals[key] += c["map_win"]
                rows.append(FeatureRow(m["match_id"], SCOPE, f"fp_coach_map_win:{coaches[team]}", c["map_win"], [
                    _rule_ref(version, "coach_map_win", c["map_win"], 1),
                    {"table": "series_maps", "series_id": series["series_id"], "map_num": m["map_num"]},
                ]))

    winner = series["winner"]
    loser = series["team_a"] if winner == series["team_b"] else series["team_b"]
    per_map_totals[(deciding, winner)] += c["series_win"]
    rows.append(FeatureRow(deciding, SCOPE, f"fp_coach_series_win:{coaches[winner]}", c["series_win"],
                           [_rule_ref(version, "coach_series_win", c["series_win"], 1), series_ref]))

    if team_prices[winner] < team_prices[loser]:
        per_map_totals[(deciding, winner)] += c["upset"]
        rows.append(FeatureRow(deciding, SCOPE, f"fp_coach_upset:{coaches[winner]}", c["upset"], [
            _rule_ref(version, "coach_upset", c["upset"], 1), series_ref,
            {"table": "event_prices", "event_id": series["event_id"], "team_id": winner},
            {"table": "event_prices", "event_id": series["event_id"], "team_id": loser},
        ]))

    for team, diff in sorted(round_diff.items()):
        value = max(diff, 0) // c["round_diff_divisor"]
        if value:
            per_map_totals[(deciding, team)] += value
            rows.append(FeatureRow(deciding, SCOPE, f"fp_coach_round_diff:{coaches[team]}", value, [
                _rule_ref(version, "coach_round_diff", 1, value),
                series_ref,
                *({"table": "rounds", "match_id": m["match_id"]} for m in maps),
            ]))

    for (match_id, team), total in sorted(per_map_totals.items()):
        rows.append(FeatureRow(match_id, SCOPE, f"fp_coach_total:{coaches[team]}", total,
                               [{"table": "features", "match_id": match_id,
                                 "name_prefix": "fp_coach_", "entity": coaches[team]}]))
    return rows


def compute_event_rows(conn: sqlite3.Connection, event_id: str, rules: dict[str, Any]) -> list[FeatureRow]:
    """Every fantasy feature row for an event, from raw rows. Writes nothing."""
    version = rules_version(rules)
    coaches = {r["team_id"]: r["coach_id"] for r in conn.execute(
        "SELECT team_id, coach_id FROM pro_coaches")}
    team_prices = team_price_totals(conn, event_id)
    rows: list[FeatureRow] = []
    series_rows = conn.execute(
        "SELECT * FROM series WHERE event_id = ? ORDER BY series_id", (event_id,)).fetchall()
    for series in series_rows:
        for m in conn.execute(
            "SELECT match_id FROM series_maps WHERE series_id = ? ORDER BY map_num",
            (series["series_id"],),
        ).fetchall():
            rows.extend(player_rows(m["match_id"], map_stats(conn, m["match_id"]), rules, version))
        rows.extend(coach_rows(conn, series, coaches, team_prices, rules, version))
    return rows


def score_season(conn: sqlite3.Connection, rules: dict[str, Any] | None = None) -> dict[str, int]:
    """Replace all prices and points. Events run in order, since each sets the next's prices."""
    rules = rules or load_rules()
    with conn:
        conn.execute("DELETE FROM features WHERE scope = ?", (SCOPE,))
        conn.execute("DELETE FROM event_prices")
    written = 0
    for e in conn.execute("SELECT event_id FROM events ORDER BY ordinal").fetchall():
        with conn:
            write_event_prices(conn, e["event_id"], rules)
            rows = compute_event_rows(conn, e["event_id"], rules)
            conn.executemany(
                """INSERT OR REPLACE INTO features
                   (match_id, round_num, scope, name, value, inputs_json)
                   VALUES (?,?,?,?,?,?)""",
                [(r.match_id, r.round_num, r.scope, r.name, r.value, r.inputs_json()) for r in rows],
            )
        written += len(rows)
    return {"feature_rows": written}
