"""Schema-faithful VALORANT match simulator.

Emits payloads matching the documented `val-match-v1` response shape, grounded in
real map/agent IDs pulled from `val-content-v1` (which *is* dev-key accessible).

This is not a toy random generator: the economy model is causal, so downstream
coaching conclusions are testable against known ground truth. Round outcome is a
function of loadout differential, plant state, and a skill prior — which means we
can assert that the Economist agent recovers the eco-loss relationship we injected.
That property is the whole reason the simulator is worth building rather than
hand-waving with pure noise.

**Role-awareness (R2e).** On top of the causal economy core, combat is resolved as
a per-round *kill timeline* whose ordering is weighted by each player's agent role:
duelists are drawn into first contact (as first killer *and* first victim),
sentinels are picked last so they survive late and rarely take the opening death,
and initiators are credited assists. Utility cast counts per round also skew by
role. This is what makes the role features downstream (first-contact, first-death,
trades, setup) non-vacuous. It is `sim-approx` ground truth — the *shape* is real,
the numbers stand in for live data until a production key lands.
"""

from __future__ import annotations

import os
import json
import random
import uuid
from pathlib import Path

from src.riot.resolve import Role, UnknownAgentError, role_of

CONTENT_CACHE = Path("data/content.json")

# Fallback IDs if content cache is absent. Replaced by real val-content-v1 UUIDs.
FALLBACK_MAPS = ["Ascent", "Bind", "Haven", "Split", "Lotus", "Sunset", "Abyss"]
FALLBACK_AGENTS = ["Jett", "Omen", "Sova", "Killjoy", "Raze", "Cypher", "Viper"]
# Roles for the fallback agents (which are names, not UUIDs, so `role_of` can't map
# them). Keeps role behaviour working even without the content cache.
FALLBACK_ROLE: dict[str, Role] = {
    "Jett": "duelist", "Raze": "duelist", "Sova": "initiator", "Omen": "controller",
    "Viper": "controller", "Killjoy": "sentinel", "Cypher": "sentinel",
}

ROUND_RESULTS = ["Eliminated", "Bomb detonated", "Bomb defused", "Round timer expired"]

CREDS_START = 800
CREDS_MAX = 9000
WIN_REWARD = 3000
LOSS_BONUS = [1900, 2400, 2900]  # escalates with consecutive losses

# --- Role behaviour weights (R2e) -----------------------------------------------
# ENTRY: likelihood of making a kill / being the aggressor (drives first kills).
# EXPOSURE: likelihood of *being* a victim, weighted toward early deaths (duelists
#   peek first and die first; sentinels hold and are picked last -> late survival).
# ASSIST: likelihood of being credited an assist (initiators set up kills).
ENTRY_WEIGHT: dict[Role, float] = {
    "duelist": 4.0, "initiator": 2.0, "controller": 1.3, "sentinel": 1.1,
}
EXPOSURE_WEIGHT: dict[Role, float] = {
    "duelist": 3.0, "initiator": 1.6, "controller": 1.4, "sentinel": 0.7,
}
ASSIST_WEIGHT: dict[Role, float] = {
    "initiator": 4.0, "controller": 2.0, "sentinel": 1.3, "duelist": 1.0,
}
# Mean per-round utility casts (grenade, ability1, ability2) by role. Capped at 3
# per slot. Support roles cast the most; duelists spend their kit entering.
UTILITY_MEANS: dict[Role, tuple[float, float, float]] = {
    "duelist": (0.3, 0.6, 0.3),
    "initiator": (0.8, 1.4, 1.0),
    "controller": (1.6, 1.1, 0.6),
    "sentinel": (0.6, 0.8, 0.5),
}
TRADE_P = 0.35  # chance the previous fragger is immediately traded back


def _other(side: str) -> str:
    return "Blue" if side == "Red" else "Red"


def _role_of(character_id: str) -> Role:
    """Role for a roster entry, tolerant of the (cache-less) fallback names."""
    try:
        return role_of(character_id)
    except UnknownAgentError:
        return FALLBACK_ROLE.get(character_id, "initiator")


def _capped_count(rng: random.Random, mean: float, cap: int = 3) -> int:
    """A small non-negative count with the given mean, capped — mean = cap * p."""
    p = min(max(mean / cap, 0.0), 1.0)
    return sum(1 for _ in range(cap) if rng.random() < p)


def _weighted_sample(rng: random.Random, items: list, weights: list[float], k: int) -> list:
    """Sample k distinct items with the given weights, without replacement."""
    items, weights = list(items), list(weights)
    out = []
    for _ in range(min(k, len(items))):
        i = rng.choices(range(len(items)), weights=weights)[0]
        out.append(items.pop(i))
        weights.pop(i)
    return out


