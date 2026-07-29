"""Regenerate the committed golden trace.

Run this only after reviewing why the trace changed -- a diff here means a rule,
a threshold, or a feature moved, and the diff is the review artifact.

    python -m tests.regen_golden
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.agents.rules import analyze
from src.agents.trace import build_trace, dumps
from src.agents.watchdog import verify
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

MATCH_ID = "agent-golden-1"
OUT = Path(__file__).with_name("golden") / f"trace_{MATCH_ID}.json"


def main() -> None:
    # ignore_cleanup_errors: Windows keeps the SQLite WAL files locked briefly
    # after close, which is not worth failing a regeneration over.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = init_db(str(Path(tmp) / "golden.db"))
        try:
            normalize(conn, get_source("sim").match(MATCH_ID), "sim")
            compute_for_match(conn, MATCH_ID)
            trace = build_trace(MATCH_ID, verify(conn, MATCH_ID, analyze(conn, MATCH_ID)))
        finally:
            conn.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(trace) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({trace['summary']['conclusions']} conclusions, "
          f"{trace['summary']['source_rows_cited']} source rows)")


if __name__ == "__main__":
    main()
