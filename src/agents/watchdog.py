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


# Percentiles are computed, not stored as REAL, so allow a hair more slack than the
# raw-value tolerance for display rounding on the way into a claim.
PCT_TOLERANCE = 0.05


def verify_role(conn: sqlite3.Connection, match_id: str, conclusions: list[Conclusion],
                baseline, roles: dict[str, str]) -> list[Conclusion]:
    """Run the base verify, then re-query every role claim's percentile.

    A role claim states a within-role percentile ("9th among Sentinels"). The base
    check confirms the raw feature value still matches the store; this adds the
    second half — recompute the percentile from the cited baseline and confirm it
    agrees, and that the baseline version the claim named is the one in hand. A
    drifted value, a recomputed distribution, or a swapped baseline all surface here
    as `unverified` rather than a plausible-looking wrong number.
    """
    verify(conn, match_id, conclusions)
    for c in conclusions:
        if c.percentile is None:
            continue
        if c.verified is not True:
            continue  # base check already failed; don't overwrite its reason
        if c.baseline_version != baseline.version:
            c.verified = False
            c.unverified_reason = (
                f"claim cites baseline {c.baseline_version}, have {baseline.version}")
            continue
        # The signature feature is the sole player-scoped citation: `<feature>:<puuid>`.
        ref = next((r for r in c.citations if r.scope == "player"), None)
        if ref is None:
            c.verified = False
            c.unverified_reason = "role claim carries a percentile but cites no player feature"
            continue
        feature, _, puuid = ref.name.partition(":")
        stored = _stored_value(conn, match_id, ref.name, ref.round_num, ref.scope)
        role = roles.get(puuid)
        result = baseline.percentile_within_role(role, feature, stored) if role else None
        if result is None:
            c.verified = False
            c.unverified_reason = f"no {role} baseline for {feature} to re-query"
        elif abs(result.oriented_percentile - c.percentile) > PCT_TOLERANCE:
            c.verified = False
            c.unverified_reason = (
                f"percentile drift: claim {c.percentile:.1f}, "
                f"baseline re-query {result.oriented_percentile:.1f}")
    return conclusions


def verified_only(conclusions: list[Conclusion]) -> list[Conclusion]:
    """A conclusion that was never checked is treated exactly like a failed one."""
    return [c for c in conclusions if c.verified is True]
