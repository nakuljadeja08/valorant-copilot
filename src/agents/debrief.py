"""Demoable artifact for Phase 3: the debrief, plus the trace behind every sentence.

Usage:
    python -m src.agents.debrief --match <id>
    python -m src.agents.debrief --match <id> --no-llm
    python -m src.agents.debrief --match <id> --trace-out trace.json
"""

from __future__ import annotations

import argparse
import sqlite3

from src.agents.base import Conclusion
from src.agents.role_coach import analyze_roles
from src.agents.rules import analyze
from src.agents.trace import build_trace, dumps
from src.agents.watchdog import verified_only, verify, verify_role
from src.agents.writer import ROLE_SYSTEM, Report, write_report
from src.features.baselines import BASELINE_PATH, Baselines
from src.features.queries import player_roles
from src.features.run import compute_for_match
from src.storage.init import init as init_db


def debrief(conn: sqlite3.Connection, match_id: str,
            use_llm: bool = True) -> tuple[Report, list[Conclusion], dict]:
    exists = conn.execute(
        "SELECT 1 FROM matches WHERE match_id = ?", (match_id,)
    ).fetchone()
    if not exists:
        raise SystemExit(f"match {match_id!r} not found -- ingest it first")

    compute_for_match(conn, match_id)  # idempotent: debrief reflects current features

    conclusions = verify(conn, match_id, analyze(conn, match_id))
    report = write_report(verified_only(conclusions), use_llm)
    return report, conclusions, build_trace(match_id, conclusions)


def role_debrief(conn: sqlite3.Connection, match_id: str,
                 use_llm: bool = True) -> tuple[Report, list[Conclusion], dict]:
    """The per-player role debrief (R3): claims scored within-role, percentile-verified."""
    if not conn.execute("SELECT 1 FROM matches WHERE match_id = ?", (match_id,)).fetchone():
        raise SystemExit(f"match {match_id!r} not found -- ingest it first")
    if not BASELINE_PATH.exists():
        raise SystemExit("no baseline artifact -- run `python -m src.features.baselines --build`")

    compute_for_match(conn, match_id)
    baseline = Baselines.load()
    roles = player_roles(conn, match_id)
    conclusions = verify_role(conn, match_id, analyze_roles(conn, match_id, baseline),
                              baseline, roles)
    report = write_report(verified_only(conclusions), use_llm, system=ROLE_SYSTEM)
    return report, conclusions, build_trace(match_id, conclusions)


def render(match_id: str, report: Report, conclusions: list[Conclusion], trace: dict) -> str:
    header = f"Debrief -- match {match_id}"
    lines = [header, "=" * len(header), ""]

    if report.used_llm:
        lines.append("[LLM-phrased, numeral post-check passed]")
    elif report.error:
        lines.append(f"[template -- LLM unavailable: {report.error}]")
    else:
        lines.append("[template (--no-llm)]")
    if report.rejected_numerals:
        lines.append(f"[numeral post-check rejected: {', '.join(report.rejected_numerals)}]")
    lines.append("")
    lines.append(report.text)
    lines.append("")

    s = trace["summary"]
    lines.append("-" * len(header))
    lines.append(
        f"{s['verified']} verified / {s['conclusions']} conclusions, "
        f"citing {s['source_rows_cited']} raw source rows"
    )

    unverified = [c for c in conclusions if c.verified is not True]
    for c in unverified:
        lines.append(f"  EXCLUDED {c.rule_id}: {c.unverified_reason}")

    return "\n".join(lines)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="match id to debrief")
    ap.add_argument("--no-llm", action="store_true",
                    help="emit template text; runs with no API key")
    ap.add_argument("--by-role", action="store_true",
                    help="per-player role debrief (within-role percentiles) instead of the team debrief")
    ap.add_argument("--trace-out", help="write the decision trace JSON to this path")
    args = ap.parse_args()

    conn = init_db()
    run = role_debrief if args.by_role else debrief
    report, conclusions, trace = run(conn, args.match, use_llm=not args.no_llm)
    print(render(args.match, report, conclusions, trace))

    if args.trace_out:
        with open(args.trace_out, "w", encoding="utf-8") as fh:
            fh.write(dumps(trace))
        print(f"\ntrace written to {args.trace_out}")
