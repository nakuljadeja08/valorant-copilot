"""Idempotent feature runner: raw rows -> features table.

Usage:
    python -m src.features.run --match <id>
    python -m src.features.run --all
"""

from __future__ import annotations

import argparse
import logging
import sqlite3

from src.features.base import Feature, FeatureRow
from src.features.registry import REGISTRY
from src.storage.init import init as init_db

log = logging.getLogger(__name__)


def compute_for_match(
    conn: sqlite3.Connection, match_id: str, features: list[Feature] = REGISTRY
) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    for feature in features:
        rows.extend(feature.compute(conn, match_id))

    with conn:
        for r in rows:
            conn.execute(
                """INSERT OR REPLACE INTO features
                   (match_id, round_num, scope, name, value, inputs_json)
                   VALUES (?,?,?,?,?,?)""",
                (r.match_id, r.round_num, r.scope, r.name, r.value, r.inputs_json()),
            )
    return rows


def run(match_id: str | None, all_matches: bool) -> dict:
    conn = init_db()
    if all_matches:
        match_ids = [row["match_id"] for row in conn.execute("SELECT match_id FROM matches")]
    else:
        match_ids = [match_id]

    stats = {"matches": 0, "features": 0}
    for mid in match_ids:
        rows = compute_for_match(conn, mid)
        stats["matches"] += 1
        stats["features"] += len(rows)
        log.info("match %s: %d feature rows", mid, len(rows))

    return stats


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--match", help="compute features for one match id")
    group.add_argument("--all", action="store_true", help="compute features for every ingested match")
    args = ap.parse_args()

    result = run(args.match, args.all)
    print(f"features complete: {result}")
