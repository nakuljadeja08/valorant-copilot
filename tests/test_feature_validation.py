"""2c validation: the tests that make computed features (not just raw sim rows)
defensible as ground truth for later coaching claims.
"""

import json

from src.features.registry import REGISTRY
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

N_MATCHES = 150


def _build_store(tmp_path, n=N_MATCHES):
    conn = init_db(str(tmp_path / "validation.db"))
    src = get_source("sim")
    match_ids = [f"val-feat-{i}" for i in range(n)]
    for mid in match_ids:
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    return conn, match_ids


class TestEcoWinEdgeRecoverable:
    def test_richer_team_wins_more_via_feature_store(self, tmp_path):
        """The injected eco->win edge must survive the round trip through the
        `features` table, not just be visible in raw round_player_stats.
        """
        conn, _ = _build_store(tmp_path)

        rows = conn.execute(
            """SELECT f.match_id, f.round_num, f.value AS spend_diff, r.winning_team
               FROM features f
               JOIN rounds r ON r.match_id = f.match_id AND r.round_num = f.round_num
               WHERE f.name = 'spend_diff'"""
        ).fetchall()

        richer_wins = total = 0
        for row in rows:
            if row["spend_diff"] == 0:
                continue
            richer = "Blue" if row["spend_diff"] > 0 else "Red"  # spend_diff = Blue - Red
            total += 1
            if row["winning_team"] == richer:
                richer_wins += 1

        assert total > 500
        edge = richer_wins / total
        # Same tolerance band as the raw-row check in test_core.py: the edge
        # exists but the sim also mixes in a skill prior, so it isn't huge.
        assert 0.52 < edge < 0.75


class TestBuyClassifierBonusRounds:
    def test_eco_force_frequency_spikes_after_a_loss(self, tmp_path):
        """A team entering a round on a loss streak (playing bonus money) should
        show a materially higher eco/force rate than a team entering fresh off
        a win -- that's the mechanic the loss-bonus escalation is meant to show.
        """
        conn, _ = _build_store(tmp_path)

        rows = conn.execute(
            """SELECT bt.match_id, bt.round_num, bt.name, bt.value AS buy_code,
                      ls.value AS streak
               FROM features bt
               JOIN features ls
                 ON ls.match_id = bt.match_id AND ls.round_num = bt.round_num
                AND ls.name = 'loss_streak:' || substr(bt.name, length('buy_type:') + 1)
               WHERE bt.name LIKE 'buy_type:%'"""
        ).fetchall()

        assert rows, "join produced no rows -- buy_type/loss_streak naming drifted"

        def is_eco_force(code: float) -> bool:
            return code in (0.0, 1.0)  # eco, force

        off_win = [r for r in rows if r["streak"] == 0]
        off_loss = [r for r in rows if r["streak"] >= 1]
        assert len(off_win) > 200 and len(off_loss) > 200

        rate_off_win = sum(is_eco_force(r["buy_code"]) for r in off_win) / len(off_win)
        rate_off_loss = sum(is_eco_force(r["buy_code"]) for r in off_loss) / len(off_loss)

        assert rate_off_loss > rate_off_win


class TestLineageIntegrity:
    def test_every_reference_points_at_an_existing_row(self, tmp_path):
        conn, match_ids = _build_store(tmp_path, n=25)

        existing_rounds = {
            (r["match_id"], r["round_num"])
            for r in conn.execute("SELECT match_id, round_num FROM rounds")
        }
        existing_rps = {
            (r["match_id"], r["round_num"], r["puuid"])
            for r in conn.execute("SELECT match_id, round_num, puuid FROM round_player_stats")
        }
        existing_kills = {
            (r["match_id"], r["round_num"], r["kill_ordinal"])
            for r in conn.execute("SELECT match_id, round_num, kill_ordinal FROM round_kills")
        }
        existing_assists = {
            (r["match_id"], r["round_num"], r["kill_ordinal"], r["assistant_puuid"])
            for r in conn.execute(
                "SELECT match_id, round_num, kill_ordinal, assistant_puuid FROM round_kill_assists")
        }

        checked = 0
        for row in conn.execute("SELECT match_id, inputs_json FROM features"):
            for ref in json.loads(row["inputs_json"]):
                assert ref["match_id"] == row["match_id"]
                if ref["table"] == "rounds":
                    assert (ref["match_id"], ref["round_num"]) in existing_rounds
                elif ref["table"] == "round_player_stats":
                    assert (ref["match_id"], ref["round_num"], ref["puuid"]) in existing_rps
                elif ref["table"] == "round_kills":
                    assert (ref["match_id"], ref["round_num"], ref["kill_ordinal"]) in existing_kills
                elif ref["table"] == "round_kill_assists":
                    assert (ref["match_id"], ref["round_num"], ref["kill_ordinal"],
                            ref["assistant_puuid"]) in existing_assists
                else:
                    raise AssertionError(f"unexpected lineage table: {ref['table']}")
                checked += 1

        assert checked > 1000

    def test_registry_features_are_idempotent_across_all_matches(self, tmp_path):
        conn, match_ids = _build_store(tmp_path, n=10)
        before = {
            (r["match_id"], r["round_num"], r["scope"], r["name"]): r["value"]
            for r in conn.execute("SELECT match_id, round_num, scope, name, value FROM features")
        }

        for mid in match_ids:
            compute_for_match(conn, mid, features=REGISTRY)

        after = {
            (r["match_id"], r["round_num"], r["scope"], r["name"]): r["value"]
            for r in conn.execute("SELECT match_id, round_num, scope, name, value FROM features")
        }
        assert before == after
