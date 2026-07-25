"""UUID -> display name lookups against the cached val-content-v1 catalog.

Every match/round row stores raw Riot UUIDs (map_id, character_id). This module
is the single place that turns those UUIDs into names for UI/report labels, so
the mapping only has to be built once per process.

Usage:
    python -m src.riot.resolve            # round-trip check against content.json
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONTENT_PATH = Path("data/content.json")


class ContentResolver:
    """Looks up agent/map display names by UUID from the cached content catalog."""

    def __init__(self, content_path: Path | str = CONTENT_PATH):
        content = json.loads(Path(content_path).read_text())
        self._agents = {c["id"]: c["name"] for c in content.get("characters", [])}
        self._maps = {m["id"]: m["name"] for m in content.get("maps", [])}

    def agent_name(self, character_id: str) -> str:
        return self._agents.get(character_id, f"unknown-agent:{character_id}")

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
    if agent_misses or map_misses:
        raise SystemExit(1)
