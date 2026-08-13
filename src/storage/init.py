"""Bootstrap the local match store.

Usage:
    python -m src.storage.init
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")

# `schema.sql` uses CREATE TABLE IF NOT EXISTS, so a column added to it is invisible
# to any store that already exists. Each entry is (table, column, declaration) and is
# applied only when the column is missing, which keeps init() idempotent.
MIGRATIONS = [
    ("matches", "hero_puuid", "TEXT"),
    # R2a: utility cast counts, for role cadence/volume features.
    ("round_player_stats", "grenade_casts", "INTEGER DEFAULT 0"),
    ("round_player_stats", "ability1_casts", "INTEGER DEFAULT 0"),
    ("round_player_stats", "ability2_casts", "INTEGER DEFAULT 0"),
    ("round_player_stats", "ultimate_casts", "INTEGER DEFAULT 0"),
]


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.getenv("DB_PATH", "data/copilot.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init(db_path: str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA.read_text())
    _migrate(conn)
    conn.commit()
    return conn


if __name__ == "__main__":
    c = init()
    tables = [r["name"] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"initialized {os.getenv('DB_PATH', 'data/copilot.db')}")
    print("tables:", ", ".join(tables))
