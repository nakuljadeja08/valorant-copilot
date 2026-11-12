"""F1: the simulated season must be repeatable, plausible and walled off from coaching.

The first test matters most outside fantasy: `build_match` with no fixture has to stay
byte-identical, because the committed coaching bundles are built from it.
"""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

import pytest

from src.fantasy.league import apply_roster_moves, build_league
from src.fantasy.schedule import SeasonSimulator, load_config
from src.fantasy.source import SimProSeasonSource, get_pro_source
from src.fantasy.store import ForeignStoreError, load_season, open_store
from src.ingest.pipeline import normalize
from src.riot.resolve import role_of
from src.sim.generator import FixtureSide, MatchFixture, MatchGenerator, _map_over
from src.storage.init import init as init_db

SEED = 1337

# Recorded from the generator before fixtures were added.
GOLDEN_DEFAULT_MATCHES = {
    ("golden-a", "hero"): "07de24e59ea16528a250533c622b0c123d4e22e44f1350350976138636126d2d",
    ("golden-b", "p0"): "941ed385def22ed0ce93bde4b42d2eb8dac23b17dfce7224f17b23897d6d0d49",
}

# The real 2027-2028 partner teams. A simulated name must never match one.
REAL_TEAM_WORDS = {
    "loud", "heretics", "xi lai", "rrq", "g2", "bbl", "weibo", "full sense", "nrg", "fnatic",
    "edward", "t1", "sentinels", "vitality", "tyloo", "paper rex", "kru", "liquid",
    "all gamers", "crazy raccoon", "leviatan", "gentle mates", "trace", "zeta", "mibr",
    "karmine", "bilibili", "gen.g", "100 thieves", "fut", "jd gaming", "gam",
}


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    return str(tmp_path_factory.mktemp("fantasy") / "fantasy.db")


@pytest.fixture(scope="module")
def conn(db_path):
    c = open_store(db_path)
    load_season(c, SimProSeasonSource(SEED))
    yield c
    c.close()


def _digest(conn) -> str:
    h = hashlib.sha256()
    for query in (
        "SELECT * FROM pro_players ORDER BY puuid",
        "SELECT * FROM event_teams ORDER BY event_id, team_id",
        "SELECT * FROM series ORDER BY series_id",
        "SELECT * FROM series_maps ORDER BY series_id, map_num",
        "SELECT * FROM round_kills ORDER BY match_id, round_num, kill_ordinal",
    ):
        for row in conn.execute(query):
            h.update(repr(tuple(row)).encode())
    return h.hexdigest()


# --- The coaching product is untouched ---------------------------------------------

@pytest.mark.parametrize("key,expected", GOLDEN_DEFAULT_MATCHES.items())
def test_default_build_match_is_byte_identical(key, expected):
    match_id, hero = key
    payload = MatchGenerator().build_match(match_id, hero_puuid=hero)
    assert hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() == expected


def test_refuses_to_write_into_the_coaching_store(tmp_path):
    path = str(tmp_path / "coaching.db")
    coaching = init_db(path)
    with coaching:
        normalize(coaching, MatchGenerator().build_match("ranked-1"), "sim")
    coaching.close()

    with pytest.raises(ForeignStoreError):
        open_store(path)

    check = init_db(path)
    tables = {r["name"] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "pro_teams" not in tables
    assert check.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1
    check.close()


# --- Repeatable --------------------------------------------------------------------

def test_same_seed_gives_identical_season_and_reload_replaces(conn):
    before = _digest(conn)
    load_season(conn, SimProSeasonSource(SEED))
    assert _digest(conn) == before


def test_different_seed_gives_different_season():
    config = load_config()
    a = next(SeasonSimulator(SEED, config).events())
    b = next(SeasonSimulator(SEED + 1, config).events())
    assert {e.team_id for e in a.entries} != {e.team_id for e in b.entries}


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError):
        get_pro_source(SEED, source="vlr")


# --- Maps always produce a winner ---------------------------------------------------

