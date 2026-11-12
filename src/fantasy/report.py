"""Print where a player's or coach's points came from, down to the raw rows.

Usage:
    python -m src.fantasy.report --player <handle or puuid> --event kickoff
    python -m src.fantasy.report --coach <handle or coach_id> --event kickoff --rows
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from src.fantasy.scoring import SCOPE
from src.fantasy.store import open_store


def _find(conn: sqlite3.Connection, table: str, id_col: str, needle: str) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {id_col} = ? OR handle = ? COLLATE NOCASE",  # noqa: S608
        (needle, needle)).fetchone()
    if row is None:
        raise SystemExit(f"no match for {needle!r} in {table}")
    return row


def _describe(ref: dict) -> str:
    table = ref.get("table", "?")
    detail = ", ".join(f"{k}={v}" for k, v in sorted(ref.items()) if k not in ("table", "match_id"))
    return f"{table}({detail})"


def report(conn: sqlite3.Connection, entity: str, label: str, event_id: str, show_rows: bool) -> float:
    maps = conn.execute(
        """SELECT DISTINCT f.match_id, s.series_id, s.round_num, s.stage, sm.map_num
           FROM features f
           JOIN series_maps sm ON sm.match_id = f.match_id
           JOIN series s ON s.series_id = sm.series_id
           WHERE s.event_id = ? AND f.scope = ? AND f.name LIKE ?
           ORDER BY s.scheduled_ms, sm.map_num""",
        (event_id, SCOPE, f"%:{entity}")).fetchall()
    if not maps:
        raise SystemExit(f"{label} scored nothing at {event_id}")

    event_total = 0.0
    print(f"{label} at {event_id}")
    for m in maps:
        rows = conn.execute(
            """SELECT name, value, inputs_json FROM features
               WHERE match_id = ? AND scope = ? AND name LIKE ? ORDER BY name""",
            (m["match_id"], SCOPE, f"%:{entity}")).fetchall()
        total = next(r["value"] for r in rows if r["name"].partition(":")[0] in ("fp_total", "fp_coach_total"))
        event_total += total
        print(f"\n  R{m['round_num']} {m['stage']} map {m['map_num']}  ({m['match_id']}): {total:g} points")
        for r in rows:
            rule = r["name"].partition(":")[0]
            if rule in ("fp_total", "fp_coach_total"):
                continue
            inputs = json.loads(r["inputs_json"])
            head = inputs[0]
            print(f"    {head['rule']:<20} {head['count']:>3} x {head['points_each']:>2} = {r['value']:g}")
            if show_rows:
                for ref in inputs[1:]:
                    print(f"        {_describe(ref)}")
    print(f"\n  Event total: {event_total:g} points across {len(maps)} maps")
    return event_total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--player", help="handle or puuid")
    who.add_argument("--coach", help="handle or coach_id")
    ap.add_argument("--event", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--rows", action="store_true", help="also list the raw rows behind each line")
    args = ap.parse_args()

    store = open_store(args.db)
    if args.player:
        row = _find(store, "pro_players", "puuid", args.player)
        report(store, row["puuid"], row["handle"], args.event, args.rows)
    else:
        row = _find(store, "pro_coaches", "coach_id", args.coach)
        report(store, row["coach_id"], f"Coach {row['handle']}", args.event, args.rows)
