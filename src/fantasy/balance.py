"""Test the rules across many simulated seasons, against the targets in FANTASY_PLAN.md.

Several leagues are each replayed under many result seeds. Replaying a league is what makes
"is one player a must-have?" answerable, since the same players then face different results.

Targets:
  role_spread        mean points per map by role, within 15% of each other
  optimal_share      no player in more than 60% of hindsight-best squads
  affordable         legal squads exist in every bracket, and the budget still forces choices
  coach_share        coaches earn 10-20% of a typical squad's points

"Hindsight-best" comes from local search, not an exact solver, so it's a close approximation.
These numbers calibrate rules on simulated data. F7 must re-run them on real distributions.

Usage:
    python -m src.fantasy.balance --leagues 4 --seeds-per-league 50 --workers 20
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from src.fantasy.scoring import load_rules, score_season
from src.fantasy.source import SimProSeasonSource
from src.fantasy.squads import Squad, score_week, validate_squad
from src.fantasy.store import load_season, open_store
from src.riot.resolve import role_of

RANDOM_SQUADS_PER_BRACKET = 60
SEARCH_RESTARTS = 3
TARGETS = {"role_spread": 0.15, "optimal_share": 0.60, "coach_share": (0.10, 0.20)}


def _brackets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT DISTINCT event_id, bracket FROM event_teams ORDER BY 1, 2").fetchall()


def _pool(conn: sqlite3.Connection, event_id: str, bracket: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """SELECT ep.entity_id, ep.kind, ep.team_id, ep.price, ep.listed_role FROM event_prices ep
           JOIN event_teams et ON et.event_id = ep.event_id AND et.team_id = ep.team_id
           WHERE ep.event_id = ? AND et.bracket = ?""", (event_id, bracket)).fetchall()
    return {r["entity_id"]: dict(r) for r in rows}


def _weekly_points(conn: sqlite3.Connection, event_id: str, bracket: str) -> dict[int, dict[str, float]]:
    weeks: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in conn.execute(
        """SELECT s.week_num, f.name, f.value FROM features f
           JOIN series_maps sm ON sm.match_id = f.match_id
           JOIN series s ON s.series_id = sm.series_id
           WHERE s.event_id = ? AND s.bracket = ? AND f.scope = 'fantasy'
             AND (f.name LIKE 'fp_total:%' OR f.name LIKE 'fp_coach_total:%')""", (event_id, bracket)):
        weeks[r["week_num"]][r["name"].partition(":")[2]] += r["value"]
    return weeks


def _random_squad(rng: random.Random, pool: dict[str, dict], rules: dict) -> Squad:
    """A manager's plausible pick: legal shape, no hindsight. May be over budget."""
    by_role: dict[str, list[str]] = defaultdict(list)
    players, coaches = [], []
    for entity, row in sorted(pool.items()):
        if row["kind"] == "coach":
            coaches.append(entity)
        else:
            players.append(entity)
            by_role[row["listed_role"]].append(entity)
    starters = [rng.choice(by_role[r]) for r in rules["squad"]["required_roles"]]
    rest = rng.sample([p for p in players if p not in starters], 3)
    starters.append(rest[0])
    chosen_coaches = rng.sample(coaches, rules["squad"]["coaches"])
    by_price = sorted(starters, key=lambda p: (-pool[p]["price"], p))
    return Squad(tuple(starters), tuple(rest[1:]), tuple(chosen_coaches), by_price[0], by_price[1])


def _objective(squad: Squad, totals: dict[str, float]) -> float:
    starters = [totals.get(p, 0.0) for p in squad.starters]
    return sum(starters) + max(starters) + sum(totals.get(c, 0.0) for c in squad.coaches)


def _best_squad(pool: dict[str, dict], totals: dict[str, float], rules: dict, rng: random.Random,
                kind: str = "regional") -> Squad | None:
    """Local search: swap one person at a time until nothing legal improves the score."""
    players = sorted(e for e, r in pool.items() if r["kind"] == "player")
    coaches = sorted(e for e, r in pool.items() if r["kind"] == "coach")

    def legal(squad: Squad) -> bool:
        return not validate_squad(squad, pool, rules, kind)

    best: Squad | None = None
    best_score = float("-inf")
    for _ in range(SEARCH_RESTARTS):
        current = None
        for _ in range(3000):
            candidate = _random_squad(rng, pool, rules)
            if legal(candidate):
                current = candidate
                break
        if current is None:
            continue
        score = _objective(current, totals)
        improved = True
        while improved:
            improved = False
            for slot, group, options in (("starters", current.starters, players),
                                         ("subs", current.subs, players),
                                         ("coaches", current.coaches, coaches)):
                for i in range(len(group)):
                    for option in options:
                        members = list(getattr(current, slot))
                        members[i] = option
                        starters = tuple(members) if slot == "starters" else current.starters
                        ranked = sorted(starters, key=lambda p: (-totals.get(p, 0.0), p))
                        trial = Squad(starters,
                                      tuple(members) if slot == "subs" else current.subs,
                                      tuple(members) if slot == "coaches" else current.coaches,
                                      ranked[0], ranked[1])
                        trial_score = _objective(trial, totals)
                        if trial_score > score and legal(trial):
                            current, score, improved = trial, trial_score, True
                            break
                    if improved:
                        break
                if improved:
                    break
        if score > best_score:
            best, best_score = current, score
    return best


