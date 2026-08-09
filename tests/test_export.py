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
        normalize(conn, src.match(mid), "sim", hero_puuid="hero")
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
                assert (rnd["economy"][team]["kill_share_sim_approx"]
                        == features.get((f"trade_efficiency_sim_approx:{team}", n)))
                assert (rnd["economy"][team]["win_prob_proxy"]
                        == features.get((f"win_prob_proxy:{team}", n)))

    def test_the_momentum_proxy_is_a_two_sided_series(self, store):
        """Both sides are exported so no consumer has to know that the feature's
        reference team is `sorted(teams)[0]`."""
        conn, ids = store
        bundle = build_match_bundle(conn, ids[1])  # ids[0] is a shutout; see below
        assert bundle["match_features"].get("pivotal_round") is not None

        for rnd in bundle["rounds"]:
            blue = rnd["economy"]["Blue"]["win_prob_proxy"]
            red = rnd["economy"]["Red"]["win_prob_proxy"]
            assert 0.0 < blue < 1.0
            assert blue + red == pytest.approx(1.0)

    def test_a_shutout_has_no_proxy_series_on_either_side(self, store):
        """`PivotalRoundFeature` declines to rank rounds when only one team ever
        won one -- there is no swing to find. The export must carry that absence
        symmetrically rather than emit a half-populated series."""
        conn, ids = store
        bundle = build_match_bundle(conn, ids[0])
        winners = {r["winning_team"] for r in bundle["rounds"] if r["winning_team"]}
        assert len(winners) == 1, "fixture 0 is expected to be a shutout"

        assert "pivotal_round" not in bundle["match_features"]
        for rnd in bundle["rounds"]:
            assert rnd["economy"]["Blue"]["win_prob_proxy"] is None
            assert rnd["economy"]["Red"]["win_prob_proxy"] is None

    def test_the_proxy_ships_with_its_own_disclaimer(self, store):
        """The feature is explicit that it is not a calibrated probability. That
        caveat travels in the bundle so frontend copy cannot drift from it."""
        conn, ids = store
        provenance = build_match_bundle(conn, ids[0])["provenance"]
        assert "not a calibrated win probability" in provenance["proxy_note"]
        assert "sim" in provenance["sim_approx_note"].lower()

    def test_hero_puuid_round_trips_to_a_team(self, store):
        conn, ids = store
        meta = build_match_bundle(conn, ids[0])["match"]
        assert meta["hero_puuid"] == "hero"
        assert meta["hero_team"] in ("Blue", "Red")

    def test_a_puuid_outside_the_roster_is_not_recorded(self, tmp_path):
        """Storing a focal player who never played would let the UI attribute a
        record to a side at random."""
        conn = init_db(str(tmp_path / "stranger.db"))
        normalize(conn, get_source("sim").match("stranger-1"), "sim", hero_puuid="not-in-match")
        compute_for_match(conn, "stranger-1")

        meta = build_match_bundle(conn, "stranger-1")["match"]
        assert meta["hero_puuid"] is None
        assert meta["hero_team"] is None

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

    def test_season_aggregates_agree_with_the_bundles(self, store):
        """Recomputed independently here. The overview and the match view read
        the same numbers, so a drift between them is a real bug."""
        conn, ids = store
        bundles = [build_match_bundle(conn, mid) for mid in ids]
        season = build_index(bundles)["season"]

        wins = forced = rounds = broken = 0
        for b in bundles:
            team = b["match"]["hero_team"]
            if b["match"]["winner"] == team:
                wins += 1
            for r in b["rounds"]:
                econ = r["economy"][team]
                if econ["buy_type"] is not None:
                    rounds += 1
                    forced += econ["buy_type"] == "force"
                broken += econ["broken_buy"] == 1.0

        assert season["record"]["wins"] == wins
        assert season["rounds"] == rounds
        assert season["broken_buys"] == broken
        assert season["force_rate"] == pytest.approx(forced / rounds, abs=1e-4)
        assert season["perspective"] == "hero"

        total = sum(v["rounds"] for v in season["buy_type_win_rate"].values())
        assert total == rounds

    def test_season_record_covers_every_match(self, store):
        conn, ids = store
        season = build_index([build_match_bundle(conn, m) for m in ids])["season"]
        record = season["record"]
        assert record["wins"] + record["losses"] + record["draws"] == len(ids)

    def test_every_match_has_a_verdict_stating_its_own_score(self, store):
        conn, ids = store
        bundles = [build_match_bundle(conn, mid) for mid in ids]
        index = build_index(bundles)
        by_id = {b["match"]["match_id"]: b for b in bundles}

        for entry in index["matches"]:
            b = by_id[entry["match_id"]]
            team = b["match"]["hero_team"]
            other = "Blue" if team == "Red" else "Red"
            score = b["match"]["score"]
            assert entry["verdict"], "a match with no verdict renders as a blank card"
            assert f"{score[team]}–{score[other]}" in entry["verdict"]
            assert entry["verdict"].endswith(".")

    def test_verdicts_are_deterministic(self, store):
        """Templated, not phrased by the LLM -- export defaults to no-LLM and
        re-export has to stay byte-identical."""
        conn, ids = store
        first = build_index([build_match_bundle(conn, m) for m in ids])
        second = build_index([build_match_bundle(conn, m) for m in ids])
        assert [m["verdict"] for m in first["matches"]] == \
               [m["verdict"] for m in second["matches"]]

    def test_every_rule_has_a_verdict_template(self):
        """An uncovered rule falls back to a bare outcome, which reads in the UI
        like a missing explanation rather than a missing template."""
        from src.agents.analyst import RULES as ANALYST
        from src.agents.economist import RULES as ECONOMIST
        from src.export.bundle import _VERDICT_TEMPLATES

        missing = {r.id for r in (*ANALYST, *ECONOMIST)} - set(_VERDICT_TEMPLATES)
        assert not missing, f"rules with no verdict template: {sorted(missing)}"

    def test_force_rate_matches_the_round_list(self, store):
        conn, ids = store
        bundles = [build_match_bundle(conn, mid) for mid in ids]
        index = build_index(bundles)
        by_id = {b["match"]["match_id"]: b for b in bundles}

        for entry in index["matches"]:
            b = by_id[entry["match_id"]]
            buys = [r["economy"][b["match"]["hero_team"]]["buy_type"] for r in b["rounds"]]
            buys = [x for x in buys if x is not None]
            expected = sum(1 for x in buys if x == "force") / len(buys)
            assert entry["force_rate"] == pytest.approx(expected, abs=1e-4)

    def test_bundle_version_is_current(self):
        """Bumped whenever the shape the frontend reads changes."""
        from src.export.bundle import BUNDLE_VERSION
        assert BUNDLE_VERSION == 2


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
