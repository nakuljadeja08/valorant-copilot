"""The rule registry, and the deterministic pass that runs it.

Order here is the order rules fire, and conclusions come back sorted by
(severity, rule id) so the same match always produces the same sequence. The
golden-trace test depends on that.
"""

from __future__ import annotations

import sqlite3

from src.agents import analyst, economist
from src.agents.base import SEVERITIES, Conclusion, Rule
from src.agents.view import FeatureView

REGISTRY: list[Rule] = [*analyst.RULES, *economist.RULES]


def run_rules(view: FeatureView, rules: list[Rule] = REGISTRY) -> list[Conclusion]:
    conclusions: list[Conclusion] = []
    for rule in rules:
        conclusions.extend(rule.evaluate(view))

    return sorted(
        conclusions,
        key=lambda c: (SEVERITIES.index(c.severity), c.rule_id, c.text),
    )


def analyze(conn: sqlite3.Connection, match_id: str,
            rules: list[Rule] = REGISTRY) -> list[Conclusion]:
    return run_rules(FeatureView(conn, match_id), rules)
