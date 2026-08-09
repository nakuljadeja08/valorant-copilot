"""Resumable ingest: MatchSource -> normalized local store.

Design points that matter:

- **Idempotent.** Re-running never duplicates; `INSERT OR REPLACE` keyed on natural PKs.
- **Resumable.** `ingest_log` tracks per-match status, so a dev-key expiry or crash
  mid-run resumes exactly where it stopped.
- **Provenance.** Every match row records whether it came from 'sim' or 'live'.

Usage:
    python -m src.ingest.pipeline --source sim --matches 200
    python -m src.ingest.pipeline --source live --puuid <PUUID>   # needs production key
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from typing import Any

from src.riot.adapter import get_source
from src.storage.init import init as init_db

log = logging.getLogger(__name__)


def normalize(conn: sqlite3.Connection, m: dict[str, Any], source: str,
              hero_puuid: str | None = None) -> None:
    info = m["matchInfo"]

    # Only record the focal player when they actually appear in the roster. A puuid
    # we queried but that isn't in the match tells us nothing about a side, and
    # storing it anyway would let the UI attribute a record to a team at random.
    roster = {p["puuid"] for p in m.get("players", [])}
    hero = hero_puuid if hero_puuid in roster else None

    conn.execute(
        """INSERT OR REPLACE INTO matches
           (match_id, map_id, game_length_ms, game_start_ms, queue_id, season_id,
            is_completed, source, hero_puuid)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (info["matchId"], info["mapId"], info.get("gameLengthMillis"),
         info.get("gameStartMillis"), info.get("queueId"), info.get("seasonId"),
         int(info.get("isCompleted", True)), source, hero),
    )

    for p in m.get("players", []):
        stats = p.get("stats") or {}
        conn.execute(
            """INSERT OR REPLACE INTO match_players
               (match_id, puuid, team_id, character_id, competitive_tier, score, kills, deaths, assists)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (info["matchId"], p["puuid"], p["teamId"], p["characterId"],
             p.get("competitiveTier"), stats.get("score"),
             stats.get("kills"), stats.get("deaths"), stats.get("assists")),
        )

    for r in m.get("roundResults", []):
        conn.execute(
            """INSERT OR REPLACE INTO rounds
               (match_id, round_num, winning_team, round_result, round_ceremony,
                plant_site, plant_ms, defuse_ms)
               VALUES (?,?,?,?,?,?,?,?)""",
            (info["matchId"], r["roundNum"], r.get("winningTeam"), r.get("roundResult"),
             r.get("roundCeremony"), r.get("plantSite") or None,
             r.get("plantRoundTime") or None, r.get("defuseRoundTime") or None),
        )
        for ps in r.get("playerStats", []):
            econ = ps.get("economy") or {}
            conn.execute(
                """INSERT OR REPLACE INTO round_player_stats
                   (match_id, round_num, puuid, loadout_value, spent, remaining,
                    armor_id, weapon_id, kills, damage, score)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (info["matchId"], r["roundNum"], ps["puuid"],
                 econ.get("loadoutValue"), econ.get("spent"), econ.get("remaining"),
                 econ.get("armor") or None, econ.get("weapon") or None,
                 ps.get("kills"),
                 sum(d.get("damage", 0) for d in ps.get("damage", []) if isinstance(d, dict)),
                 ps.get("score")),
            )


def run(source_name: str, puuid: str = "hero", limit: int | None = None) -> dict:
    conn = init_db()
    src = get_source(source_name)

    ids = src.matchlist(puuid)
    if limit:
        ids = ids[:limit]

    done = {r["match_id"] for r in conn.execute(
        "SELECT match_id FROM ingest_log WHERE status='done'")}
    todo = [i for i in ids if i not in done]
    log.info("matchlist: %d total, %d already ingested, %d to do", len(ids), len(ids) - len(todo), len(todo))

    stats = {"done": 0, "failed": 0, "skipped": len(ids) - len(todo)}
    for mid in todo:
        try:
            payload = src.match(mid)
            with conn:
                normalize(conn, payload, source_name, hero_puuid=puuid)
                conn.execute(
                    "INSERT OR REPLACE INTO ingest_log (match_id, status, attempts) "
                    "VALUES (?, 'done', COALESCE((SELECT attempts FROM ingest_log WHERE match_id=?),0)+1)",
                    (mid, mid))
            stats["done"] += 1
        except Exception as e:  # noqa: BLE001 — log and continue; resumability is the point
            log.warning("failed %s: %s", mid, e)
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ingest_log (match_id, status, attempts, last_error) "
                    "VALUES (?, 'failed', COALESCE((SELECT attempts FROM ingest_log WHERE match_id=?),0)+1, ?)",
                    (mid, mid, str(e)[:500]))
            stats["failed"] += 1

    return stats


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim", "live"], default=None)
    ap.add_argument("--puuid", default="hero")
    ap.add_argument("--matches", type=int, default=None)
    args = ap.parse_args()

    result = run(args.source, args.puuid, args.matches)
    print(f"ingest complete: {result}")
