"""Feature protocol + row type for the feature store.

Every derived signal a coaching claim cites is a FeatureRow: a value plus the
`inputs` lineage it was computed from. Phase 3's decision trace walks that
lineage backward from a claim to the raw rows behind it, so lineage is
recorded here rather than reconstructed later.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Protocol

MATCH_SCOPE_ROUND = -1  # sentinel: this feature is match-scoped, not per-round


@dataclass
class FeatureRow:
    match_id: str
    scope: str  # 'match' | 'round' | 'team_round' | ...
    name: str
    value: float
    inputs: list[dict[str, Any]] = field(default_factory=list)
    round_num: int = MATCH_SCOPE_ROUND

    def inputs_json(self) -> str:
        return json.dumps(self.inputs, sort_keys=True)


class Feature(Protocol):
    """A feature knows its own name and how to derive its rows for one match."""

    name: str

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        ...
