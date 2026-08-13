"""R3c: the tests that make the role decision trace trustworthy.

Mirrors the base-agent trust tests, for the role layer:
  - a fixed match produces byte-identical role-trace JSON (golden file)
  - the Watchdog catches a role claim whose percentile no longer re-queries
  - the Watchdog catches a swapped baseline version
  - the Watchdog catches a drifted raw feature value (base path still applies)
  - the numeral post-check rejects an invented percentile
  - --no-llm produces a complete role debrief with no API key
"""

import json
from pathlib import Path

import pytest

from src.agents.debrief import role_debrief
from src.agents.role_coach import analyze_roles
from src.agents.trace import build_trace, dumps
from src.agents.watchdog import verified_only, verify_role
from src.agents.writer import check_numerals
from src.features.baselines import Baselines, build_from_corpus
from src.features.queries import player_roles
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db
from tests.regen_role_golden import MATCH_ID as GOLDEN_MATCH
from tests.regen_role_golden import build_role_trace

GOLDEN = Path(__file__).with_name("golden") / f"role_trace_{GOLDEN_MATCH}.json"


def _store(tmp_path, match_id):
    conn = init_db(str(tmp_path / "t.db"))
    normalize(conn, get_source("sim").match(match_id), "sim", hero_puuid="hero")
    compute_for_match(conn, match_id)
    return conn


def _conclusions(conn, match_id, baseline):
    roles = player_roles(conn, match_id)
    return verify_role(conn, match_id, analyze_roles(conn, match_id, baseline), baseline, roles)


class TestGoldenRoleTrace:
    def test_role_trace_matches_committed_golden(self):
        """Role rule/threshold/sim/baseline changed? Review the diff, then
        regenerate with `python -m tests.regen_role_golden`."""
        actual = build_role_trace()
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert actual == expected

    def test_golden_carries_the_percentile_chain(self):
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        pct_claims = [c for c in expected["conclusions"] if "within_role_percentile" in c]
        assert pct_claims, "golden should contain percentile-scored role claims"
        for c in pct_claims:
            assert c["baseline_version"], "a percentile claim must name its baseline"


class TestWatchdog:
    def test_corrupted_percentile_is_unverified(self, tmp_path):
        conn = _store(tmp_path, "role-wd-1")
        baseline = Baselines.load()
        cons = analyze_roles(conn, "role-wd-1", baseline)
        target = next(c for c in cons if c.percentile is not None)
        target.percentile += 40.0  # a percentile the baseline will not re-query to
        verify_role(conn, "role-wd-1", cons, baseline, player_roles(conn, "role-wd-1"))
        assert target.verified is False
        assert "percentile drift" in target.unverified_reason

    def test_swapped_baseline_version_is_unverified(self, tmp_path):
        conn = _store(tmp_path, "role-wd-2")
        committed = Baselines.load()
        cons = analyze_roles(conn, "role-wd-2", committed)
        pct_claim = next(c for c in cons if c.percentile is not None)
        # A different corpus yields a different version; the claims still cite the old one.
        other = build_from_corpus([f"role-wd-other-{i}" for i in range(30)])
        assert other.version != committed.version
        verify_role(conn, "role-wd-2", cons, other, player_roles(conn, "role-wd-2"))
        assert pct_claim.verified is False
        assert "baseline" in pct_claim.unverified_reason

    def test_drifted_raw_value_is_unverified(self, tmp_path):
        conn = _store(tmp_path, "role-wd-3")
        baseline = Baselines.load()
        cons = analyze_roles(conn, "role-wd-3", baseline)
        target = next(c for c in cons if c.percentile is not None)
        ref = target.citations[0]
        with conn:  # corrupt the stored feature the claim cites
            conn.execute(
                "UPDATE features SET value = value + 0.5 WHERE match_id=? AND name=? AND scope=?",
                ("role-wd-3", ref.name, ref.scope))
        verify_role(conn, "role-wd-3", cons, baseline, player_roles(conn, "role-wd-3"))
        assert target.verified is False


class TestNumeralCheck:
    def test_invented_percentile_is_rejected(self, tmp_path):
        conn = _store(tmp_path, "role-num-1")
        cons = verified_only(_conclusions(conn, "role-num-1", Baselines.load()))
        assert cons, "need at least one verified role claim"
        draft = "You sat in the 999th percentile among Duelists, a career year."
        assert "999" in check_numerals(draft, cons)

    def test_faithful_rephrase_passes(self, tmp_path):
        conn = _store(tmp_path, "role-num-2")
        cons = verified_only(_conclusions(conn, "role-num-2", Baselines.load()))
        # Rephrase using only numbers the claims already state.
        draft = " ".join(c.text for c in cons)
        assert check_numerals(draft, cons) == []


class TestNoLlmDebrief:
    def test_no_llm_produces_a_complete_role_debrief(self, tmp_path):
        conn = _store(tmp_path, "role-debrief-1")
        report, cons, trace = role_debrief(conn, "role-debrief-1", use_llm=False)
        assert report.used_llm is False
        assert report.text and report.text != "No verified findings for this match."
        # Every verified conclusion's rule id shows up in the template body.
        for c in verified_only(cons):
            assert c.rule_id in report.text
        assert trace["summary"]["verified"] == len(verified_only(cons))
