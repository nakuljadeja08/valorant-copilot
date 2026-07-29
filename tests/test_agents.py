"""3c: the tests that make the decision trace trustworthy.

Three properties are load-bearing and each gets a test:
  - a fixed match produces byte-identical trace JSON on every run (golden file)
  - the Watchdog catches a claim whose cited value no longer matches the store
  - the numeral post-check rejects LLM prose containing an invented statistic
"""

import json
from pathlib import Path

import pytest

from src.agents.base import Conclusion
from src.agents.rules import REGISTRY, analyze
from src.agents.trace import build_trace, dumps
from src.agents.view import FeatureRef, FeatureView
from src.agents.watchdog import verified_only, verify
from src.agents.writer import check_numerals, template_report, write_report
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

GOLDEN = Path(__file__).with_name("golden") / "trace_agent-golden-1.json"
GOLDEN_MATCH = "agent-golden-1"


def _store(tmp_path, match_id=GOLDEN_MATCH, n=1):
    """A store seeded with deterministic sim matches, features computed."""
    conn = init_db(str(tmp_path / "agents.db"))
    src = get_source("sim")
    ids = [match_id] if n == 1 else [f"{match_id}-{i}" for i in range(n)]
    for mid in ids:
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    return conn, ids


class TestGoldenTrace:
    def test_trace_is_byte_identical_across_runs(self, tmp_path):
        """Same match, two independent passes, same JSON. No timestamps, no set order."""
        conn, _ = _store(tmp_path)
        first = dumps(build_trace(GOLDEN_MATCH, verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH))))
        second = dumps(build_trace(GOLDEN_MATCH, verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH))))
        assert first == second

    def test_trace_matches_committed_golden_file(self, tmp_path):
        """Rules changed? This test is supposed to fail -- review the diff, then
        regenerate with `python -m tests.regen_golden`."""
        conn, _ = _store(tmp_path)
        actual = build_trace(GOLDEN_MATCH, verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH)))
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert actual == expected

    def test_every_claim_traces_back_to_raw_rows(self, tmp_path):
        conn, _ = _store(tmp_path)
        trace = build_trace(GOLDEN_MATCH, verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH)))

        existing_rounds = {
            r["round_num"] for r in
            conn.execute("SELECT round_num FROM rounds WHERE match_id=?", (GOLDEN_MATCH,))
        }
        assert trace["conclusions"], "golden match produced no conclusions"
        for c in trace["conclusions"]:
            assert c["evidence"], f"{c['rule_id']} cites nothing"
            for e in c["evidence"]:
                assert e["source_rows"], f"{c['rule_id']} cites a feature with no lineage"
                for ref in e["source_rows"]:
                    assert ref["match_id"] == GOLDEN_MATCH
                    assert ref["round_num"] in existing_rounds


class TestRuleRegistry:
    def test_at_least_ten_rules_across_both_agents(self):
        agents = {r.agent for r in REGISTRY}
        assert len(REGISTRY) >= 10
        assert agents == {"Analyst", "Economist"}

    def test_rule_ids_are_unique(self):
        ids = [r.id for r in REGISTRY]
        assert len(ids) == len(set(ids))

    def test_every_rule_fires_somewhere_in_a_sample(self, tmp_path):
        """A rule that can never fire produces no trace output and is dead weight."""
        conn, ids = _store(tmp_path, match_id="agent-cover", n=40)
        fired = {c.rule_id for mid in ids for c in analyze(conn, mid)}
        never = sorted({r.id for r in REGISTRY} - fired)
        assert not never, f"rules that never fired across 40 matches: {never}"


class TestWatchdog:
    def test_clean_store_verifies_every_claim(self, tmp_path):
        conn, _ = _store(tmp_path)
        checked = verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH))
        assert checked
        assert all(c.verified for c in checked)
        assert verified_only(checked) == checked

    def test_catches_a_corrupted_feature_value(self, tmp_path):
        """Mutation test: move a cited value in the store, the claim must fall out
        of the report rather than being printed with a stale number."""
        conn, _ = _store(tmp_path)
        conclusions = analyze(conn, GOLDEN_MATCH)
        target = next(c for c in conclusions if c.citations)
        cited = target.citations[0]

        with conn:
            conn.execute(
                """UPDATE features SET value = value + 999
                   WHERE match_id=? AND name=? AND round_num=? AND scope=?""",
                (GOLDEN_MATCH, cited.name, cited.round_num, cited.scope),
            )

        checked = verify(conn, GOLDEN_MATCH, conclusions)
        assert target.verified is False
        assert cited.name in target.unverified_reason
        assert target not in verified_only(checked)

    def test_catches_a_deleted_feature_row(self, tmp_path):
        conn, _ = _store(tmp_path)
        conclusions = analyze(conn, GOLDEN_MATCH)
        target = next(c for c in conclusions if c.citations)
        cited = target.citations[0]

        with conn:
            conn.execute(
                """DELETE FROM features
                   WHERE match_id=? AND name=? AND round_num=? AND scope=?""",
                (GOLDEN_MATCH, cited.name, cited.round_num, cited.scope),
            )

        verify(conn, GOLDEN_MATCH, conclusions)
        assert target.verified is False
        assert "missing from store" in target.unverified_reason

    def test_a_claim_citing_nothing_is_never_verified(self, tmp_path):
        conn, _ = _store(tmp_path)
        bare = Conclusion(rule_id="test.bare", agent="Analyst", severity="info",
                          text="Blue lost 7 rounds.", citations=[])
        verify(conn, GOLDEN_MATCH, [bare])
        assert bare.verified is False
        assert verified_only([bare]) == []

    def test_unchecked_conclusions_are_excluded(self):
        """verified=None means the Watchdog never ran -- treat as failed, not passed."""
        unchecked = Conclusion(rule_id="test.unchecked", agent="Analyst",
                               severity="info", text="Blue won.", citations=[])
        assert unchecked.verified is None
        assert verified_only([unchecked]) == []


