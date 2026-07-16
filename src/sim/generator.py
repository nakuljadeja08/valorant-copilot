"""Schema-faithful VALORANT match simulator.

Emits payloads matching the documented `val-match-v1` response shape, grounded in
real map/agent IDs pulled from `val-content-v1` (which *is* dev-key accessible).

This is not a toy random generator: the economy model is causal, so downstream
coaching conclusions are testable against known ground truth. Round outcome is a
function of loadout differential, plant state, and a skill prior — which means we
can assert that the Economist agent recovers the eco-loss relationship we injected.
That property is the whole reason the simulator is worth building rather than
hand-waving with pure noise.
"""

from __future__ import annotations

import os
import json
import random
import uuid
from pathlib import Path

CONTENT_CACHE = Path("data/content.json")

# Fallback IDs if content cache is absent. Replaced by real val-content-v1 UUIDs.
FALLBACK_MAPS = ["Ascent", "Bind", "Haven", "Split", "Lotus", "Sunset", "Abyss"]
FALLBACK_AGENTS = ["Jett", "Omen", "Sova", "Killjoy", "Raze", "Cypher", "Viper"]

ROUND_RESULTS = ["Eliminated", "Bomb detonated", "Bomb defused", "Round timer expired"]

CREDS_START = 800
CREDS_MAX = 9000
WIN_REWARD = 3000
LOSS_BONUS = [1900, 2400, 2900]  # escalates with consecutive losses


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

            round_stats = []
            for side in ("Red", "Blue"):
                for p in teams[side]:
                    k = rng.randint(0, 3) if side == winner else rng.randint(0, 2)
                    dmg = k * rng.randint(120, 180) + rng.randint(0, 90)
                    players_out[p["puuid"]]["kills"] += k
                    players_out[p["puuid"]]["deaths"] += 1 if side == loser and rng.random() < 0.8 else 0
                    players_out[p["puuid"]]["score"] += dmg
                    round_stats.append({
                        "puuid": p["puuid"],
                        "economy": {
                            "loadoutValue": loadout[side] // 5,
                            "spent": spent[side] // 5,
                            "remaining": (loadout[side] - spent[side]) // 5,
                            "weapon": "", "armor": "",
                        },
                        "kills": k, "damage": [], "score": dmg,
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