def test_map_over_rules():
    assert _map_over({"Red": 13, "Blue": 5}, 18, overtime=True)
    assert _map_over({"Red": 13, "Blue": 11}, 24, overtime=True)
    assert not _map_over({"Red": 12, "Blue": 12}, 24, overtime=True)
    assert not _map_over({"Red": 13, "Blue": 12}, 25, overtime=True)
    assert _map_over({"Red": 14, "Blue": 12}, 26, overtime=True)
    assert _map_over({"Red": 12, "Blue": 12}, 24, overtime=False)


def test_every_map_has_one_winner_with_a_legal_score(conn):
    rows = conn.execute(
        """SELECT sm.match_id, sm.winner, sm.red_team, sm.blue_team,
                  SUM(r.winning_team = 'Red') AS red, SUM(r.winning_team = 'Blue') AS blue
           FROM series_maps sm JOIN rounds r ON r.match_id = sm.match_id
           GROUP BY sm.match_id""").fetchall()
    assert rows
    overtime = 0
    for r in rows:
        high, low = max(r["red"], r["blue"]), min(r["red"], r["blue"])
        assert r["red"] != r["blue"], r["match_id"]
        assert r["winner"] == (r["red_team"] if r["red"] > r["blue"] else r["blue_team"])
        if high > 13:
            assert high - low == 2, r["match_id"]
            overtime += 1
        else:
            assert high == 13 and low <= 12, r["match_id"]
    assert overtime, "no map reached overtime, so the path is untested"


def test_payload_marks_exactly_one_winner_in_overtime():
    generator = MatchGenerator()
    agents = tuple(generator.agents[:5])
    side = lambda tag: FixtureSide(tuple(f"{tag}{i}" for i in range(5)), agents, 0.0, {})  # noqa: E731
    for i in range(60):
        payload = generator.build_match(
            f"ot-{i}", fixture=MatchFixture(generator.maps[0], side("r"), side("b"), 0))
        assert sum(t["won"] for t in payload["teams"]) == 1


# --- Rosters are stable inside an event ----------------------------------------------

def test_players_keep_their_team_across_an_event(conn):
    bad = conn.execute(
        """SELECT mp.match_id, mp.puuid FROM match_players mp
           JOIN series_maps sm ON sm.match_id = mp.match_id
           JOIN series s ON s.series_id = sm.series_id
           LEFT JOIN event_rosters er
             ON er.event_id = s.event_id AND er.puuid = mp.puuid
            AND er.team_id = CASE mp.team_id WHEN 'Red' THEN sm.red_team ELSE sm.blue_team END
           WHERE er.puuid IS NULL""").fetchall()
    assert not bad


def test_every_entered_team_has_five_players_and_a_coach(conn):
    sizes = conn.execute(
        """SELECT et.event_id, et.team_id, COUNT(er.puuid) AS n FROM event_teams et
           LEFT JOIN event_rosters er ON er.event_id = et.event_id AND er.team_id = et.team_id
           GROUP BY et.event_id, et.team_id""").fetchall()
    assert sizes and all(r["n"] == 5 for r in sizes)
    coaches = conn.execute(
        "SELECT COUNT(*) FROM pro_teams t LEFT JOIN pro_coaches c ON c.team_id = t.team_id "
        "WHERE c.coach_id IS NULL").fetchone()[0]
    assert coaches == 0


def test_each_break_moves_at_most_one_player_per_team():
    config = load_config()
    league = build_league(config, SEED)
    total = 0
    for event in config["events"]:
        moves = apply_roster_moves(league, SEED, event["id"])
        total += len(moves)
        assert max(Counter(team for team, _, _ in moves).values(), default=0) <= 1
        signed = [p.puuid for t in league.teams for p in t.roster]
        assert len(signed) == 5 * len(league.teams) == len(set(signed))
    assert total, "no roster ever changed, so per-event rosters are untested"


def test_stored_rosters_differ_between_events(conn):
    rosters = defaultdict(lambda: defaultdict(set))
    for r in conn.execute("SELECT event_id, team_id, puuid FROM event_rosters"):
        rosters[r["team_id"]][r["event_id"]].add(r["puuid"])
    assert any(len({frozenset(s) for s in by_event.values()}) > 1 for by_event in rosters.values())


