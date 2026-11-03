"""F2: fantasy points must be exact, traceable and verified.

Rules here are pinned locally, so tuning `rules_2027.json` can't make a hand calculation
drift. The season-level tests run the shipped rules.
"""

import copy
import json

import pytest

from src.fantasy.balance import _best_squad, _pool, summarize
from src.fantasy.prices import team_price_totals
from src.fantasy.scoring import (
    compute_event_rows, load_rules, role_bonuses, rules_version, score_season,
)
from src.fantasy.source import SimProSeasonSource
from src.fantasy.squads import Squad, score_week, validate_squad
from src.fantasy.stats import PlayerMapStats, find_clutch, map_stats
from src.fantasy.store import load_season, open_store
from src.fantasy.verify import verified_totals, verify_points
from src.features.queries import KillEvent
from src.riot.resolve import AGENT_ROLE

RULES = {
    "player": {
        "kill": 2, "assist": {"duelist": 1, "initiator": 1, "controller": 1, "sentinel": 1},
        "death": -1, "first_kill": 1, "first_death": -1,
        "multikill": {"3": 1, "4": 3, "5": 5}, "clutch": {"2": 1, "3": 2, "4": 3, "5": 5},
        "map_win": 2, "role_bonus": [3],
    },
    "coach": {"map_win": 3, "series_win": 5, "round_diff_divisor": 5, "upset": 3},
    "squad": {
        "budget": {"regional": 100, "international": 112}, "starters": 5, "subs": 2, "coaches": 2, "max_players_per_team": 2,
        "max_coaches_per_team": 1, "required_roles": ["duelist", "initiator", "controller", "sentinel"],
        "captain_multiplier": 2,
    },
    "prices": {"player_min": 8.0, "player_max": 16.0, "coach_min": 3.0, "coach_max": 9.0,
               "step_per_sd": 0.5, "max_move": 1.5},
}
MATCH = "vct27-hand-m1"


def _agent(role: str, skip: int = 0) -> str:
    return [a for a, r in AGENT_ROLE.items() if r == role][skip]


