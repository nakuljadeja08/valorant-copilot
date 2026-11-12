"""The fantasy store: match tables plus season tables, in their own database.

It must stay separate from the coaching store. `src.export.bundle` exports every row of
`matches`, and CI compares that export byte for byte, so one fantasy map in the coaching
store would leak into the dashboard and fail the drift check. `open_store` refuses any
database that already holds matches from elsewhere.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from src.fantasy.source import ProSeasonSource
from src.ingest.pipeline import normalize
from src.storage.init import connect, init as init_db

SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_PATH = "data/fantasy.db"
MATCH_ID_PREFIX = "vct27-"

# Children first, so foreign keys hold while a season is replaced.
_SEASON_TABLES = (
    "series_maps", "series", "event_prices", "event_rosters", "event_teams", "match_weeks",
    "events",
    "pro_coaches", "pro_players", "pro_teams",
    "features", "round_kill_assists", "round_kills", "round_player_stats", "rounds",
    "match_players", "ingest_log", "matches",
)


class ForeignStoreError(RuntimeError):
    """The target database holds matches that didn't come from a fantasy season."""


def _assert_fantasy_store(conn: sqlite3.Connection, path: str) -> None:
    has_matches = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
    if not has_matches:
        return
    foreign = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE match_id NOT LIKE ?", (f"{MATCH_ID_PREFIX}%",)
    ).fetchone()[0]
    if foreign:
        raise ForeignStoreError(
            f"{path} holds {foreign} non-fantasy matches. It looks like the coaching store; "
            f"use a separate database such as {DEFAULT_PATH}."
        )


def open_store(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or os.getenv("FANTASY_DB_PATH", DEFAULT_PATH)
    probe = connect(path)
    try:
        _assert_fantasy_store(probe, path)
    finally:
        probe.close()
    conn = init_db(path)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    return conn


def _insert_league(conn: sqlite3.Connection, source: ProSeasonSource) -> None:
    for t in source.teams():
        conn.execute("INSERT INTO pro_teams (team_id, name, region, tier, rating) VALUES (?,?,?,?,?)",
                     (t.team_id, t.name, t.region, t.tier, t.rating))
        conn.execute("INSERT INTO pro_coaches (coach_id, handle, team_id) VALUES (?,?,?)",
                     (t.coach.coach_id, t.coach.handle, t.team_id))
    for p in source.players():
        conn.execute("INSERT INTO pro_players (puuid, handle, region, base_role, skill) VALUES (?,?,?,?,?)",
                     (p.puuid, p.handle, p.region, p.base_role, p.skill))


def _insert_event(conn: sqlite3.Connection, ordinal: int, record, provenance: str) -> None:
    e = record.config
    conn.execute(
        """INSERT INTO events (event_id, ordinal, name, kind, starts_on, ends_on,
                               format_json, field_json, cities_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (e["id"], ordinal, e["name"], e["kind"], e["start"], e["end"],
         json.dumps(e["format"], sort_keys=True), json.dumps(e["field"], sort_keys=True),
         json.dumps(e["cities"], sort_keys=True, ensure_ascii=False)),
    )
    for week, deadline in sorted(record.deadlines.items()):
        conn.execute("INSERT INTO match_weeks (event_id, week_num, deadline_ms) VALUES (?,?,?)",
                     (e["id"], week, deadline))
    for entry in record.entries:
        conn.execute(
            """INSERT INTO event_teams (event_id, team_id, bracket, seed, placement, qualified_via)
               VALUES (?,?,?,?,?,?)""",
            (e["id"], entry.team_id, entry.bracket, entry.seed, entry.placement, entry.qualified_via),
        )
    for team_id, puuids in record.rosters.items():
        for puuid in puuids:
            conn.execute("INSERT INTO event_rosters (event_id, team_id, puuid) VALUES (?,?,?)",
                         (e["id"], team_id, puuid))
    for s in record.series:
        conn.execute(
            """INSERT INTO series (series_id, event_id, bracket, stage, round_num, week_num,
                                   scheduled_ms, best_of, team_a, team_b, maps_a, maps_b, winner)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s.series_id, e["id"], s.bracket, s.stage, s.round_num, s.week_num, s.scheduled_ms,
             s.best_of, s.team_a, s.team_b, s.maps_a, s.maps_b, s.winner),
        )
        for m in s.maps:
            normalize(conn, m.payload, provenance)
            conn.execute(
                """INSERT INTO series_maps (series_id, map_num, match_id, red_team, blue_team, winner)
                   VALUES (?,?,?,?,?,?)""",
                (s.series_id, m.map_num, m.match_id, m.red_team, m.blue_team, m.winner),
            )


def load_season(conn: sqlite3.Connection, source: ProSeasonSource) -> dict[str, int]:
    """Replace the stored season with this source's, all or nothing."""
    with conn:
        for table in _SEASON_TABLES:
            conn.execute(f"DELETE FROM {table}")
        _insert_league(conn, source)
        for ordinal, record in enumerate(source.events(), start=1):
            _insert_event(conn, ordinal, record, source.provenance)
    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    return {"events": count("events"), "series": count("series"), "maps": count("series_maps")}
