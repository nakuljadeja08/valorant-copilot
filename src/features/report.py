"""Demoable artifact for Phase 2: every feature for a match, its value, and the
source rows it was computed from.

Usage:
    python -m src.features.report --match <id>
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from src.features.constants import BUY_NAMES
from src.features.run import compute_for_match
from src.storage.init import init as init_db

DECODED_PREFIXES = ("buy_type:",)


def _display_value(name: str, value: float) -> str:
    if name.startswith(DECODED_PREFIXES):
        return f"{value:g} ({BUY_NAMES.get(value, '?')})"
    return f"{value:g}"


def _lineage_summary(inputs_json: str) -> str:
    refs = json.loads(inputs_json)
    if not refs:
        return "(no lineage)"
    tables = sorted({r["table"] for r in refs})
    rounds = sorted({r["round_num"] for r in refs if "round_num" in r})
    round_span = f"R{rounds[0]}" if len(rounds) == 1 else f"R{rounds[0]}-R{rounds[-1]}"
    return f"{len(refs)} rows from {', '.join(tables)} ({round_span})"


def report(conn: sqlite3.Connection, match_id: str) -> str:
    exists = conn.execute(
        "SELECT 1 FROM matches WHERE match_id = ?", (match_id,)
    ).fetchone()
    if not exists:
        raise SystemExit(f"match {match_id!r} not found -- ingest it first")

    compute_for_match(conn, match_id)  # idempotent: ensures the report reflects current rules

    rows = conn.execute(
        """SELECT round_num, scope, name, value, inputs_json
           FROM features WHERE match_id = ?
           ORDER BY round_num, scope, name""",
        (match_id,),
    ).fetchall()

    lines = [f"Feature report - match {match_id}", "=" * 60]
    header = f"{'round':>6}  {'scope':<11} {'name':<28} {'value':<16} lineage"
    lines.append(header)
    lines.append("-" * len(header))
    for r in rows:
        round_label = "match" if r["round_num"] == -1 else str(r["round_num"])
        lines.append(
            f"{round_label:>6}  {r['scope']:<11} {r['name']:<28} "
            f"{_display_value(r['name'], r['value']):<16} {_lineage_summary(r['inputs_json'])}"
        )
    lines.append("-" * len(header))
    lines.append(f"{len(rows)} feature rows total")
    return "\n".join(lines)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="match id to report on")
    args = ap.parse_args()

    print(report(init_db(), args.match))