class TestNumeralPostCheck:
    def _conclusion(self):
        ref = FeatureRef(round_num=14, scope="match", name="pivotal_round",
                         value=14.0, inputs=[])
        return Conclusion(rule_id="test.rule", agent="Analyst", severity="info",
                          text="R14 was the pivotal round, a 0.31 swing.", citations=[ref])

    def test_accepts_a_faithful_rephrasing(self):
        c = [self._conclusion()]
        text = "The match turned on R14 -- a swing of 0.31 in the proxy."
        assert check_numerals(text, c) == []

    def test_rejects_an_invented_statistic(self):
        c = [self._conclusion()]
        text = "R14 was pivotal (0.31 swing), and Blue held a 73% win rate after it."
        assert check_numerals(text, c) == ["73"]

    def test_rejects_a_recomputed_figure(self):
        """Rounding 0.31 to 31% is still a number that isn't in the trace."""
        c = [self._conclusion()]
        assert "31" in check_numerals("R14 swung the proxy by 31 percent.", c)

    def test_prose_with_no_numbers_always_passes(self):
        assert check_numerals("The pivotal round decided the match.", [self._conclusion()]) == []


class TestNoLlmMode:
    def test_no_llm_produces_a_complete_debrief(self, tmp_path):
        conn, _ = _store(tmp_path)
        verified = verified_only(verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH)))
        report = write_report(verified, use_llm=False)

        assert report.used_llm is False
        assert report.error is None
        # Every verified claim's text survives into the dry report.
        for c in verified:
            assert c.text in report.text
        assert "Analyst" in report.text and "Economist" in report.text

    def test_no_llm_never_touches_the_network(self, tmp_path, monkeypatch):
        """--no-llm must run with no API key and no SDK import."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        conn, _ = _store(tmp_path)
        verified = verified_only(verify(conn, GOLDEN_MATCH, analyze(conn, GOLDEN_MATCH)))
        assert write_report(verified, use_llm=False).text

    def test_empty_findings_still_render(self):
        assert "No verified findings" in template_report([])


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


def _stub_anthropic(monkeypatch, response):
    """Drive the LLM path without credentials or a network call."""
    import anthropic

    class _Messages:
        def create(self, **kwargs):
            if isinstance(response, Exception):
                raise response
            _Messages.last_kwargs = kwargs
            return response

    class _Client:
        def __init__(self, *a, **kw):
            self.messages = _Messages()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    return _Messages


class TestLlmPath:
    """The LLM may rephrase; it may not add numbers. Enforced, not requested."""

    def _findings(self):
        ref = FeatureRef(round_num=5, scope="match", name="pivotal_round",
                         value=5.0, inputs=[])
        return [Conclusion(rule_id="test.rule", agent="Analyst", severity="info",
                           text="R5 was the pivotal round, a 0.12 swing.", citations=[ref])]

    def test_faithful_draft_is_used(self, monkeypatch):
        _stub_anthropic(monkeypatch, _Response("You lost the match at R5 -- a 0.12 swing."))
        report = write_report(self._findings(), use_llm=True)
        assert report.used_llm is True
        assert report.error is None
        assert "R5" in report.text

    def test_invented_stat_is_rejected_and_falls_back(self, monkeypatch):
        _stub_anthropic(
            monkeypatch,
            _Response("R5 swung 0.12, and your 64% post-plant rate sealed it."),
        )
        report = write_report(self._findings(), use_llm=True)
        assert report.used_llm is False
        assert report.rejected_numerals == ["64"]
        # The fallback still carries the real claim, unaltered.
        assert self._findings()[0].text in report.text

    def test_refusal_falls_back(self, monkeypatch):
        _stub_anthropic(monkeypatch, _Response("", stop_reason="refusal"))
        report = write_report(self._findings(), use_llm=True)
        assert report.used_llm is False
        assert "declined" in report.error

    def test_api_error_falls_back(self, monkeypatch):
        _stub_anthropic(monkeypatch, RuntimeError("connection reset"))
        report = write_report(self._findings(), use_llm=True)
        assert report.used_llm is False
        assert "connection reset" in report.error
        assert report.text

    def test_request_omits_parameters_opus_5_rejects(self, monkeypatch):
        """temperature/top_p and budget_tokens are 400s on claude-opus-5."""
        messages = _stub_anthropic(monkeypatch, _Response("R5 was pivotal, 0.12 swing."))
        write_report(self._findings(), use_llm=True)
        sent = messages.last_kwargs
        assert "temperature" not in sent and "top_p" not in sent
        assert sent["model"] == "claude-opus-5"
        assert sent["output_config"] == {"effort": "low"}
