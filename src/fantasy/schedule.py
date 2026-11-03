"""Play the simulated 2027 season: fields, brackets, series and maps.

The event order, dates and qualification come from `season_2027.json`. Riot has not
published match formats, so the bracket here is an assumption, marked as such in the
config: a double-elimination that takes any field size and has no bracket reset.

Determinism: every random draw comes from a `random.Random` seeded with a string naming
what it decides, so one change to a bracket doesn't shift the draws of another.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from src.fantasy.league import CORE_ROLES, League, Team, apply_roster_moves, build_league
from src.riot.resolve import role_of
from src.sim.generator import CONTENT_CACHE, FixtureSide, MatchFixture, MatchGenerator

CONFIG_PATH = Path(__file__).with_name("season_2027.json")

# Spread of a team's results around its rating, per series: form and matchups.
SERIES_FORM_SD = 0.012
# Chance a team swaps two players' roles on a given map, so listed and played role can
# differ. F2 scores the role bonus on the role actually played.
FLEX_P = 0.12
AGENTS_PER_ROLE = 3
FIRST_SERIES_HOUR_UTC = 12
HOURS_BETWEEN_SERIES = 2
SERIES_PER_DAY = 6
MS_PER_MAP = 60 * 60 * 1000


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class MapRecord:
    match_id: str
    map_num: int
    red_team: str
    blue_team: str
    winner: str
    payload: dict[str, Any]  # val-match-v1 shaped


@dataclass
class SeriesRecord:
    series_id: str
    bracket: str
    stage: str
    round_num: int
    week_num: int
    scheduled_ms: int
    best_of: int
    team_a: str
    team_b: str
    maps_a: int
    maps_b: int
    winner: str
    loser: str
    maps: list[MapRecord] = field(default_factory=list)


@dataclass
class EntryRecord:
    team_id: str
    bracket: str
    seed: int
    qualified_via: str
    placement: int = 0


@dataclass
class EventRecord:
    """One finished event. This shape is the contract a real data source must also meet."""

    config: dict[str, Any]
    entries: list[EntryRecord]
    rosters: dict[str, list[str]]  # team_id -> 5 puuids
    series: list[SeriesRecord]
    deadlines: dict[int, int]  # week_num -> deadline in ms


def _utc_ms(day: date, hour: int) -> int:
    moment = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def _pairs(ordered: list[Team]) -> tuple[list[tuple[Team, Team]], list[Team]]:
    """Pair high seed against low seed. With an odd count, the top seed gets the bye."""
    pool = list(ordered)
    byes = [pool.pop(0)] if len(pool) % 2 else []
    half = len(pool) // 2
    return [(pool[i], pool[-1 - i]) for i in range(half)], byes


@dataclass
class _Pairing:
    stage: str
    round_num: int
    team_a: Team
    team_b: Team
    best_of: int


class SeasonSimulator:
    def __init__(self, seed: int, config: dict[str, Any] | None = None,
                 generator: MatchGenerator | None = None, league_seed: int | None = None):
        """`league_seed` replays a league under different results, for balance testing."""
        self.seed = seed
        self.config = config or load_config()
        self.gen = generator or MatchGenerator(seed=seed)
        self.league: League = build_league(self.config, seed if league_seed is None else league_seed)
        self.results: dict[str, EventRecord] = {}
        self.map_ids = self._map_pool()
        self.agents_by_role = self._agents_by_role()
        self.agent_pools = self._assign_agent_pools()

    # --- Content ---------------------------------------------------------------------

    def _map_pool(self) -> list[str]:
        content = json.loads(CONTENT_CACHE.read_text())
        wanted = self.config["map_pool"]["names"]
        by_name = {m["name"]: m["id"] for m in content["maps"]}
        missing = [n for n in wanted if n not in by_name]
        if missing:
            raise ValueError(f"map pool names not in content catalog: {missing}")
        return [by_name[n] for n in wanted]

    def _agents_by_role(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {r: [] for r in CORE_ROLES}
        for agent in self.gen.agents:
            out[role_of(agent)].append(agent)
        return out

    def _assign_agent_pools(self) -> dict[str, list[str]]:
        """Each player has a few agents they play in their role, fixed for the season."""
        pools = {}
        for player in self.league.every_player:
            rng = random.Random(f"{self.seed}:agents:{player.puuid}")
            pools[player.puuid] = rng.sample(self.agents_by_role[player.base_role], AGENTS_PER_ROLE)
        return pools

    # --- Fields ----------------------------------------------------------------------

    def _open_draw(self, event_id: str, teams: list[Team]) -> list[Team]:
        """Stand-in for Open Qualifiers and Open Playoffs, which aren't scored in fantasy.

        Better teams usually get through, and a team that did well in the last event
        gets a small lift, but nothing is guaranteed.
        """
        rng = random.Random(f"{self.seed}:open:{event_id}")
        last_top = self._recent_top_teams()
        def draw(t: Team) -> float:
            lift = 0.012 if t.team_id in last_top else 0.0
            return t.rating + lift + rng.gauss(0, 0.03)
        scored = [(draw(t), t.team_id, t) for t in teams]
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [t for _, _, t in scored]

    def _recent_top_teams(self) -> set[str]:
        if not self.results:
            return set()
        last = list(self.results.values())[-1]
        return {e.team_id for e in last.entries if e.placement <= 4}

    def _regional_field(self, event: dict, region: str) -> list[tuple[Team, str]]:
        spec = event["field"]
        teams = self.league.in_region(region)
        if spec["source"] == "direct_and_open":
            direct_tiers = spec["direct_tiers"]
        else:
            direct_tiers = spec.get("direct_regions_tiers", {}).get(region, [])
        direct = [t for t in teams if t.tier in direct_tiers]
        others = [t for t in teams if t.tier not in direct_tiers]
        entered = self._open_draw(f"{event['id']}:{region}", others)[: spec["teams"] - len(direct)]
        return [(t, f"direct:{t.tier}") for t in direct] + [(t, "open") for t in entered]

    def _international_field(self, event: dict) -> list[tuple[Team, str]]:
        spec = event["field"]
        source = self.results[spec["from_event"]]
        by_id = {t.team_id: t for t in self.league.teams}
        field_: list[tuple[Team, str]] = []
        for region in self.config["regions"]:
            placed = sorted(
                (e for e in source.entries if e.bracket == region),
                key=lambda e: (e.placement, e.seed),
            )
            qualified = placed[: spec["per_region"]]
            field_.extend((by_id[e.team_id], f"{spec['from_event']}:{region}") for e in qualified)
        return field_

    # --- Playing ---------------------------------------------------------------------

    def _agents_for_map(self, team: Team, rng: random.Random) -> list[str]:
        roles = [p.base_role for p in team.roster]
        if rng.random() < FLEX_P:
            i, j = rng.sample(range(len(roles)), 2)
            roles[i], roles[j] = roles[j], roles[i]
        taken: set[str] = set()
        chosen = []
        for player, role in zip(team.roster, roles):
            own = self.agent_pools[player.puuid]
            options = own if role == player.base_role else self.agents_by_role[role]
            free = [a for a in options if a not in taken] or \
                   [a for a in self.agents_by_role[role] if a not in taken]
            agent = rng.choice(free)
            taken.add(agent)
            chosen.append(agent)
        return chosen

    def _play_series(self, series_id: str, pairing: _Pairing, bracket: str, week: int,
                     scheduled_ms: int) -> SeriesRecord:
        rng = random.Random(f"{self.seed}:series:{series_id}")
        a, b = pairing.team_a, pairing.team_b
        form_a, form_b = rng.gauss(0, SERIES_FORM_SD), rng.gauss(0, SERIES_FORM_SD)
        map_order = rng.sample(self.map_ids, pairing.best_of)
        to_win = pairing.best_of // 2 + 1
        wins = {a.team_id: 0, b.team_id: 0}
        maps: list[MapRecord] = []

        for map_num, map_id in enumerate(map_order, start=1):
            if max(wins.values()) >= to_win:
                break
            # Sides alternate by map; a real side-pick would need the veto, which isn't modelled.
            red, blue = (a, b) if map_num % 2 else (b, a)
            red_edge, blue_edge = (a.rating + form_a, b.rating + form_b) if map_num % 2 \
                else (b.rating + form_b, a.rating + form_a)
            match_id = f"{series_id}-m{map_num}"
            fixture = MatchFixture(
                map_id=map_id,
                red=FixtureSide(tuple(p.puuid for p in red.roster),
                                tuple(self._agents_for_map(red, rng)),
                                red_edge, red.player_skill),
                blue=FixtureSide(tuple(p.puuid for p in blue.roster),
                                 tuple(self._agents_for_map(blue, rng)),
                                 blue_edge, blue.player_skill),
                start_ms=scheduled_ms + (map_num - 1) * MS_PER_MAP,
            )
            payload = self.gen.build_match(match_id, fixture=fixture)
            won_red = next(t["won"] for t in payload["teams"] if t["teamId"] == "Red")
            winner = red if won_red else blue
            wins[winner.team_id] += 1
            maps.append(MapRecord(match_id, map_num, red.team_id, blue.team_id,
                                  winner.team_id, payload))

        winner_id = max(wins, key=lambda t: wins[t])
        loser_id = a.team_id if winner_id == b.team_id else b.team_id
        return SeriesRecord(
            series_id=series_id, bracket=bracket, stage=pairing.stage,
            round_num=pairing.round_num, week_num=week, scheduled_ms=scheduled_ms,
            best_of=pairing.best_of, team_a=a.team_id, team_b=b.team_id,
            maps_a=wins[a.team_id], maps_b=wins[b.team_id],
            winner=winner_id, loser=loser_id, maps=maps,
        )

    def _play_bracket(self, event: dict, bracket: str, seeded: list[Team]
                      ) -> tuple[list[SeriesRecord], dict[str, int]]:
        """Double elimination with no bracket reset. Returns series and team placements.

        The rounds are built as results come in, so the calendar is laid out afterwards
        from a dry count: a team's fate doesn't change how many rounds a field size needs.
        """
        fmt = event["format"]
        by_id = {t.team_id: t for t in seeded}
        seed_of = {t.team_id: i for i, t in enumerate(seeded)}
        days = self._series_days(event, _round_count(len(seeded)))

        upper = list(seeded)
        lower: list[Team] = []
        exits: list[tuple[int, str]] = []  # (round eliminated, team)
        series: list[SeriesRecord] = []
        round_num = 0

        def play(stage: str, pairings: list[tuple[Team, Team]], best_of: int) -> list[SeriesRecord]:
            played = []
            for slot, (a, b) in enumerate(pairings):
                series_id = f"vct27-{self.seed}-{event['id']}-{bracket}-r{round_num}-{stage[0]}{slot}"
                day = days[min(round_num, len(days) - 1)]
                hour = FIRST_SERIES_HOUR_UTC + (slot % SERIES_PER_DAY) * HOURS_BETWEEN_SERIES
                record = self._play_series(
                    series_id, _Pairing(stage, round_num, a, b, best_of), bracket,
                    self._week_of(event, day), _utc_ms(day, hour),
                )
                series.append(record)
                played.append(record)
            return played

        def by_seed(teams: list[Team]) -> list[Team]:
            return sorted(teams, key=lambda t: seed_of[t.team_id])

        while len(upper) > 1 or len(lower) > 1:
            dropped: list[Team] = []
            upper_next: list[Team] = []
            lower_next: list[Team] = []

            if len(upper) > 1:
                pairings, byes = _pairs(by_seed(upper))
                upper_next.extend(byes)
                for rec in play("upper", pairings, fmt["best_of"]):
                    upper_next.append(by_id[rec.winner])
                    dropped.append(by_id[rec.loser])
            else:
                upper_next = upper

            if len(lower) > 1:
                pairings, byes = _pairs(by_seed(lower))
                lower_next.extend(byes)
                for rec in play("lower", pairings, fmt["best_of"]):
                    lower_next.append(by_id[rec.winner])
                    exits.append((round_num, rec.loser))
            else:
                lower_next = lower

            upper = upper_next
            lower = lower_next + dropped
            round_num += 1

        final = play("final", [(upper[0], lower[0])], fmt["final_best_of"])[0]
        return series, _placements(final, exits)

    def _series_days(self, event: dict, rounds: int) -> list[date]:
        start, end = date.fromisoformat(event["start"]), date.fromisoformat(event["end"])
        span = (end - start).days
        if rounds == 1:
            return [end]
        return [start + timedelta(days=round(i * span / (rounds - 1))) for i in range(rounds)]

    def _week_of(self, event: dict, day: date) -> int:
        return (day - date.fromisoformat(event["start"])).days // 7 + 1

    def _play_event(self, event: dict) -> EventRecord:
        apply_roster_moves(self.league, self.seed, event["id"])

        if event["kind"] == "regional":
            brackets = {r: self._regional_field(event, r) for r in self.config["regions"]}
        else:
            brackets = {"global": self._international_field(event)}

        entries: list[EntryRecord] = []
        rosters: dict[str, list[str]] = {}
        series: list[SeriesRecord] = []

        for bracket, field_ in brackets.items():
            # Seeded by the sim's ground truth; real seeding isn't announced.
            ordered = sorted(field_, key=lambda f: (-f[0].rating, f[0].team_id))
            seeded = [t for t, _ in ordered]
            played, placements = self._play_bracket(event, bracket, seeded)
            series.extend(played)
            for seed, (team, via) in enumerate(ordered, start=1):
                entries.append(EntryRecord(team.team_id, bracket, seed, via,
                                           placements[team.team_id]))
                rosters[team.team_id] = [p.puuid for p in team.roster]

        deadlines: dict[int, int] = {}
        for s in series:
            deadlines[s.week_num] = min(deadlines.get(s.week_num, s.scheduled_ms), s.scheduled_ms)

        record = EventRecord(event, entries, rosters, series, deadlines)
        self.results[event["id"]] = record
        return record

    def events(self) -> Iterator[EventRecord]:
        for event in self.config["events"]:
            yield self._play_event(event)


def _round_count(teams: int) -> int:
    """Rounds a double elimination of this size needs, not counting the final."""
    upper, lower, rounds = teams, 0, 0
    while upper > 1 or lower > 1:
        dropped = upper // 2 if upper > 1 else 0
        upper_next = upper - dropped
        lower_next = lower - lower // 2 if lower > 1 else lower
        upper, lower = upper_next, lower_next + dropped
        rounds += 1
    return rounds + 1


def _placements(final: SeriesRecord, exits: list[tuple[int, str]]) -> dict[str, int]:
    """1 and 2 from the final, then later exits rank higher. A shared round is a tie."""
    placements = {final.winner: 1, final.loser: 2}
    place = 3
    for round_num in sorted({r for r, _ in exits}, reverse=True):
        out = [team for r, team in exits if r == round_num]
        for team in out:
            placements[team] = place
        place += len(out)
    return placements
