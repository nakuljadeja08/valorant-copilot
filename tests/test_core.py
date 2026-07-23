"""Tests for the rate limiter and the simulator's causal guarantees."""

import time

from src.riot.client import SlidingWindowLimiter
from src.sim.generator import MatchGenerator


class TestLimiter:
    def test_burst_bucket_blocks(self):
        lim = SlidingWindowLimiter([(5, 0.5)])
        t0 = time.monotonic()
        for _ in range(6):
            lim.acquire()
        assert time.monotonic() - t0 >= 0.45  # 6th call had to wait for the window

    def test_under_limit_is_instant(self):
        lim = SlidingWindowLimiter([(100, 1.0)])
        t0 = time.monotonic()
        for _ in range(50):
            lim.acquire()
        assert time.monotonic() - t0 < 0.2

    def test_tightest_bucket_governs(self):
        lim = SlidingWindowLimiter([(1000, 1.0), (3, 0.4)])
        t0 = time.monotonic()
        for _ in range(4):
            lim.acquire()
        assert time.monotonic() - t0 >= 0.35


class TestSimulator:
    def test_schema_shape(self):
        g = MatchGenerator(seed=42)
        m = g.build_match("test-match-1")
        assert set(m) == {"matchInfo", "players", "teams", "roundResults"}
        assert len(m["players"]) == 10
        assert {t["teamId"] for t in m["teams"]} == {"Red", "Blue"}
        for r in m["roundResults"]:
            assert len(r["playerStats"]) == 10
            for ps in r["playerStats"]:
                assert {"loadoutValue", "spent", "remaining"} <= set(ps["economy"])

    def test_deterministic_by_match_id(self):
        g = MatchGenerator(seed=42)
        a, b = g.build_match("same-id"), g.build_match("same-id")
        assert a == b

    def test_valid_score(self):
        g = MatchGenerator(seed=7)
        m = g.build_match("score-check")
        won = [t for t in m["teams"] if t["won"]]
        rounds_won = {t["teamId"]: t["roundsWon"] for t in m["teams"]}
        # Either someone reached 13, or the cap ended it
        assert max(rounds_won.values()) == 13 or len(m["roundResults"]) == 24
        assert len(won) <= 1

    def test_economy_effect_recoverable(self):
        """The injected eco→win relationship must be statistically visible.

        This is the property that makes synthetic data defensible: downstream
        agents' claims can be validated against known ground truth.
        """
        g = MatchGenerator(seed=99)
        higher_spend_wins = total = 0
        for i in range(120):
            m = g.build_match(f"eco-{i}")
            for r in m["roundResults"]:
                spend = {"Red": 0, "Blue": 0}
                team_of = {p["puuid"]: p["teamId"] for p in m["players"]}
                for ps in r["playerStats"]:
                    spend[team_of[ps["puuid"]]] += ps["economy"]["spent"]
                if spend["Red"] == spend["Blue"]:
                    continue
                richer = "Red" if spend["Red"] > spend["Blue"] else "Blue"
                total += 1
                if r["winningTeam"] == richer:
                    higher_spend_wins += 1
        assert total > 500
        assert higher_spend_wins / total > 0.52  # edge exists, but isn't deterministic
