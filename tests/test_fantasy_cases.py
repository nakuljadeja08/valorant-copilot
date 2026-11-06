"""Shared squad cases: the same file runs against `web/src/lib/fantasy.js` in `web/test`.

If a rule changes, both implementations must change with it, or one of the two suites
fails. Expected values were generated from this implementation and checked by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.fantasy.squads import (
    Squad, chip_half, free_transfers_next, score_week, transfer_hit, transfers_made, validate_squad,
)

CASES = json.loads((Path(__file__).parent / "fixtures" / "fantasy_cases.json").read_text(encoding="utf-8"))
RULES = CASES["rules"]


def _squad(s: dict) -> Squad:
    return Squad(tuple(s["starters"]), tuple(s["subs"]), tuple(s["coaches"]), s["captain"], s["vice"])


@pytest.mark.parametrize("case", CASES["validate"], ids=lambda c: c["name"])
def test_validate(case):
    assert validate_squad(_squad(case["squad"]), CASES["prices"], RULES, case["event_kind"]) == case["errors"]


@pytest.mark.parametrize("case", CASES["score"], ids=lambda c: c["name"])
def test_score(case):
    assert score_week(_squad(case["squad"]), case["points"], RULES, case["chip"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["transfers"], ids=lambda c: c["name"])
def test_transfers(case):
    made = transfers_made(_squad(case["previous"]), _squad(case["squad"]))
    assert (made, transfer_hit(made, case["free"], RULES),
            free_transfers_next(case["free"], made, RULES)) == (case["made"], case["hit"], case["free_next"])


@pytest.mark.parametrize("case", CASES["chip_half"], ids=lambda c: c["event_id"])
def test_chip_half(case):
    assert chip_half(case["event_id"], case["event_order"], RULES) == case["half"]


def test_cases_cover_every_rule_the_game_uses():
    names = {c["name"] for group in ("validate", "score", "transfers") for c in CASES[group]}
    for needed in ("over budget at a regional event", "auto-sub fills a starter who played no map",
                   "vice takes the armband", "triple captain", "bench boost scores every sub",
                   "two transfers, one free"):
        assert needed in names
    rules = json.loads(Path("src/fantasy/rules_2027.json").read_text(encoding="utf-8"))
    assert {k: rules[k] for k in RULES} == RULES, "fixture rules drifted from rules_2027.json"
