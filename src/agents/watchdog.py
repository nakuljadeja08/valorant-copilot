"""Watchdog: re-check every cited number against the store before anyone reads it.

The rules read features through `FeatureView`, which snapshots the table into
memory. The Watchdog deliberately does *not* reuse that snapshot -- it goes back
to SQL for each citation and compares. If a value drifted, was recomputed under
different thresholds, or was never there at all, the claim is marked
`unverified` and excluded from the report rather than quietly printed.

This is the check that makes "no hallucinated stats by construction" a property
of the pipeline instead of a promise.
"""

from __future__ import annotations

import math
import sqlite3

from src.agents.base import Conclusion

# Values round-trip through SQLite REAL, so an exact match is the norm; the
# tolerance exists for float formatting drift, not for genuine disagreement.
TOLERANCE = 1e-9


def _stored_value(conn: sqlite3.Connection, match_id: str, name: str,
                  round_num: int, scope: str) -> float | None:
    row = conn.execute(
        """SELECT value FROM features
           WHERE match_id = ? AND name = ? AND round_num = ? AND scope = ?""",
        (match_id, name, round_num, scope),
    ).fetchone()
    return None if row is None else row["value"]


def verify(conn: sqlite3.Connection, match_id: str,
           conclusions: list[Conclusion]) -> list[Conclusion]:
    """Stamp every conclusion with a verdict. Mutates and returns the list."""
    for c in conclusions:
        if not c.citations:
            c.verified = False
            c.unverified_reason = "claim cites no feature rows"
            continue

        problems = []
        for ref in c.citations:
            stored = _stored_value(conn, match_id, ref.name, ref.round_num, ref.scope)
            if stored is None:
                problems.append(f"{ref.name}@R{ref.round_num} missing from store")
            elif not math.isclose(stored, ref.value, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                problems.append(
                    f"{ref.name}@R{ref.round_num} cited {ref.value:g}, store has {stored:g}"
                )

        c.verified = not problems
        c.unverified_reason = "; ".join(problems) if problems else None

    return conclusions


def verified_only(conclusions: list[Conclusion]) -> list[Conclusion]:
    """A conclusion that was never checked is treated exactly like a failed one."""
    return [c for c in conclusions if c.verified is True]
