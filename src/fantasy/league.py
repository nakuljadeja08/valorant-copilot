"""The fictional 2027 league: teams, players and coaches for the simulated season.

**Nothing here is a real person or organisation.** Invented stats must never be attached
to a real pro, so names are built from word lists and invented syllables, and
`tests/test_fantasy_sim.py` checks them against the real partner-team list.

Ratings are simulation ground truth. Players carry a `skill` multiplier on their kill and
survival weights; teams carry a `rating` added to their round-win probability.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field

from src.riot.resolve import Role

CORE_ROLES: tuple[Role, ...] = ("duelist", "initiator", "controller", "sentinel")

TEAM_WORDS_A = (
    "Cobalt", "Velvet", "Ember", "Hollow", "Quiet", "Copper", "Paper", "Lunar", "Bright",
    "Silent", "Amber", "Iron", "Salt", "Wild", "Slate", "Marble", "Ashen", "Golden",
)
TEAM_WORDS_B = (
    "Herons", "Anchors", "Lanterns", "Foxes", "Comets", "Otters", "Kestrels", "Tides",
    "Bellows", "Ravens", "Harbors", "Thistles", "Pilots", "Sparrows", "Orchards", "Wolves",
)
SYLLABLES = (
    "va", "lo", "ri", "ke", "su", "ta", "mi", "no", "xe", "dra", "qui", "zo", "fen", "ly",
    "ro", "sha", "ven", "tu", "bre", "ka", "ni", "gor", "el", "vy",
)

# Round-win edge. A rating gap of one standard deviation is worth about 3 points of
# round-win probability, which over 24 rounds decides most maps without deciding all.
TEAM_RATING_SD = 0.022
TIER_RATING_BONUS = {"partner": 0.018, "visitor": 0.006, "open": 0.0}
# Multiplier on kill weights, as exp(gauss). Partners sign slightly better players.
PLAYER_SKILL_SD = 0.12
TIER_SKILL_BONUS = {"partner": 0.05, "visitor": 0.02, "open": 0.0}


@dataclass
class Player:
    puuid: str
    handle: str
    region: str
    base_role: Role
    skill: float


@dataclass
class Coach:
    coach_id: str
    handle: str


@dataclass
class Team:
    team_id: str
    name: str
    region: str
    tier: str  # partner | visitor | open
    rating: float
    coach: Coach
    roster: list[Player] = field(default_factory=list)  # always exactly 5

    @property
    def player_skill(self) -> dict[str, float]:
        return {p.puuid: p.skill for p in self.roster}


@dataclass
class League:
    teams: list[Team]
    free_agents: dict[str, list[Player]]  # region -> unsigned players
    every_player: list[Player]

    def in_region(self, region: str) -> list[Team]:
        return [t for t in self.teams if t.region == region]


def _new_id(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128)))


class _Names:
    """Unique names across the league."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.teams = [f"{a} {b}" for a in TEAM_WORDS_A for b in TEAM_WORDS_B]
        rng.shuffle(self.teams)
        self.handles: set[str] = set()

    def team(self) -> str:
        return self.teams.pop()

    def handle(self) -> str:
        # Three syllables: real pro handles are rarely this long, so a chance match is unlikely.
        while True:
            name = "".join(self.rng.choices(SYLLABLES, k=3)).capitalize()
            if name not in self.handles:
                self.handles.add(name)
                return name


def _player(rng: random.Random, names: _Names, region: str, role: Role, bonus: float) -> Player:
    return Player(
        puuid=_new_id(rng),
        handle=names.handle(),
        region=region,
        base_role=role,
        skill=round(math.exp(rng.gauss(bonus, PLAYER_SKILL_SD)), 6),
    )


def _roster_roles(rng: random.Random) -> list[Role]:
    """Every team fields all four roles, plus a fifth player in any of them."""
    return [*CORE_ROLES, rng.choice(CORE_ROLES)]


def build_league(config: dict, seed: int) -> League:
    """Deterministic for a given seed. Depends on nothing but the seed and the config."""
    rng = random.Random(f"{seed}:league")
    names = _Names(rng)
    teams: list[Team] = []
    free_agents: dict[str, list[Player]] = {}
    every_player: list[Player] = []

    for region in config["regions"]:
        for tier, count in config["league"]["tiers"][region].items():
            for _ in range(count):
                team = Team(
                    team_id=_new_id(rng),
                    name=names.team(),
                    region=region,
                    tier=tier,
                    rating=round(rng.gauss(TIER_RATING_BONUS[tier], TEAM_RATING_SD), 6),
                    coach=Coach(_new_id(rng), names.handle()),
                )
                team.roster = [
                    _player(rng, names, region, role, TIER_SKILL_BONUS[tier])
                    for role in _roster_roles(rng)
                ]
                every_player.extend(team.roster)
                teams.append(team)

        pool = [
            _player(rng, names, region, rng.choice(CORE_ROLES), 0.0)
            for _ in range(config["league"]["free_agents_per_region"])
        ]
        free_agents[region] = pool
        every_player.extend(pool)

    return League(teams=teams, free_agents=free_agents, every_player=every_player)


# Between events, a team may sign one free agent in the same role. One move per break
# stays inside Riot's rule that a team keeps its progress with 3 of its 5 players.
ROSTER_MOVE_P = {"partner": 0.06, "visitor": 0.10, "open": 0.15}


def apply_roster_moves(league: League, seed: int, event_id: str) -> list[tuple[str, str, str]]:
    """Apply moves before `event_id`. Returns (team_id, puuid_out, puuid_in) for each."""
    rng = random.Random(f"{seed}:moves:{event_id}")
    moves = []
    for team in league.teams:
        if rng.random() >= ROSTER_MOVE_P[team.tier]:
            continue
        slot = rng.randrange(len(team.roster))
        outgoing = team.roster[slot]
        pool = league.free_agents[team.region]
        same_role = [p for p in pool if p.base_role == outgoing.base_role]
        if not same_role:
            continue
        incoming = rng.choice(same_role)
        pool.remove(incoming)
        pool.append(outgoing)
        team.roster[slot] = incoming
        moves.append((team.team_id, outgoing.puuid, incoming.puuid))
    return moves
