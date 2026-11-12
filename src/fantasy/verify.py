"""Watchdog for fantasy points: recompute from raw rows and compare with the store.

The coaching Watchdog re-reads a cited value. This goes one step further: points are
recalculated from the kill timeline, so a corrupted raw row, a corrupted feature row and
a changed rules file are all caught. A total that doesn't verify is dropped, never shown.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any

from src.agents.watchdog import TOLERANCE
from src.fantasy.scoring import SCOPE, compute_event_rows, load_rules, rules_version


@dataclass(frozen=True)
class Mismatch:
    match_id: str
    name: str
    reason: str

    @property
    def entity(self) -> str:
        return self.name.partition(":")[2]


def _stored(conn: sqlite3.Connection, event_id: str) -> dict[tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        """SELECT f.match_id, f.name, f.value, f.inputs_json FROM features f
           JOIN series_maps sm ON sm.match_id = f.match_id
           JOIN series s ON s.series_id = sm.series_id
           WHERE s.event_id = ? AND f.scope = ?""", (event_id, SCOPE)).fetchall()
    return {(r["match_id"], r["name"]): r for r in rows}


def _stored_version(row: sqlite3.Row) -> str | None:
    inputs = json.loads(row["inputs_json"])
    return inputs[0].get("version") if inputs and inputs[0].get("table") == "fantasy_rules" else None


def verify_points(conn: sqlite3.Connection, rules: dict[str, Any] | None = None) -> list[Mismatch]:
    rules = rules or load_rules()
    version = rules_version(rules)
    problems: list[Mismatch] = []

    for e in conn.execute("SELECT event_id FROM events ORDER BY ordinal").fetchall():
        expected = {(r.match_id, r.name): r for r in compute_event_rows(conn, e["event_id"], rules)}
        stored = _stored(conn, e["event_id"])

        for key, row in expected.items():
            match_id, name = key
            have = stored.get(key)
            if have is None:
                problems.append(Mismatch(match_id, name, "missing from store"))
            elif not math.isclose(have["value"], row.value, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                problems.append(Mismatch(match_id, name,
                                         f"store has {have['value']:g}, raw rows give {row.value:g}"))
            else:
                seen = _stored_version(have)
                if seen is not None and seen != version:
                    problems.append(Mismatch(match_id, name,
                                             f"scored under rules {seen}, current are {version}"))
        for match_id, name in stored.keys() - expected.keys():
            problems.append(Mismatch(match_id, name, "raw rows no longer support this row"))

    return sorted(problems, key=lambda m: (m.match_id, m.name))


def verified_totals(conn: sqlite3.Connection, rules: dict[str, Any] | None = None
                    ) -> dict[tuple[str, str], float]:
    """(match_id, entity) -> points, leaving out any entity with a mismatch on that map."""
    bad = {(m.match_id, m.entity) for m in verify_points(conn, rules)}
    totals: dict[tuple[str, str], float] = {}
    for r in conn.execute(
        """SELECT match_id, name, value FROM features
           WHERE scope = ? AND (name LIKE 'fp_total:%' OR name LIKE 'fp_coach_total:%')""", (SCOPE,)):
        key = (r["match_id"], r["name"].partition(":")[2])
        if key not in bad:
            totals[key] = r["value"]
    return totals
