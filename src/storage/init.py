"""Bootstrap the local match store.

Usage:
    python -m src.storage.init
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.getenv("DB_PATH", "data/copilot.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    return conn


if __name__ == "__main__":
    c = init()
    tables = [r["name"] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"initialized {os.getenv('DB_PATH', 'data/copilot.db')}")
    print("tables:", ", ".join(tables))
