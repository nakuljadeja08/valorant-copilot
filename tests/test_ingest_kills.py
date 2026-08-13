"""R2a-1: the kill timeline and utility casts survive ingest intact.

The role features are only as trustworthy as the events they cite, so ingest of
the val-match-v1 kills[] timeline gets its own round-trip tests: ordering,
counts, assists, and the ability-cast columns.
"""

from src.features.queries import kills_by_round
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db


def _seed(tmp_path, match_id="kills-1"):
    conn = init_db(str(tmp_path / "k.db"))
    normalize(conn, get_source("sim").match(match_id), "sim")
    return conn, match_id


def test_kill_count_matches_the_per_round_aggregate(tmp_path):
    conn, mid = _seed(tmp_path)
    for r in conn.execute("SELECT DISTINCT round_num FROM rounds WHERE match_id=?", (mid,)):
        rn = r["round_num"]
        events = conn.execute(
            "SELECT COUNT(*) c FROM round_kills WHERE match_id=? AND round_num=?", (mid, rn)
        ).fetchone()["c"]
        agg = conn.execute(
            "SELECT COALESCE(SUM(kills),0) s FROM round_player_stats WHERE match_id=? AND round_num=?",
            (mid, rn),
        ).fetchone()["s"]
        assert events == agg, f"round {rn}: {events} timeline events != {agg} kill count"


def test_ordinals_are_dense_and_time_ordered(tmp_path):
    conn, mid = _seed(tmp_path)
    for rn, events in kills_by_round(conn, mid).items():
        ordinals = [e.kill_ordinal for e in events]
        assert ordinals == list(range(len(events))), f"round {rn} ordinals not dense: {ordinals}"
        times = [e.round_time_ms for e in events]
        assert times == sorted(times), f"round {rn} not time-ordered"


def test_assists_reference_real_kill_events(tmp_path):
    conn, mid = _seed(tmp_path)
    orphans = conn.execute(
        """SELECT COUNT(*) c FROM round_kill_assists a
           LEFT JOIN round_kills k
             ON k.match_id=a.match_id AND k.round_num=a.round_num
            AND k.kill_ordinal=a.kill_ordinal
           WHERE a.match_id=? AND k.match_id IS NULL""",
        (mid,),
    ).fetchone()["c"]
    assert orphans == 0
    # And there is at least some assist data to reason about.
    total = conn.execute(
        "SELECT COUNT(*) c FROM round_kill_assists WHERE match_id=?", (mid,)
    ).fetchone()["c"]
    assert total > 0


def test_ability_casts_are_persisted(tmp_path):
    conn, mid = _seed(tmp_path)
    total = conn.execute(
        """SELECT COALESCE(SUM(grenade_casts+ability1_casts+ability2_casts),0) s
           FROM round_player_stats WHERE match_id=?""",
        (mid,),
    ).fetchone()["s"]
    assert total > 0, "no utility casts persisted"
