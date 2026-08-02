"""Phase 4: the static bundles the dashboard is built from.

The frontend can only be as honest as its input, so the properties worth
pinning are: the bundle agrees with the store, the trace is passed through
rather than reshaped, and re-exporting an unchanged store changes nothing.
"""

import json

import pytest

from src.agents.rules import analyze
from src.agents.trace import build_trace
from src.agents.watchdog import verify
from src.export.bundle import build_index, build_match_bundle, dumps, export
from src.features.constants import BUY_NAMES
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

MATCH = "export-fixture-1"


@pytest.fixture
def store(tmp_path):
    conn = init_db(str(tmp_path / "export.db"))
    src = get_source("sim")
    ids = [f"{MATCH}-{i}" for i in range(3)]
    for mid in ids:
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    return conn, ids


class TestMatchBundle:
    def test_meta_and_score_match_the_rounds_table(self, store):
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])

        wins = dict(conn.execute(
            "SELECT winning_team, COUNT(*) FROM rounds WHERE match_id = ? GROUP BY winning_team",
            (ids[0],),
        ).fetchall())
        assert bundle["match"]["score"] == {"Blue": wins.get("Blue", 0), "Red": wins.get("Red", 0)}
        assert bundle["match"]["rounds"] == len(bundle["rounds"])
        assert bundle["match"]["source"] == "sim"

    def test_map_and_agents_resolve_to_real_content_names(self, store):
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])

        assert not bundle["match"]["map_name"].startswith("unknown-map:")
        assert bundle["players"], "no players exported"
        for p in bundle["players"]:
            assert not p["agent_name"].startswith("unknown-agent:")

    def test_round_economy_matches_the_feature_store(self, store):
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])

        features = {
            (r["name"], r["round_num"]): r["value"]
            for r in conn.execute(
                "SELECT name, round_num, value FROM features WHERE match_id = ?", (ids[0],)
            )
        }
        for rnd in bundle["rounds"]:
            n = rnd["round_num"]
            for team in ("Blue", "Red"):
                assert rnd["economy"][team]["spend"] == features[(f"spend:{team}", n)]
                assert rnd["economy"][team]["bank"] == features[(f"bank:{team}", n)]
                assert rnd["economy"][team]["buy_type"] == BUY_NAMES[features[(f"buy_type:{team}", n)]]

    def test_trace_is_passed_through_verbatim(self, store):
        """The UI expands claims straight out of the Phase 3 trace. If the export
        reshaped it, 'the page shows what the trace says' would stop being true."""
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])
        expected = build_trace(ids[0], verify(conn, ids[0], analyze(conn, ids[0])))
        assert bundle["trace"] == expected

    def test_only_verified_claims_carry_evidence_to_the_ui(self, store):
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])

        excluded_ids = {e["rule_id"] for e in bundle["excluded"]}
        for c in bundle["trace"]["conclusions"]:
            if c["verified"] is not True:
                assert c["rule_id"] in excluded_ids

    def test_no_llm_by_default_so_export_needs_no_api_key(self, store):
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])
        assert bundle["debrief"]["used_llm"] is False
        assert bundle["debrief"]["text"]

    def test_provenance_note_is_on_every_match_bundle(self, store):
        conn, ids = store
        for mid in ids:
            bundle = build_match_bundle(conn, mid)
            assert "production key" in bundle["provenance"]["note"]


class TestIndex:
    def test_index_counts_agree_with_the_per_match_bundles(self, store):
        conn, ids = store
        bundles = [build_match_bundle(conn, mid) for mid in ids]
        index = build_index(bundles)

        assert index["match_count"] == len(ids)
        by_id = {m["match_id"]: m for m in index["matches"]}
        for b in bundles:
            entry = by_id[b["match"]["match_id"]]
            assert entry["verified_claims"] == b["trace"]["summary"]["verified"]
            assert entry["source_rows_cited"] == b["trace"]["summary"]["source_rows_cited"]

    def test_matches_are_sorted_so_the_list_is_stable(self, store):
        conn, ids = store
        index = build_index([build_match_bundle(conn, mid) for mid in ids])
        listed = [m["match_id"] for m in index["matches"]]
        assert listed == sorted(listed)


class TestExport:
    def test_writes_an_index_and_one_file_per_match(self, store, tmp_path):
        conn, ids = store
        out = tmp_path / "bundles"
        result = export(conn, out)

        assert result["matches"] == len(ids)
        assert (out / "index.json").exists()
        for mid in ids:
            assert (out / "match" / f"{mid}.json").exists()

    def test_re_export_is_byte_identical(self, store, tmp_path):
        """Same store, same bytes -- so a diff in the committed bundles always
        means the data or the rules actually changed."""
        conn, _ = store
        out = tmp_path / "bundles"

        export(conn, out)
        first = {p.name: p.read_bytes() for p in sorted(out.rglob("*.json"))}
        export(conn, out)
        second = {p.name: p.read_bytes() for p in sorted(out.rglob("*.json"))}

        assert first == second

    def test_serialization_is_sorted_and_newline_terminated(self):
        text = dumps({"b": 1, "a": 2})
        assert text.endswith("\n")
        assert list(json.loads(text)) == ["a", "b"]
        assert text.index('"a"') < text.index('"b"')

    def test_empty_store_fails_loudly(self, tmp_path):
        conn = init_db(str(tmp_path / "empty.db"))
        with pytest.raises(SystemExit):
            export(conn, tmp_path / "bundles")
