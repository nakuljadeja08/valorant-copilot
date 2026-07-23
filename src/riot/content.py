"""Fetch val-content-v1 and val-status-v1 — the endpoints a development key CAN reach.

This is the pipeline's connection to real Riot data. The simulator reads the cached
content so every simulated match uses authentic agent/map/season IDs.

Usage:
    python -m src.riot.content            # fetch + cache
    python -m src.riot.content --status   # also print platform status
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

from src.riot.client import RiotClient

CONTENT_PATH = Path("data/content.json")


def fetch_content(client: RiotClient, locale: str = "en-US") -> dict:
    platform = os.getenv("RIOT_PLATFORM", "na")
    data = client.get(platform, "/val/content/v1/contents", params={"locale": locale})
    CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)

    slim = {
        "version": data.get("version"),
        "characters": [
            {"id": c["id"], "name": c["name"]}
            for c in data.get("characters", [])
            if not c.get("name", "").startswith("Null")
        ],
        "maps": [
            {"id": m["id"], "name": m["name"], "assetPath": m.get("assetPath", "")}
            for m in data.get("maps", [])
        ],
        "equips": [{"id": e["id"], "name": e["name"]} for e in data.get("equips", [])],
        "acts": [
            {"id": a["id"], "name": a["name"], "isActive": a.get("isActive", False)}
            for a in data.get("acts", [])
        ],
        "gameModes": [{"id": g["id"], "name": g["name"]} for g in data.get("gameModes", [])],
    }
    CONTENT_PATH.write_text(json.dumps(slim, indent=2))
    return slim


def fetch_status(client: RiotClient) -> dict:
    platform = os.getenv("RIOT_PLATFORM", "na")
    return client.get(platform, "/val/status/v1/platform-data")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    client = RiotClient()
    try:
        content = fetch_content(client)
        active = [a["name"] for a in content["acts"] if a["isActive"]]
        print(f"content v{content['version']}: "
              f"{len(content['characters'])} agents, {len(content['maps'])} maps, "
              f"active act: {', '.join(active) or 'n/a'}")
        print(f"cached -> {CONTENT_PATH}")

        if "--status" in sys.argv:
            status = fetch_status(client)
            incidents = status.get("incidents", [])
            print(f"platform: {status.get('name')} — {len(incidents)} incident(s)")
    finally:
        client.close()