def _bracket_metrics(conn: sqlite3.Connection, event_id: str, bracket: str, rules: dict, seed: int) -> dict:
    pool = _pool(conn, event_id, bracket)
    weeks = _weekly_points(conn, event_id, bracket)
    kind = conn.execute("SELECT kind FROM events WHERE event_id = ?", (event_id,)).fetchone()["kind"]
    budget = rules["squad"]["budget"][kind]
    totals: dict[str, float] = defaultdict(float)
    for week in weeks.values():
        for entity, points in week.items():
            totals[entity] += points

    rng = random.Random(f"{seed}:{event_id}:{bracket}")
    players = sorted((r["price"], e) for e, r in pool.items() if r["kind"] == "player")
    coaches = sorted(r["price"] for r in pool.values() if r["kind"] == "coach")

    legal = attempts = 0
    shares = {"players": 0.0, "captain_bonus": 0.0, "coaches": 0.0}
    squad_total = 0.0
    while legal < RANDOM_SQUADS_PER_BRACKET and attempts < RANDOM_SQUADS_PER_BRACKET * 40:
        attempts += 1
        squad = _random_squad(rng, pool, rules)
        if validate_squad(squad, pool, rules, kind):
            continue
        legal += 1
        for points in weeks.values():
            scored = score_week(squad, points, rules)
            for part in shares:
                shares[part] += scored[part]
            squad_total += scored["total"]

    best = _best_squad(pool, totals, rules, rng, kind)
    return {
        "event_id": event_id,
        "bracket": bracket,
        "budget": budget,
        "legal_rate": legal / attempts if attempts else 0.0,
        "typical_total": squad_total / legal if legal else 0.0,
        "coach_share": shares["coaches"] / squad_total if squad_total else 0.0,
        "captain_share": shares["captain_bonus"] / squad_total if squad_total else 0.0,
        "cheapest_core": sum(p for p, _ in players[:7]) + sum(coaches[:2]),
        "dearest_core": sum(p for p, _ in players[-7:]) + sum(coaches[-2:]),
        "best_squad": sorted(best.starters) if best else [],
        "best_coaches": sorted(best.coaches) if best else [],
        "best_total": sum(totals.get(e, 0.0) for e in (*best.starters, *best.coaches)) if best else 0.0,
        "best_cost": sum(pool[e]["price"] for e in (*best.starters, *best.subs, *best.coaches)) if best else 0.0,
    }


def run_season(job: tuple[int, int]) -> dict:
    """Build, score and measure one season in a throwaway store."""
    league_seed, seed = job
    rules = load_rules()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = open_store(str(Path(tmp) / "balance.db"))
        conn.execute("PRAGMA synchronous=OFF")
        load_season(conn, SimProSeasonSource(seed, league_seed=league_seed))
        score_season(conn, rules)

        by_role: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        by_region: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        roles = {(r["match_id"], r["puuid"]): role_of(r["character_id"]) for r in conn.execute(
            "SELECT match_id, puuid, character_id FROM match_players")}
        regions = {r["puuid"]: r["region"] for r in conn.execute("SELECT puuid, region FROM pro_players")}
        top_kills = conn.execute("SELECT MAX(kills) FROM match_players").fetchone()[0]
        for r in conn.execute(
            "SELECT match_id, name, value FROM features WHERE scope = 'fantasy' AND name LIKE 'fp_total:%'"):
            puuid = r["name"].partition(":")[2]
            role = by_role[roles[(r["match_id"], puuid)]]
            role[0] += r["value"]
            role[1] += 1
            region = by_region[regions[puuid]]
            region[0] += r["value"]
            region[1] += 1

        brackets = [_bracket_metrics(conn, b["event_id"], b["bracket"], rules, seed) for b in _brackets(conn)]
        conn.close()
    return {"league": league_seed, "seed": seed, "by_role": dict(by_role), "by_region": dict(by_region),
            "top_kills": top_kills, "brackets": brackets}


