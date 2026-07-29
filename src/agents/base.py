"""Conclusion + Rule protocol.

A rule is the only thing allowed to turn features into a claim, and a claim can
only be phrased from values it cites. The LLM layer downstream may rewrite the
prose but never the numbers -- `numerals()` is what that check is enforced
against.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from src.agents.view import FeatureRef, FeatureView

# Severity, most to least urgent. Report ordering and the writer's emphasis both
# key off this list, so it is the single place the ranking is defined.
SEVERITIES = ["critical", "warning", "info"]

_NUMERAL = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Conclusion:
    rule_id: str
    agent: str
    severity: str
    text: str
    citations: list[FeatureRef] = field(default_factory=list)

    # Set by the Watchdog. None means "not yet checked" -- a conclusion in that
    # state must never reach a report.
    verified: bool | None = None
    unverified_reason: str | None = None

    def numerals(self) -> set[str]:
        """Every numeric token this claim is entitled to state."""
        return set(_NUMERAL.findall(self.text))


class Rule(Protocol):
    """Declares what it reads, when it fires, and what it concludes."""

    id: str
    agent: str
    severity: str
    inputs: list[str]  # feature names (or `name:{team}` patterns) the rule reads

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        ...


def pct(value: float) -> str:
    """Rates render as whole percents so the numeral check has a stable token."""
    return f"{round(value * 100)}"
