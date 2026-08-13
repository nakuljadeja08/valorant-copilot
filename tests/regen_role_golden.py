"""Regenerate the committed role-debrief trace golden.

Run only after reviewing why the role trace changed -- a diff here means a role
rule, a threshold, the sim, or the committed baseline moved, and the diff is the
review artifact. The role trace is scored against the committed baseline artifact,
so rebuild that first if it changed:

    python -m src.features.baselines --build
    python -m tests.regen_role_golden
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.agents.role_coach import analyze_roles
from src.agents.trace import build_trace, dumps
from src.agents.watchdog import verify_role
from src.features.baselines import Baselines
from src.features.queries import player_roles
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

MATCH_ID = "role-golden-1"
OUT = Path(__file__).with_name("golden") / f"role_trace_{MATCH_ID}.json"


def build_role_trace() -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = init_db(str(Path(tmp) / "golden.db"))
        try:
            normalize(conn, get_source("sim").match(MATCH_ID), "sim")
            compute_for_match(conn, MATCH_ID)
            baseline = Baselines.load()
            roles = player_roles(conn, MATCH_ID)
            conclusions = verify_role(
                conn, MATCH_ID, analyze_roles(conn, MATCH_ID, baseline), baseline, roles)
            return build_trace(MATCH_ID, conclusions)
        finally:
            conn.close()


def main() -> None:
    trace = build_role_trace()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(trace) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({trace['summary']['conclusions']} conclusions, "
          f"{trace['summary']['verified']} verified, "
          f"{trace['summary']['source_rows_cited']} source rows)")


if __name__ == "__main__":
    main()