def test_no_duplicate_agents_on_a_team(conn):
    bad = conn.execute(
        """SELECT match_id, team_id, character_id FROM match_players
           GROUP BY match_id, team_id, character_id HAVING COUNT(*) > 1""").fetchall()
    assert not bad


# --- Fields follow the published structure -------------------------------------------

def _field(conn, event_id, bracket=None):
    q = """SELECT et.*, t.tier, t.region FROM event_teams et JOIN pro_teams t USING (team_id)
           WHERE et.event_id = ?"""
    args = [event_id]
    if bracket:
        q += " AND et.bracket = ?"
        args.append(bracket)
    return conn.execute(q, args).fetchall()


@pytest.mark.parametrize("region", ["americas", "emea", "pacific"])
def test_kickoff_is_eight_partners_and_four_open(conn, region):
    tiers = Counter(r["tier"] for r in _field(conn, "kickoff", region))
    assert tiers == {"partner": 8, "open": 4}


def test_china_kickoff_is_eight_partners_two_visitors_two_open(conn):
    tiers = Counter(r["tier"] for r in _field(conn, "kickoff", "china"))
    assert tiers == {"partner": 8, "visitor": 2, "open": 2}


def test_masters_seoul_takes_the_top_three_from_each_kickoff(conn):
    kickoff_top = {r["team_id"] for r in _field(conn, "kickoff") if r["placement"] <= 3}
    assert {r["team_id"] for r in _field(conn, "masters_seoul")} == kickoff_top
    assert len(kickoff_top) == 12


def test_champions_field_is_sixteen_from_all_regions(conn):
    field = _field(conn, "champions")
    assert len(field) == 16
    assert Counter(r["region"] for r in field) == {
        "americas": 4, "emea": 4, "pacific": 4, "china": 4}


def test_cups_can_drop_partners_outside_china_but_not_inside(conn):
    for cup in ("cup_1", "cup_2"):
        china = Counter(r["tier"] for r in _field(conn, cup, "china"))
        assert china["partner"] == 8 and china["visitor"] == 2
        for region in ("americas", "emea", "pacific"):
            assert len(_field(conn, cup, region)) == 12
    missing = sum(
        8 - Counter(r["tier"] for r in _field(conn, cup, region))["partner"]
        for cup in ("cup_1", "cup_2") for region in ("americas", "emea", "pacific")
    )
    assert missing > 0, "partners are never at risk, which is the point of the 2027 format"


# --- Brackets ----------------------------------------------------------------------

def test_double_elimination_is_sound(conn):
    brackets = conn.execute("SELECT DISTINCT event_id, bracket FROM event_teams").fetchall()
    assert len(brackets) == 15  # 3 regional events x 4 regions + 3 international
    for b in brackets:
        event_id, bracket = b["event_id"], b["bracket"]
        field = _field(conn, event_id, bracket)
        placements = Counter(r["placement"] for r in field)
        assert placements[1] == 1 and placements[2] == 1 and placements[3] == 1

        losses = Counter()
        finals = conn.execute(
            "SELECT * FROM series WHERE event_id = ? AND bracket = ?", (event_id, bracket)).fetchall()
        for s in finals:
            losses[s["team_a"] if s["winner"] == s["team_b"] else s["team_b"]] += 1
        for r in field:
            if r["placement"] > 2:
                assert losses[r["team_id"]] == 2, (event_id, bracket, r["team_id"])
            else:
                assert losses[r["team_id"]] <= 2

        decider = [s for s in finals if s["stage"] == "final"]
        assert len(decider) == 1 and decider[0]["best_of"] == 5
        champion = next(r["team_id"] for r in field if r["placement"] == 1)
        assert decider[0]["winner"] == champion


def test_series_scores_match_their_maps(conn):
    for s in conn.execute("SELECT * FROM series").fetchall():
        maps = conn.execute(
            "SELECT winner FROM series_maps WHERE series_id = ?", (s["series_id"],)).fetchall()
        wins = Counter(m["winner"] for m in maps)
        assert wins[s["team_a"]] == s["maps_a"] and wins[s["team_b"]] == s["maps_b"]
        assert max(s["maps_a"], s["maps_b"]) == s["best_of"] // 2 + 1


# --- Calendar ----------------------------------------------------------------------

