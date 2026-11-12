"""Build the simulated season into the fantasy store and print the results.

Everything printed is read back from the store, so this also shows what downstream
phases will see. All teams and players are fictional.

Usage:
    python -m src.fantasy.season --seed 1337
    python -m src.fantasy.season --seed 1337 --bracket   # every series, round by round
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3

from src.fantasy.scoring import score_season
from src.fantasy.source import get_pro_source
from src.fantasy.store import load_season, open_store


def _team_names(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM pro_teams")}


def _print_bracket(conn: sqlite3.Connection, event_id: str, bracket: str,
                   names: dict[str, str]) -> None:
    rows = conn.execute(
        """SELECT stage, round_num, team_a, team_b, maps_a, maps_b FROM series
           WHERE event_id = ? AND bracket = ? ORDER BY round_num, stage DESC, series_id""",
        (event_id, bracket),
    )
    for r in rows:
        print(f"      R{r['round_num']} {r['stage']:<5}  "
              f"{names[r['team_a']]} {r['maps_a']}-{r['maps_b']} {names[r['team_b']]}")


def report(conn: sqlite3.Connection, show_bracket: bool = False) -> None:
    names = _team_names(conn)
    for e in conn.execute("SELECT * FROM events ORDER BY ordinal").fetchall():
        assumed = json.loads(e["format_json"]).get("assumed") or json.loads(e["field_json"]).get("assumed")
        tag = "  [assumed format or field]" if assumed else ""
        print(f"\n{e['name']}  {e['starts_on']} to {e['ends_on']}{tag}")

        brackets = conn.execute(
            "SELECT DISTINCT bracket FROM event_teams WHERE event_id = ? ORDER BY bracket",
            (e["event_id"],),
        ).fetchall()
        for b in brackets:
            bracket = b["bracket"]
            top = conn.execute(
                """SELECT team_id, placement FROM event_teams
                   WHERE event_id = ? AND bracket = ? ORDER BY placement, seed LIMIT 3""",
                (e["event_id"], bracket),
            ).fetchall()
            podium = ", ".join(f"{r['placement']}. {names[r['team_id']]}" for r in top)
            print(f"  {bracket:<9} {podium}")
            if show_bracket:
                _print_bracket(conn, e["event_id"], bracket, names)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "1337")))
    ap.add_argument("--db", default=None, help="store path (default: FANTASY_DB_PATH or data/fantasy.db)")
    ap.add_argument("--bracket", action="store_true", help="print every series, round by round")
    args = ap.parse_args()

    store = open_store(args.db)
    totals = load_season(store, get_pro_source(args.seed))
    scored = score_season(store)
    print(f"SIMULATED season, seed {args.seed}. Teams and players are fictional.")
    print(f"{totals['events']} events, {totals['series']} series, {totals['maps']} maps, "
          f"{scored['feature_rows']} fantasy feature rows")
    report(store, show_bracket=args.bracket)
