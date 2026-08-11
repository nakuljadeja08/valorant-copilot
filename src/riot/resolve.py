"""UUID -> display name / role lookups against the cached val-content-v1 catalog.

Every match/round row stores raw Riot UUIDs (map_id, character_id). This module
is the single place that turns those UUIDs into names for UI/report labels, so
the mapping only has to be built once per process.

Role (`role_of`) is the R1 layer: a curated agent -> {duelist | initiator |
controller | sentinel} map. Role is *not* in content-v1, so it lives here as a
maintained constant. It is intentionally strict — an unknown agent UUID raises
rather than defaulting, so a new agent shipping without a role entry fails loudly
instead of silently coaching everyone as if they were the same role.

Usage:
    python -m src.riot.resolve            # round-trip check + a sim roster's roles
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

CONTENT_PATH = Path("data/content.json")

Role = Literal["duelist", "initiator", "controller", "sentinel"]

# Curated characterId (UUID) -> role. Seeded from Riot's published role
# classifications and verified against the live agent roster (agents ship often):
# 8 duelists, 7 initiators, 7 controllers, 7 sentinels = 29, matching content.json.
# Keys mirror the (uppercase) UUIDs in data/content.json; lookup is case-insensitive
# so live val-match-v1 payloads (which use lowercase UUIDs) resolve identically.
AGENT_ROLE: dict[str, Role] = {
    # Duelists
    "F94C3B30-42BE-E959-889C-5AA313DBA261": "duelist",     # Raze
    "EB93336A-449B-9C1B-0A54-A891F7921D69": "duelist",     # Phoenix
    "0E38B510-41A8-5780-5E8F-568B2A4F2D6C": "duelist",     # Iso
    "BB2A4828-46EB-8CD1-E765-15848195D751": "duelist",     # Neon
    "7F94D92C-4234-0A36-9646-3A87EB8B5C89": "duelist",     # Yoru
    "DF1CB487-4902-002E-5C17-D28E83E78588": "duelist",     # Waylay
    "A3BFB853-43B2-7238-A4F1-AD90E9E46BCC": "duelist",     # Reyna
    "ADD6443A-41BD-E414-F6AD-E58D267F4E95": "duelist",     # Jett
    # Initiators
    "E370FA57-4757-3604-3648-499E1F642D3F": "initiator",   # Gekko
    "DADE69B4-4F5A-8528-247B-219E5A1FACD6": "initiator",   # Fade
    "5F8D3A7F-467B-97F3-062C-13ACF203C006": "initiator",   # Breach
    "B444168C-4E35-8076-DB47-EF9BF368F384": "initiator",   # Tejo
    "601DBBE7-43CE-BE57-2A40-4ABD24953621": "initiator",   # KAY/O
    "6F2A04CA-43E0-BE17-7F36-B3908627744D": "initiator",   # Skye
    "320B2A48-4D9B-A075-30F1-1F93A9B638FA": "initiator",   # Sova
    # Controllers
    "7C8A4701-4DE6-9355-B254-E09BC2A34B72": "controller",  # Miks
    "95B78ED7-4637-86D9-7E41-71BA8C293152": "controller",  # Harbor
    "707EAB51-4836-F488-046A-CDA6BF494859": "controller",  # Viper
    "41FB69C1-4189-7B37-F117-BCAF1E96F1BF": "controller",  # Astra
    "9F0D8BA9-4140-B941-57D3-A7AD57C6B417": "controller",  # Brimstone
    "1DBF2EDD-4729-0984-3115-DAA5EED44993": "controller",  # Clove
    "8E253930-4C05-31DD-1B6C-968525494517": "controller",  # Omen
    # Sentinels
    "CC8B64C8-4B25-4FF9-6E7F-37B4DA43D235": "sentinel",    # Deadlock
    "22697A3D-45BF-8DD7-4FEC-84A9E28C69D7": "sentinel",    # Chamber
    "117ED9E3-49F3-6512-3CCF-0CADA7E3823B": "sentinel",    # Cypher
    "1E58DE9C-4950-5125-93E9-A0AEE9F98746": "sentinel",    # Killjoy
    "EFBA5359-4016-A1E5-7626-B1AE76895940": "sentinel",    # Vyse
    "92EEEF5D-43B5-1D4A-8D03-B3927A09034B": "sentinel",    # Veto
    "569FDD95-4D10-43AB-CA70-79BECC718B46": "sentinel",    # Sage
}

# Case-insensitive index (live payloads use lowercase UUIDs; the cache uppercase).
_ROLE_BY_ID: dict[str, Role] = {k.lower(): v for k, v in AGENT_ROLE.items()}


class UnknownAgentError(KeyError):
    """Raised when an agent UUID has no role mapping — a loud failure by design.

    A new agent shipping without an AGENT_ROLE entry should stop the pipeline, not
    be silently bucketed into an arbitrary role. Add the agent to AGENT_ROLE.
    """


def role_of(character_id: str) -> Role:
    """Map an agent UUID to its role. Raises UnknownAgentError on an unmapped UUID."""
    try:
        return _ROLE_BY_ID[character_id.lower()]
    except KeyError:
        raise UnknownAgentError(
            f"no role mapping for agent {character_id!r}; add it to AGENT_ROLE"
        ) from None


class ContentResolver:
    """Looks up agent/map display names by UUID from the cached content catalog."""

    def __init__(self, content_path: Path | str = CONTENT_PATH):
        content = json.loads(Path(content_path).read_text())
        self._agents = {c["id"]: c["name"] for c in content.get("characters", [])}
        self._maps = {m["id"]: m["name"] for m in content.get("maps", [])}

    def agent_name(self, character_id: str) -> str:
        return self._agents.get(character_id, f"unknown-agent:{character_id}")

    def agent_role(self, character_id: str) -> Role:
        """Role for an agent UUID. Delegates to the module-level `role_of`."""
        return role_of(character_id)

    def map_name(self, map_id: str) -> str:
        return self._maps.get(map_id, f"unknown-map:{map_id}")

    @property
    def agent_ids(self) -> list[str]:
        return list(self._agents)

    @property
    def map_ids(self) -> list[str]:
        return list(self._maps)


@lru_cache(maxsize=1)
def default_resolver() -> ContentResolver:
    return ContentResolver()


if __name__ == "__main__":
    r = default_resolver()
    agent_misses = [aid for aid in r.agent_ids if r.agent_name(aid).startswith("unknown-agent:")]
    map_misses = [mid for mid in r.map_ids if r.map_name(mid).startswith("unknown-map:")]
    print(f"agents: {len(r.agent_ids)} round-tripped, {len(agent_misses)} failed")
    print(f"maps: {len(r.map_ids)} round-tripped, {len(map_misses)} failed")

    # Every agent in the content cache must carry exactly one role (R1 checklist).
    role_misses = [aid for aid in r.agent_ids if aid.lower() not in _ROLE_BY_ID]
    print(f"roles: {len(r.agent_ids) - len(role_misses)}/{len(r.agent_ids)} agents mapped")
    for aid in role_misses:
        print(f"  UNMAPPED role: {r.agent_name(aid)} ({aid})")

    # Demoable artifact: for a sim match, print each player's agent -> role.
    from src.riot.adapter import get_source

    src = get_source("sim")
    match_id = src.matchlist("hero")[0]
    match = src.match(match_id)
    print(f"\nsim match {match_id} — roster roles:")
    for p in match["players"]:
        cid = p["characterId"]
        print(f"  {p['teamId']:>4}  {r.agent_name(cid):<10} -> {role_of(cid)}")

    if agent_misses or map_misses or role_misses:
        raise SystemExit(1)