class MatchGenerator:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed or int(os.getenv("SIM_SEED", "1337")))
        self.maps, self.agents = self._load_content()

    def _load_content(self) -> tuple[list[str], list[str]]:
        if CONTENT_CACHE.exists():
            c = json.loads(CONTENT_CACHE.read_text())
            maps = [m["id"] for m in c.get("maps", [])] or FALLBACK_MAPS
            agents = [a["id"] for a in c.get("characters", [])] or FALLBACK_AGENTS
            return maps, agents
        return FALLBACK_MAPS, FALLBACK_AGENTS

    def matchlist_for(self, puuid: str, n: int = 100) -> list[str]:
        r = random.Random(f"{puuid}-list")
        return [str(uuid.UUID(int=r.getrandbits(128))) for _ in range(n)]

    def _team_skill(self) -> float:
        return self.rng.gauss(0.0, 0.15)

    def _combat(
        self,
        crng: random.Random,
        roster: dict[str, list[str]],
        role_by_puuid: dict[str, Role],
        winner: str,
        loser: str,
        result: str,
        round_start_ms: int,
    ) -> dict[str, dict]:
        """Resolve one round as an ordered, role-weighted kill timeline.

        Victims are drawn from whichever side still owes deaths, weighted by
        EXPOSURE (so duelists die early, sentinels survive); the killer comes from
        the opposing side weighted by ENTRY. The first event is the round's first
        contact. Returns per-puuid stats including the `kills` list that player was
        the *killer* in (val-match-v1 nests kills under the killer's playerStats).
        """
        alive = {s: list(roster[s]) for s in roster}
        # Casualty targets: a wiped side (Eliminated) loses all 5; otherwise partial.
        if result == "Eliminated":
            loser_losses, winner_losses = 5, crng.randint(0, 4)
        else:
            loser_losses, winner_losses = crng.randint(2, 5), crng.randint(0, 4)
        owed = {loser: loser_losses, winner: winner_losses}

        stats = {
            p: {"kills": [], "kill_count": 0, "died": False, "assists": 0}
            for side in roster for p in roster[side]
        }
        t = round_start_ms + crng.randint(4000, 20000)
        prev_killer: str | None = None
        prev_killer_side: str | None = None

        while sum(owed.values()) > 0:
            # A side can supply a victim only if it owes a death AND the opposing
            # side still has someone alive to credit the kill to.
            victim_sides = [s for s in ("Red", "Blue")
                            if owed[s] > 0 and alive[s] and alive[_other(s)]]
            if not victim_sides:
                break

            traded = False
            # Light trade mechanic: the previous fragger is answered right back.
            if (prev_killer is not None and prev_killer_side in victim_sides
                    and prev_killer in alive[prev_killer_side]
                    and crng.random() < TRADE_P):
                vside, victim, traded = prev_killer_side, prev_killer, True
            else:
                cands = [(s, p) for s in victim_sides for p in alive[s]]
                weights = [EXPOSURE_WEIGHT[role_by_puuid[p]] for _, p in cands]
                vside, victim = crng.choices(cands, weights=weights)[0]

            kside = _other(vside)
            killer = crng.choices(
                alive[kside],
                weights=[ENTRY_WEIGHT[role_by_puuid[p]] for p in alive[kside]],
            )[0]

            mates = [p for p in roster[kside] if p != killer]
            n_assist = crng.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
            assisters = _weighted_sample(
                crng, mates, [ASSIST_WEIGHT[role_by_puuid[p]] for p in mates], n_assist
            )

            stats[killer]["kills"].append({
                "killer": killer,
                "victim": victim,
                "assistants": assisters,
                "timeSinceRoundStartMillis": t - round_start_ms,
                "timeSinceGameStartMillis": t,
                "traded": traded,
            })
            stats[killer]["kill_count"] += 1
            stats[victim]["died"] = True
            for a in assisters:
                stats[a]["assists"] += 1

            alive[vside].remove(victim)
            owed[vside] -= 1
            prev_killer, prev_killer_side = killer, kside
            t += crng.randint(1500, 9000)

        return stats

    def build_match(self, match_id: str, hero_puuid: str = "hero") -> dict:
        rng = random.Random(match_id)
        map_id = rng.choice(self.maps)

        teams = {"Red": [], "Blue": []}
        agents = rng.sample(self.agents, min(10, len(self.agents))) * 2
        for i in range(10):
            side = "Red" if i < 5 else "Blue"
            teams[side].append({
                "puuid": hero_puuid if i == 0 else str(uuid.UUID(int=rng.getrandbits(128))),
                "teamId": side,
                "characterId": agents[i],
                "competitiveTier": rng.randint(21, 23),  # Immortal band
            })

        roster = {s: [p["puuid"] for p in teams[s]] for s in teams}
        role_by_puuid = {
            p["puuid"]: _role_of(p["characterId"]) for s in teams for p in teams[s]
        }

        skill = {"Red": rng.gauss(0, 0.15), "Blue": rng.gauss(0, 0.15)}
        creds = {"Red": CREDS_START, "Blue": CREDS_START}
        streak = {"Red": 0, "Blue": 0}
        rounds, wins = [], {"Red": 0, "Blue": 0}
        players_out = {p["puuid"]: {"kills": 0, "deaths": 0, "assists": 0, "score": 0}
                       for side in teams for p in teams[side]}

        rnum = 0
        while max(wins.values()) < 13 and rnum < 24:
            loadout = {s: min(creds[s], CREDS_MAX) for s in ("Red", "Blue")}
            spent = {s: int(loadout[s] * rng.uniform(0.55, 0.95)) for s in ("Red", "Blue")}

            # Causal core: economy differential drives win probability.
            econ_edge = (spent["Red"] - spent["Blue"]) / 20000.0
            p_red = 0.5 + econ_edge + (skill["Red"] - skill["Blue"])
            p_red = min(max(p_red, 0.05), 0.95)
            winner = "Red" if rng.random() < p_red else "Blue"
            loser = "Blue" if winner == "Red" else "Red"

            planted = rng.random() < 0.55
            result = rng.choice(ROUND_RESULTS[:2] if planted else ["Eliminated", "Round timer expired"])

            # Combat: role-weighted kill timeline on its own deterministic stream, so
            # the economy/winner draws above stay independent of round order.
            combat = self._combat(
                random.Random(f"{match_id}:{rnum}:combat"),
                roster, role_by_puuid, winner, loser, result, rnum * 100_000,
            )
            # Utility casts on their own deterministic stream, drawn in roster order.
            urng = random.Random(f"{match_id}:{rnum}:util")

            round_stats = []
            for side in ("Red", "Blue"):
                for p in teams[side]:
                    puuid = p["puuid"]
                    cs = combat[puuid]
                    k, died, assists = cs["kill_count"], cs["died"], cs["assists"]
                    dmg = k * rng.randint(120, 180) + assists * 40
                    role = role_by_puuid[puuid]
                    util = UTILITY_MEANS[role]
                    players_out[puuid]["kills"] += k
                    players_out[puuid]["deaths"] += 1 if died else 0
                    players_out[puuid]["assists"] += assists
                    players_out[puuid]["score"] += dmg
                    round_stats.append({
                        "puuid": puuid,
                        "economy": {
                            "loadoutValue": loadout[side] // 5,
                            "spent": spent[side] // 5,
                            "remaining": (loadout[side] - spent[side]) // 5,
                            "weapon": "", "armor": "",
                        },
                        "kills": cs["kills"],
                        "ability": {
                            "grenadeCasts": _capped_count(urng, util[0]),
                            "ability1Casts": _capped_count(urng, util[1]),
                            "ability2Casts": _capped_count(urng, util[2]),
                            "ultimateCasts": 0,
                        },
                        "damage": [], "score": dmg,
                    })

            rounds.append({
                "roundNum": rnum,
                "roundResult": result,
                "roundCeremony": "CeremonyDefault",
                "winningTeam": winner,
                "plantSite": rng.choice(["A", "B", "C"]) if planted else "",
                "plantRoundTime": rng.randint(20000, 60000) if planted else 0,
                "defuseRoundTime": rng.randint(30000, 75000) if result == "Bomb defused" else 0,
                "playerStats": round_stats,
            })

            wins[winner] += 1
            streak[loser] = min(streak[loser] + 1, 2)
            streak[winner] = 0
            creds[winner] = min(creds[winner] - spent[winner] + WIN_REWARD, CREDS_MAX)
            creds[loser] = min(creds[loser] - spent[loser] + LOSS_BONUS[streak[loser]], CREDS_MAX)
            rnum += 1

        return {
            "matchInfo": {
                "matchId": match_id,
                "mapId": map_id,
                "gameLengthMillis": rnum * 100_000,
                "gameStartMillis": 1_770_000_000_000 + rng.randint(0, 10_000_000),
                "isCompleted": True,
                "queueId": "competitive",
                "seasonId": "e10a3",
            },
            "players": [
                {**p, **players_out[p["puuid"]], "stats": players_out[p["puuid"]]}
                for side in teams for p in teams[side]
            ],
            "teams": [
                {"teamId": s, "won": wins[s] >= 13, "roundsPlayed": rnum, "roundsWon": wins[s]}
                for s in ("Red", "Blue")
            ],
            "roundResults": rounds,
        }
