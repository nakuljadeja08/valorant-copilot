"""Tests for the feature store plumbing: protocol, idempotency, lineage integrity.

Phase 2b adds the real features; these exercise the mechanism itself with a
minimal stand-in so the plumbing is validated before any concrete feature
exists.
"""

import sqlite3

from src.features.base import FeatureRow
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db


class RoundCountFeature:
    """Minimal stand-in: one match-scoped row, lineage pointing at every round."""

    name = "round_count"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = conn.execute(
            "SELECT round_num FROM rounds WHERE match_id=? ORDER BY round_num", (match_id,)
        ).fetchall()
        return [
            FeatureRow(
                match_id=match_id,
                scope="match",
                name=self.name,
                value=float(len(rounds)),
                inputs=[{"table": "rounds", "match_id": match_id, "round_num": r["round_num"]}
                        for r in rounds],
            )
        ]


def _seeded_db(tmp_path, match_id: str = "feat-test-1") -> tuple[sqlite3.Connection, str]:
    conn = init_db(str(tmp_path / "test.db"))
    src = get_source("sim")
    normalize(conn, src.match(match_id), "sim")
    return conn, match_id


class TestFeatureRunner:
    def test_empty_registry_is_a_valid_noop(self, tmp_path):
        conn, match_id = _seeded_db(tmp_path)
        rows = compute_for_match(conn, match_id, features=[])
        assert rows == []
        assert conn.execute("SELECT COUNT(*) c FROM features").fetchone()["c"] == 0

    def test_idempotent_rerun_does_not_duplicate(self, tmp_path):
        conn, match_id = _seeded_db(tmp_path)
        compute_for_match(conn, match_id, features=[RoundCountFeature()])
        compute_for_match(conn, match_id, features=[RoundCountFeature()])

        rows = conn.execute(
            "SELECT * FROM features WHERE match_id=? AND name='round_count'", (match_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["round_num"] == -1  # match-scope sentinel
        assert rows[0]["scope"] == "match"

    def test_lineage_references_only_existing_rows(self, tmp_path):
        conn, match_id = _seeded_db(tmp_path)
        compute_for_match(conn, match_id, features=[RoundCountFeature()])

        row = conn.execute(
            "SELECT inputs_json, value FROM features WHERE match_id=? AND name='round_count'",
            (match_id,),
        ).fetchone()

        import json
        inputs = json.loads(row["inputs_json"])
        assert len(inputs) == int(row["value"])
        existing_rounds = {
            r["round_num"] for r in conn.execute(
                "SELECT round_num FROM rounds WHERE match_id=?", (match_id,)
            )
        }
        for ref in inputs:
            assert ref["table"] == "rounds"
            assert ref["match_id"] == match_id
            assert ref["round_num"] in existing_rounds