@pytest.fixture
def hand(tmp_path):
    """One hand-written map: Red wins 2 rounds to 1, with a 3K, a 4K and a 1v5 clutch."""
    conn = open_store(str(tmp_path / "hand.db"))
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO matches (match_id, map_id, source) VALUES (?, 'm', 'sim')", (MATCH,))
    roles = ["duelist", "initiator", "controller", "sentinel", "sentinel"]
    for side, prefix in (("Red", "R"), ("Blue", "B")):
        for i, role in enumerate(roles, start=1):
            conn.execute(
                "INSERT INTO match_players (match_id, puuid, team_id, character_id) VALUES (?,?,?,?)",
                (MATCH, f"{prefix}{i}", side, _agent(role, skip=i // 5)))

    timeline = {
        0: ("Red", [("R1", "B1", ["R2"]), ("R1", "B2", []), ("R1", "B3", []), ("B4", "R1", []),
                    ("R2", "B4", []), ("R3", "B5", [])]),
        1: ("Blue", [("B1", "R1", []), ("B1", "R2", []), ("B2", "R3", []), ("B2", "R4", []),
                     ("B3", "R5", [])]),
        2: ("Red", [("B1", "R2", []), ("B1", "R3", []), ("B1", "R4", []), ("B1", "R5", []),
                    ("R1", "B1", []), ("R1", "B2", [])]),
    }
    for round_num, (winner, kills) in timeline.items():
        conn.execute("INSERT INTO rounds (match_id, round_num, winning_team) VALUES (?,?,?)",
                     (MATCH, round_num, winner))
        for ordinal, (killer, victim, assists) in enumerate(kills):
            conn.execute(
                """INSERT INTO round_kills (match_id, round_num, kill_ordinal, killer_puuid,
                                            victim_puuid, round_time_ms) VALUES (?,?,?,?,?,?)""",
                (MATCH, round_num, ordinal, killer, victim, ordinal * 1000))
            for a in assists:
                conn.execute(
                    "INSERT INTO round_kill_assists VALUES (?,?,?,?)", (MATCH, round_num, ordinal, a))

    conn.execute("INSERT INTO events VALUES ('e', 1, 'E', 'regional', '2027-01-01', '2027-01-02', '{}', '{}', '{}')")
    for team, tier, coach in (("A", "partner", "coach-a"), ("B", "open", "coach-b")):
        conn.execute("INSERT INTO pro_teams VALUES (?, ?, 'americas', ?, 0.0)", (team, f"Team {team}", tier))
        conn.execute("INSERT INTO pro_coaches VALUES (?, ?, ?)", (coach, coach, team))
    conn.execute(
        """INSERT INTO series VALUES ('s', 'e', 'americas', 'upper', 0, 1, 0, 1, 'A', 'B', 1, 0, 'A')""")
    conn.execute("INSERT INTO series_maps VALUES ('s', 1, ?, 'A', 'B', 'A')", (MATCH,))
    # A is cheaper than B, so A's win is an upset.
    conn.execute("INSERT INTO event_prices VALUES ('e', 'R1', 'player', 'A', 8, 'duelist')")
    conn.execute("INSERT INTO event_prices VALUES ('e', 'B1', 'player', 'B', 16, 'duelist')")
    conn.commit()
    yield conn
    conn.close()


def _rows(conn, entity):
    return {r.name.partition(":")[0]: r for r in compute_event_rows(conn, "e", RULES)
            if r.name.partition(":")[2] == entity}


# --- Hand-checked scoring ------------------------------------------------------------

def test_stats_match_the_written_timeline(hand):
    stats = map_stats(hand, MATCH)
    r1 = stats["R1"]
    assert (len(r1.kills), len(r1.deaths), len(r1.first_kills), len(r1.first_deaths)) == (5, 2, 1, 1)
    assert len(r1.multikills[3]) == 3
    assert len(r1.clutches[5]) == 1
    assert r1.won and r1.role == "duelist"
    assert len(stats["R2"].assists) == 1
    assert len(stats["B1"].multikills[4]) == 4
    assert not stats["B1"].won


def test_points_match_a_hand_calculation(hand):
    rows = _rows(hand, "R1")
    values = {k: v.value for k, v in rows.items()}
    assert values == {
        "fp_kill": 10, "fp_death": -2, "fp_first_kill": 1, "fp_first_death": -1,
        "fp_multikill_3": 1, "fp_clutch_1v5": 5, "fp_map_win": 2,
        "fp_role_bonus": 3,  # beats B1 (base 14) with base 16
        "fp_total": 19,
    }
    b1 = {k: v.value for k, v in _rows(hand, "B1").items()}
    assert b1 == {"fp_kill": 12, "fp_death": -2, "fp_first_kill": 2, "fp_first_death": -1,
                  "fp_multikill_4": 3, "fp_total": 14}


def test_coach_points_match_a_hand_calculation(hand):
    winner = {k: v.value for k, v in _rows(hand, "coach-a").items()}
    assert winner == {"fp_coach_map_win": 3, "fp_coach_series_win": 5, "fp_coach_upset": 3,
                      "fp_coach_total": 11}
    loser = {k: v.value for k, v in _rows(hand, "coach-b").items()}
    assert loser == {"fp_coach_total": 0}


def test_no_upset_when_the_dearer_team_wins(hand):
    hand.execute("UPDATE event_prices SET price = 20 WHERE entity_id = 'R1'")
    assert "fp_coach_upset" not in _rows(hand, "coach-a")
    assert team_price_totals(hand, "e") == {"A": 20, "B": 16}


def test_each_point_points_at_its_raw_rows(hand):
    kill = _rows(hand, "R1")["fp_kill"]
    head, *refs = kill.inputs
    assert head == {"table": "fantasy_rules", "version": rules_version(RULES), "rule": "kill",
                    "points_each": 2, "count": 5}
    assert len(refs) == 5
    for ref in refs:
        row = hand.execute(
            "SELECT killer_puuid FROM round_kills WHERE match_id=? AND round_num=? AND kill_ordinal=?",
            (ref["match_id"], ref["round_num"], ref["kill_ordinal"])).fetchone()
        assert row["killer_puuid"] == "R1"


# --- Clutches and the role bonus -------------------------------------------------------

def _event(killer, victim):
    return KillEvent(0, 0, killer, victim, 0, False)


TEAMS = {"Red": ["r1", "r2", "r3"], "Blue": ["b1", "b2", "b3"]}


def test_clutch_counts_opponents_when_the_player_became_last_alive():
    events = [_event("b1", "r2"), _event("b1", "r3"), _event("r1", "b1"), _event("r1", "b2")]
    assert find_clutch(events, TEAMS, "Red") == ("r1", 3)


def test_clutch_needs_at_least_two_opponents():
    events = [_event("r1", "b1"), _event("r1", "b2"), _event("b3", "r2"), _event("b3", "r3")]
    assert find_clutch(events, TEAMS, "Red") is None


def test_clutch_fails_if_the_last_player_dies():
    events = [_event("b1", "r2"), _event("b1", "r3"), _event("b1", "r1")]
    assert find_clutch(events, TEAMS, "Red") is None


def test_clutch_only_goes_to_the_winning_side():
    events = [_event("b1", "r2"), _event("b1", "r3")]
    assert find_clutch(events, TEAMS, "Blue") is None


def test_role_alone_on_a_map_earns_no_bonus():
    stats = {
        "a": PlayerMapStats("a", "Red", "duelist", kills=[{}] * 9),
        "b": PlayerMapStats("b", "Blue", "duelist", kills=[{}] * 3),
        "c": PlayerMapStats("c", "Red", "controller", kills=[{}] * 30),
    }
    assert role_bonuses(stats, RULES) == {"a": 3}


# --- Squads ---------------------------------------------------------------------------

def _price_table():
    table = {}
    for i, role in enumerate(["duelist", "initiator", "controller", "sentinel", "duelist", "initiator", "sentinel"]):
        table[f"p{i}"] = {"kind": "player", "team_id": f"t{i // 2}", "price": 10.0, "listed_role": role}
    table["c0"] = {"kind": "coach", "team_id": "t0", "price": 5.0, "listed_role": None}
    table["c1"] = {"kind": "coach", "team_id": "t1", "price": 5.0, "listed_role": None}
    return table


GOOD = Squad(("p0", "p1", "p2", "p3", "p4"), ("p5", "p6"), ("c0", "c1"), "p0", "p1")


def test_a_legal_squad_passes():
    assert validate_squad(GOOD, _price_table(), RULES) == []


@pytest.mark.parametrize("change,message", [
    ({"starters": ("p0", "p1", "p2", "p3")}, "5 starters"),
    ({"subs": ("p5",)}, "2 subs"),
    ({"coaches": ("c0",)}, "2 coaches"),
    ({"subs": ("p4", "p6")}, "picked twice"),
    ({"coaches": ("c0", "nobody")}, "not available"),
    ({"coaches": ("c0", "p6")}, "player is in a coach slot"),
    ({"captain": "p6"}, "must be starters"),
    ({"vice": "p0"}, "different players"),
])
def test_illegal_squads_are_rejected(change, message):
    fields = dict(starters=GOOD.starters, subs=GOOD.subs, coaches=GOOD.coaches,
                  captain=GOOD.captain, vice=GOOD.vice) | change
    errors = validate_squad(Squad(**fields), _price_table(), RULES)
    assert any(message in e for e in errors), errors


def test_budget_role_and_team_limits_are_enforced():
    table = _price_table()
    table["p0"]["price"] = 40.0  # 110 in total
    assert any("budget" in e for e in validate_squad(GOOD, table, RULES))
    assert validate_squad(GOOD, table, RULES, "international") == []

    table = _price_table()
    table["p3"]["listed_role"] = "duelist"
    assert any("sentinel" in e for e in validate_squad(GOOD, table, RULES))

    table = _price_table()
    table["p2"]["team_id"] = "t0"
    assert any("players from one team" in e for e in validate_squad(GOOD, table, RULES))

    table = _price_table()
    table["c1"]["team_id"] = "t0"
    assert any("coach from one team" in e for e in validate_squad(GOOD, table, RULES))


def test_week_scoring_doubles_the_captain_and_adds_coaches():
    points = {"p0": 10, "p1": 5, "p2": 5, "p3": 5, "p4": 5, "p5": 99, "c0": 4}
    assert score_week(GOOD, points, RULES) == {
        "players": 30, "captain_bonus": 10, "coaches": 4, "total": 44}


def test_absent_starter_is_replaced_by_the_first_available_sub():
    points = {"p0": 10, "p1": 5, "p2": 5, "p3": 5, "p6": 7}  # p4 and p5 played nothing
    assert score_week(GOOD, points, RULES)["players"] == 32


def test_vice_captain_takes_over_when_the_captain_does_not_play():
    points = {"p1": 5, "p2": 5, "p3": 5, "p4": 5, "p5": 1}
    scored = score_week(GOOD, points, RULES)
    assert scored["captain_bonus"] == 5
    assert scored["players"] == 21


def test_no_armband_bonus_when_neither_captain_plays():
    assert score_week(GOOD, {"p2": 5}, RULES)["captain_bonus"] == 0


# --- A full season ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def season(tmp_path_factory):
    conn = open_store(str(tmp_path_factory.mktemp("scored") / "season.db"))
    conn.execute("PRAGMA synchronous=OFF")
    load_season(conn, SimProSeasonSource(1337))
    score_season(conn)
    yield conn
    conn.close()


def test_season_verifies_clean(season):
    assert verify_points(season) == []


def test_totals_are_the_sum_of_their_parts(season):
    parts: dict = {}
    totals: dict = {}
    for r in season.execute("SELECT match_id, name, value FROM features WHERE scope = 'fantasy'"):
        rule, _, entity = r["name"].partition(":")
        key = (r["match_id"], entity)
        if rule in ("fp_total", "fp_coach_total"):
            totals[key] = r["value"]
        else:
            parts[key] = parts.get(key, 0) + r["value"]
    assert totals
    for key, total in totals.items():
        assert total == pytest.approx(parts.get(key, 0)), key


def test_every_player_on_every_map_has_a_total(season):
    missing = season.execute(
        """SELECT mp.match_id, mp.puuid FROM match_players mp
           LEFT JOIN features f ON f.match_id = mp.match_id AND f.scope = 'fantasy'
            AND f.name = 'fp_total:' || mp.puuid
           WHERE f.name IS NULL""").fetchall()
    assert not missing


def test_kill_lineage_matches_the_stored_count(season):
    rows = season.execute(
        "SELECT match_id, name, inputs_json FROM features WHERE scope='fantasy' AND name LIKE 'fp_kill:%' LIMIT 200"
    ).fetchall()
    for r in rows:
        puuid = r["name"].partition(":")[2]
        head, *refs = json.loads(r["inputs_json"])
        kills = season.execute("SELECT kills FROM match_players WHERE match_id=? AND puuid=?",
                               (r["match_id"], puuid)).fetchone()["kills"]
        assert head["count"] == len(refs) == kills


def test_watchdog_catches_an_edited_point(season):
    row = season.execute(
        "SELECT match_id, name FROM features WHERE scope='fantasy' AND name LIKE 'fp_total:%' LIMIT 1").fetchone()
    entity = row["name"].partition(":")[2]
    try:
        season.execute("UPDATE features SET value = value + 1 WHERE match_id=? AND name=?",
                       (row["match_id"], row["name"]))
        problems = verify_points(season)
        assert [(p.match_id, p.name) for p in problems] == [(row["match_id"], row["name"])]
        assert (row["match_id"], entity) not in verified_totals(season)
    finally:
        season.rollback()


def test_watchdog_catches_an_edited_raw_row(season):
    row = season.execute(
        """SELECT rk.match_id, rk.round_num, rk.kill_ordinal, rk.killer_puuid, rk.victim_puuid
           FROM round_kills rk JOIN series_maps USING (match_id) LIMIT 1""").fetchone()
    try:
        season.execute(
            "DELETE FROM round_kills WHERE match_id=? AND round_num=? AND kill_ordinal=?",
            (row["match_id"], row["round_num"], row["kill_ordinal"]))
        names = {p.name for p in verify_points(season)}
        assert f"fp_kill:{row['killer_puuid']}" in names
        assert f"fp_death:{row['victim_puuid']}" in names
    finally:
        season.rollback()


def test_watchdog_catches_a_rules_change(season):
    changed = copy.deepcopy(load_rules())
    changed["player"]["kill"] += 1
    assert any("store has" in p.reason for p in verify_points(season, changed))

    # Same points, different version: only the rule set changed, so name the version.
    renamed = copy.deepcopy(load_rules())
    renamed["prices"]["max_move"] += 1
    assert any("scored under rules" in p.reason for p in verify_points(season, renamed))


def test_rescoring_is_identical(season):
    def snapshot():
        return (season.execute("SELECT match_id, name, value, inputs_json FROM features "
                               "WHERE scope='fantasy' ORDER BY 1, 2").fetchall(),
                season.execute("SELECT * FROM event_prices ORDER BY 1, 2").fetchall())
    before = [[tuple(r) for r in rows] for rows in snapshot()]
    score_season(season)
    assert [[tuple(r) for r in rows] for rows in snapshot()] == before


# --- Prices --------------------------------------------------------------------------

def test_prices_stay_in_range_on_half_steps(season):
    p = load_rules()["prices"]
    for r in season.execute("SELECT kind, price FROM event_prices"):
        low, high = (p["player_min"], p["player_max"]) if r["kind"] == "player" else (p["coach_min"], p["coach_max"])
        assert low <= r["price"] <= high
        assert (r["price"] * 2) % 1 == 0


def test_everyone_at_an_event_is_priced(season):
    for e in season.execute("SELECT event_id FROM events").fetchall():
        rostered = {r["puuid"] for r in season.execute(
            "SELECT puuid FROM event_rosters WHERE event_id=?", (e["event_id"],))}
        priced = {r["entity_id"] for r in season.execute(
            "SELECT entity_id FROM event_prices WHERE event_id=? AND kind='player'", (e["event_id"],))}
        assert rostered == priced
        teams = season.execute("SELECT COUNT(*) FROM event_teams WHERE event_id=?", (e["event_id"],)).fetchone()[0]
        coaches = season.execute("SELECT COUNT(*) FROM event_prices WHERE event_id=? AND kind='coach'",
                                 (e["event_id"],)).fetchone()[0]
        assert teams == coaches


def test_prices_move_between_events_within_the_limit(season):
    limit = load_rules()["prices"]["max_move"]
    order = [r["event_id"] for r in season.execute("SELECT event_id FROM events ORDER BY ordinal")]
    moved = 0
    for earlier, later in zip(order, order[1:]):
        rows = season.execute(
            """SELECT a.price AS before, b.price AS after FROM event_prices a
               JOIN event_prices b ON a.entity_id = b.entity_id
               WHERE a.event_id = ? AND b.event_id = ?""", (earlier, later)).fetchall()
        for r in rows:
            assert abs(r["after"] - r["before"]) <= limit + 0.5  # half-step rounding
            moved += r["after"] != r["before"]
    assert moved


def test_higher_priced_players_score_more_on_average(season):
    rows = season.execute(
        """SELECT ep.price, AVG(f.value) AS points FROM event_prices ep
           JOIN series s ON s.event_id = ep.event_id
           JOIN series_maps sm ON sm.series_id = s.series_id
           JOIN features f ON f.match_id = sm.match_id AND f.scope='fantasy'
            AND f.name = 'fp_total:' || ep.entity_id
           WHERE ep.kind = 'player' GROUP BY ep.event_id, ep.entity_id""").fetchall()
    rows = sorted(rows, key=lambda r: r["price"])
    half = len(rows) // 2
    mean = lambda xs: sum(x["points"] for x in xs) / len(xs)  # noqa: E731
    assert mean(rows[half:]) > mean(rows[:half])


def test_listed_roles_are_real_roles(season):
    roles = {r["listed_role"] for r in season.execute(
        "SELECT DISTINCT listed_role FROM event_prices WHERE kind='player'")}
    assert roles == {"duelist", "initiator", "controller", "sentinel"}


# --- Balance tooling -------------------------------------------------------------------

def test_best_squad_search_returns_a_legal_squad(season):
    import random
    rules = load_rules()
    pool = _pool(season, "kickoff", "americas")
    totals = {r["entity_id"]: float(i) for i, r in enumerate(
        season.execute("SELECT entity_id FROM event_prices WHERE event_id='kickoff' ORDER BY entity_id"))}
    best = _best_squad(pool, totals, rules, random.Random(1))
    assert best is not None
    assert validate_squad(best, pool, rules) == []


def test_summary_reports_each_target():
    bracket = {"event_id": "e", "bracket": "b", "budget": 100, "legal_rate": 0.5, "typical_total": 500.0,
               "coach_share": 0.15, "captain_share": 0.2, "cheapest_core": 80.0, "dearest_core": 120.0,
               "best_squad": ["x", "y"], "best_total": 900.0, "best_cost": 99.0}
    result = {"league": 1, "seed": 1, "top_kills": 30, "brackets": [bracket],
              "by_role": {"duelist": [100.0, 5], "sentinel": [95.0, 5]},
              "by_region": {"americas": [195.0, 10]}}
    other = {**result, "seed": 2, "brackets": [{**bracket, "best_squad": ["y", "z"]}]}
    summary = summarize([result, other], {"squad": {"budget": 100}})
    assert summary["role_spread"] == pytest.approx(0.053, abs=0.001)
    assert summary["optimal_share_max"] == 1.0  # y is in both
    assert summary["targets_met"] == {"role_spread": True, "optimal_share": False,
                                      "coach_share": True, "affordable": True}