def test_series_fall_inside_their_event_and_after_the_week_deadline(conn):
    for e in conn.execute("SELECT * FROM events").fetchall():
        start, end = date.fromisoformat(e["starts_on"]), date.fromisoformat(e["ends_on"])
        deadlines = {r["week_num"]: r["deadline_ms"] for r in conn.execute(
            "SELECT week_num, deadline_ms FROM match_weeks WHERE event_id = ?", (e["event_id"],))}
        assert deadlines
        for s in conn.execute("SELECT * FROM series WHERE event_id = ?", (e["event_id"],)).fetchall():
            day = datetime.fromtimestamp(s["scheduled_ms"] / 1000, tz=timezone.utc).date()
            assert start <= day <= end
            assert s["scheduled_ms"] >= deadlines[s["week_num"]]


def test_calendar_matches_riots_announced_dates():
    events = {e["id"]: e for e in load_config()["events"]}
    assert (events["masters_seoul"]["start"], events["masters_seoul"]["end"]) == ("2027-02-20", "2027-03-03")
    assert (events["masters_valencia"]["start"], events["masters_valencia"]["end"]) == ("2027-06-05", "2027-06-20")
    assert (events["champions"]["start"], events["champions"]["end"]) == ("2027-09-16", "2027-10-10")
    # Unannounced details must stay flagged, so the UI can say so.
    assert all(e["format"]["assumed"] for e in events.values())
    assert events["champions"]["field"]["assumed"]


# --- Results are plausible -----------------------------------------------------------

def test_better_teams_win_more_often_without_winning_everything(conn):
    rows = conn.execute(
        """SELECT s.winner, a.team_id AS a_id, a.rating AS a_rating, b.rating AS b_rating
           FROM series s JOIN pro_teams a ON a.team_id = s.team_a
                         JOIN pro_teams b ON b.team_id = s.team_b""").fetchall()
    favourite_wins = sum(
        (r["winner"] == r["a_id"]) == (r["a_rating"] > r["b_rating"]) for r in rows)
    rate = favourite_wins / len(rows)
    assert 0.55 <= rate <= 0.85, rate


def test_more_skilled_players_get_more_kills_within_a_role(conn):
    rows = conn.execute(
        """SELECT p.base_role, p.skill, SUM(mp.kills) * 1.0 / COUNT(*) AS kills_per_map
           FROM match_players mp JOIN pro_players p USING (puuid)
           GROUP BY mp.puuid HAVING COUNT(*) >= 8""").fetchall()
    by_role = defaultdict(list)
    for r in rows:
        by_role[r["base_role"]].append(r)
    assert len(by_role) == 4
    for role, players in by_role.items():
        players.sort(key=lambda r: r["skill"])
        half = len(players) // 2
        mean = lambda xs: sum(x["kills_per_map"] for x in xs) / len(xs)  # noqa: E731
        assert mean(players[half:]) > mean(players[:half]), role


def test_roles_are_stable_but_players_sometimes_flex(conn):
    base = {r["puuid"]: r["base_role"] for r in conn.execute("SELECT puuid, base_role FROM pro_players")}
    played = conn.execute("SELECT puuid, character_id FROM match_players").fetchall()
    off_role = sum(role_of(r["character_id"]) != base[r["puuid"]] for r in played)
    assert 0 < off_role / len(played) < 0.15


# --- Fictional, always ---------------------------------------------------------------

def test_no_simulated_team_uses_a_real_name():
    league = build_league(load_config(), SEED)
    assert len({t.name for t in league.teams}) == len(league.teams)
    for team in league.teams:
        padded = f" {team.name.lower()} "
        for real in REAL_TEAM_WORDS:
            assert f" {real} " not in padded, (team.name, real)


def test_handles_are_unique_across_players_and_coaches():
    league = build_league(load_config(), SEED)
    handles = [p.handle for p in league.every_player] + [t.coach.handle for t in league.teams]
    assert len(set(handles)) == len(handles)


def test_stored_matches_are_labelled_simulated(conn):
    sources = {r["source"] for r in conn.execute("SELECT DISTINCT source FROM matches")}
    assert sources == {"sim"}