def summarize(results: list[dict], rules: dict) -> dict[str, Any]:
    role_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    region_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for result in results:
        for source, target in ((result["by_role"], role_totals), (result["by_region"], region_totals)):
            for key, (points, n) in source.items():
                target[key][0] += points
                target[key][1] += n
    role_means = {k: v[0] / v[1] for k, v in sorted(role_totals.items())}
    region_means = {k: v[0] / v[1] for k, v in sorted(region_totals.items())}

    brackets = [b for r in results for b in r["brackets"]]
    mean = lambda key: sum(b[key] for b in brackets) / len(brackets)  # noqa: E731

    # Share of hindsight-best squads holding the most-picked person, per league and bracket.
    picks: dict[tuple, Counter] = defaultdict(Counter)
    coach_picks: dict[tuple, Counter] = defaultdict(Counter)
    runs: Counter = Counter()
    for result in results:
        for b in result["brackets"]:
            key = (result["league"], b["event_id"], b["bracket"])
            picks[key].update(b["best_squad"])
            coach_picks[key].update(b.get("best_coaches", []))
            runs[key] += 1
    shares = sorted(max(c.values()) / runs[k] for k, c in picks.items() if c)
    share_by_event: dict[str, list[float]] = defaultdict(list)
    for key, counter in picks.items():
        if counter:
            share_by_event[key[1]].append(max(counter.values()) / runs[key])
    coach_shares = sorted(max(c.values()) / runs[k] for k, c in coach_picks.items() if c)

    legal_by_event: dict[str, list[float]] = defaultdict(list)
    for b in brackets:
        legal_by_event[b["event_id"]].append(b["legal_rate"])

    spread = max(role_means.values()) / min(role_means.values()) - 1
    return {
        "seasons": len(results),
        "role_points_per_map": {k: round(v, 2) for k, v in role_means.items()},
        "role_spread": round(spread, 3),
        "region_points_per_map": {k: round(v, 2) for k, v in region_means.items()},
        "region_spread": round(max(region_means.values()) / min(region_means.values()) - 1, 3),
        "coach_share": round(mean("coach_share"), 3),
        "captain_share": round(mean("captain_share"), 3),
        "legal_rate_mean": round(mean("legal_rate"), 3),
        "legal_rate_min": round(min(b["legal_rate"] for b in brackets), 3),
        "cheapest_core_over_budget": sum(b["cheapest_core"] > b["budget"] for b in brackets),
        "budget_never_binds": sum(b["dearest_core"] <= b["budget"] for b in brackets),
        "best_squad_budget_used": round(sum(b["best_cost"] / b["budget"] for b in brackets) / len(brackets), 3),
        "optimal_share_over_target": f"{sum(s > TARGETS['optimal_share'] for s in shares)} of {len(shares)}",
        "optimal_share_by_event": {k: {"median": round(sorted(v)[len(v) // 2], 3), "max": round(max(v), 3)}
                                   for k, v in sorted(share_by_event.items())},
        "optimal_share_max": round(shares[-1], 3) if shares else None,
        "optimal_share_median": round(shares[len(shares) // 2], 3) if shares else None,
        "optimal_coach_share_max": round(coach_shares[-1], 3) if coach_shares else None,
        "legal_rate_by_event": {k: round(sum(v) / len(v), 3) for k, v in sorted(legal_by_event.items())},
        "top_kills_on_a_map": max(r["top_kills"] for r in results),
        "targets_met": {
            "role_spread": spread <= TARGETS["role_spread"],
            "optimal_share": bool(shares) and shares[-1] <= TARGETS["optimal_share"],
            "coach_share": TARGETS["coach_share"][0] <= mean("coach_share") <= TARGETS["coach_share"][1],
            "affordable": all(b["cheapest_core"] <= b["budget"] < b["dearest_core"] for b in brackets)
                          and min(b["legal_rate"] for b in brackets) > 0,
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", type=int, default=4)
    ap.add_argument("--seeds-per-league", type=int, default=50)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default=None, help="also write the summary to this JSON file")
    args = ap.parse_args()

    jobs = [(league, league * 1000 + i)
            for league in range(1, args.leagues + 1) for i in range(args.seeds_per_league)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        finished = list(pool.map(run_season, jobs))

    summary = summarize(finished, load_rules())
    text = json.dumps(summary, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
