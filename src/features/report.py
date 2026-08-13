"""Demoable artifact for Phase 2: every feature for a match, its value, and the
source rows it was computed from.

Usage:
    python -m src.features.report --match <id>
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from src.features.baselines import BASELINE_PATH, Baselines
from src.features.constants import BUY_NAMES
from src.features.queries import player_roles
from src.features.role import ROLE_APPROX
from src.features.run import compute_for_match
from src.riot.resolve import default_resolver
from src.storage.init import init as init_db

DECODED_PREFIXES = ("buy_type:",)

# Order role features read like a scouting card: entry story, then impact, then kit.
ROLE_FEATURE_ORDER = [
    "first_contact_rate", "entry_success_rate", "first_death_rate", "entry_trade_rate",
    "multikill_rate", "assist_rate", "survival_rate", "utility_per_round",
]


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
    if not rounds:
        return f"{len(refs)} rows from {', '.join(tables)}"
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


def report_by_role(conn: sqlite3.Connection, match_id: str) -> str:
    """Per-player role card: role, each role feature, and the source-row lineage.

    Percentile-within-role and the baseline it cites arrive in R2b; this view is
    the raw role features with their provenance so the shape is demoable now.
    """
    if not conn.execute("SELECT 1 FROM matches WHERE match_id = ?", (match_id,)).fetchone():
        raise SystemExit(f"match {match_id!r} not found -- ingest it first")
    compute_for_match(conn, match_id)

    roles = player_roles(conn, match_id)
    resolver = default_resolver()
    agents = {r["puuid"]: r["character_id"] for r in conn.execute(
        "SELECT puuid, character_id FROM match_players WHERE match_id = ?", (match_id,))}
    # Within-role percentiles are the number the UI shows — load them if the
    # baseline artifact has been built (R2b). Absent is fine: fall back to raw.
    baseline = Baselines.load() if BASELINE_PATH.exists() else None

    # Collect player-scoped role features: name is `<feature>:<puuid>`.
    per_player: dict[str, dict[str, sqlite3.Row]] = {}
    for r in conn.execute(
        "SELECT name, value, inputs_json FROM features WHERE match_id=? AND scope='player'",
        (match_id,),
    ):
        feat, _, puuid = r["name"].partition(":")
        per_player.setdefault(puuid, {})[feat] = r

    lines = [f"Role report - match {match_id}", "=" * 64]
    if baseline is not None:
        lines.append(f"within-role percentiles vs baseline {baseline.version} "
                     f"({baseline.matches} matches); p = percentile among same-role peers, "
                     f"* = inverted (low raw is good)")
    order = {"duelist": 0, "initiator": 1, "controller": 2, "sentinel": 3}
    for puuid in sorted(per_player, key=lambda p: (order.get(roles.get(p), 9), p)):
        role = roles.get(puuid, "?")
        agent = resolver.agent_name(agents.get(puuid, ""))
        who = "you" if puuid == "hero" else puuid[:8]
        lines.append(f"\n{agent} ({role})  [{who}]")
        for feat in ROLE_FEATURE_ORDER:
            row = per_player[puuid].get(feat)
            if row is None:
                continue
            badge = "  role-approx" if feat in ROLE_APPROX else ""
            pct = ""
            if baseline is not None:
                res = baseline.percentile_within_role(role, feat, row["value"])
                if res is not None:
                    mark = "*" if res.inverted else " "
                    pct = f"p{res.oriented_percentile:>5.1f}{mark} "
            lines.append(f"    {feat:<20} {row['value']:<8.3f} {pct}"
                         f"{_lineage_summary(row['inputs_json'])}{badge}")

    # Cross-role synergy strip.
    team_rows = conn.execute(
        "SELECT name, value, inputs_json FROM features WHERE match_id=? AND scope='team' "
        "ORDER BY name", (match_id,),
    ).fetchall()
    if team_rows:
        lines.append("\ncross-role (team)")
        for r in team_rows:
            feat = r["name"].split(":")[0]
            badge = "  role-approx" if feat in ROLE_APPROX else ""
            lines.append(f"    {r['name']:<28} {r['value']:<8.3f} "
                         f"{_lineage_summary(r['inputs_json'])}{badge}")
    return "\n".join(lines)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="match id to report on")
    ap.add_argument("--by-role", action="store_true",
                    help="per-player role card instead of the flat feature table")
    args = ap.parse_args()

    conn = init_db()
    print(report_by_role(conn, args.match) if args.by_role else report(conn, args.match))
