"""Decision trace: raw rows -> feature rows -> rule id -> conclusion.

Serialized per match. Deliberately carries no timestamps and sorts every
collection, so the same match produces byte-identical JSON on every run -- that
determinism is what the golden-file test asserts, and it is also what makes a
trace diffable when a rule changes.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import Conclusion
from src.agents.view import FeatureRef

TRACE_VERSION = 1


def _ref_key(ref: dict[str, Any]) -> tuple:
    return (ref.get("table", ""), ref.get("round_num", -1), ref.get("puuid", ""))


def _evidence(ref: FeatureRef) -> dict[str, Any]:
    """One feature row plus the raw rows it was computed from."""
    return {
        "feature": {
            "name": ref.name,
            "scope": ref.scope,
            "round_num": ref.round_num,
            "value": ref.value,
        },
        "source_rows": sorted(ref.inputs, key=_ref_key),
    }


def conclusion_trace(c: Conclusion) -> dict[str, Any]:
    trace = {
        "rule_id": c.rule_id,
        "agent": c.agent,
        "severity": c.severity,
        "claim": c.text,
        "verified": c.verified,
        "unverified_reason": c.unverified_reason,
        "evidence": [
            _evidence(ref)
            for ref in sorted(c.citations, key=lambda r: (r.name, r.round_num))
        ],
    }
    # Role claims add the middle link of the chain — the within-role percentile and
    # the baseline it was scored against. Omitted entirely on base claims so their
    # trace JSON stays byte-identical (the base golden depends on that).
    if c.percentile is not None:
        trace["within_role_percentile"] = c.percentile
        trace["baseline_version"] = c.baseline_version
    return trace


def build_trace(match_id: str, conclusions: list[Conclusion]) -> dict[str, Any]:
    traced = [conclusion_trace(c) for c in conclusions]
    return {
        "trace_version": TRACE_VERSION,
        "match_id": match_id,
        "summary": {
            "conclusions": len(traced),
            "verified": sum(1 for t in traced if t["verified"] is True),
            "unverified": sum(1 for t in traced if t["verified"] is not True),
            "source_rows_cited": sum(
                len(e["source_rows"]) for t in traced for e in t["evidence"]
            ),
        },
        "conclusions": traced,
    }


def dumps(trace: dict[str, Any]) -> str:
    return json.dumps(trace, indent=2, sort_keys=True)


def allowed_numerals(conclusions: list[Conclusion]) -> set[str]:
    """Every numeric token the report is permitted to contain.

    Sourced from the verified claims themselves plus the raw cited values, so a
    writer that rephrases stays inside the set and one that invents a statistic
    does not.
    """
    allowed: set[str] = set()
    for c in conclusions:
        allowed |= c.numerals()
        for ref in c.citations:
            allowed.add(f"{ref.value:g}")
            allowed.add(str(int(ref.value)) if ref.value.is_integer() else f"{ref.value:.2f}")
    return allowed
