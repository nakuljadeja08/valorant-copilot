"""R2b: per-role peer baselines + within-role percentiles.

The core principle of this layer is *never rank across roles* — a Sentinel's low
first-contact is not a failing, it's the role. So every role feature is scored
against a distribution of *same-role* players. This module builds those
distributions from the computed feature store and answers the one question the UI
actually asks: "where does this player sit among their role's peers?"

Baselines are a **versioned artifact**. They shift as the sim/data changes, so the
version is a content hash of the distributions themselves — same corpus in, same
version out (reproducible), and different data yields a different version. A debrief
cites the version it scored against, so the comparison is auditable, not just the
raw value.

Usage:
    python -m src.features.baselines --build   # build from a deterministic corpus, write artifact
    python -m src.features.baselines --show     # summarize the committed artifact
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.features.queries import player_roles

BASELINE_PATH = Path("data/baselines/role_baselines.json")

# The deterministic corpus the committed artifact is built from. Fixed ids + the
# sim's fixed seed make the baseline reproducible by anyone who reruns --build.
CORPUS_SIZE = 200
CORPUS_IDS = [f"baseline-{i}" for i in range(CORPUS_SIZE)]

# Features where a *lower* raw value is better; the statistical percentile stays
# raw, but consumers (coach/UI) flip orientation so "higher is better" reads
# uniformly. Kept here as the single source of truth for role-feature orientation.
INVERTED_FEATURES = frozenset({"first_death_rate"})

SCHEMA_VERSION = 1  # bump if the distribution encoding changes (invalidates hashes)
_ROUND = 6  # sample precision, so the content hash is stable across platforms


@dataclass(frozen=True)
class PercentileResult:
    role: str
    feature: str
    value: float
    percentile: float          # 0-100, raw statistical rank within the role
    n: int                     # peers the percentile was computed against
    baseline_version: str
    inverted: bool

    @property
    def oriented_percentile(self) -> float:
        """Percentile flipped for inverted metrics, so higher always reads better."""
        return 100.0 - self.percentile if self.inverted else self.percentile


class Baselines:
    """Per-role, per-feature sorted sample distributions with percentile lookup."""

    def __init__(self, distributions: dict[str, dict[str, list[float]]],
                 matches: int, version: str | None = None):
        # Stored sorted so percentile lookup is a bisect and the hash is canonical.
        self.distributions = {
            role: {feat: sorted(round(v, _ROUND) for v in vals)
                   for feat, vals in feats.items()}
            for role, feats in distributions.items()
        }
        self.matches = matches
        self.version = version or self._compute_version()

    def _compute_version(self) -> str:
        canonical = json.dumps(
            {"schema": SCHEMA_VERSION, "distributions": self.distributions},
            sort_keys=True, separators=(",", ":"),
        )
        return f"v{SCHEMA_VERSION}-" + hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def n(self, role: str, feature: str) -> int:
        return len(self.distributions.get(role, {}).get(feature, []))

    def percentile_within_role(self, role: str, feature: str, value: float
                               ) -> PercentileResult | None:
        """Where `value` sits among same-role peers, as a 0-100 percentile.

        Returns None when the role/feature has no peer samples to compare against
        (e.g. a feature nobody of that role ever produced) — callers must not
        fabricate a comparison, so the absence is explicit.
        """
        samples = self.distributions.get(role, {}).get(feature)
        if not samples:
            return None
        # Fraction of peers at or below this value: "better than X% of your role".
        le = bisect.bisect_right(samples, round(value, _ROUND))
        pct = 100.0 * le / len(samples)
        return PercentileResult(
            role=role, feature=feature, value=value, percentile=pct,
            n=len(samples), baseline_version=self.version,
            inverted=feature in INVERTED_FEATURES,
        )

    # --- persistence ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "schema": SCHEMA_VERSION,
            "corpus": {
                "matches": self.matches,
                "samples_by_role": {
                    role: {feat: len(vals) for feat, vals in feats.items()}
                    for role, feats in self.distributions.items()
                },
            },
            "inverted_features": sorted(INVERTED_FEATURES),
            "distributions": self.distributions,
        }

    def save(self, path: Path | str = BASELINE_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str = BASELINE_PATH) -> "Baselines":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        b = cls(distributions=data["distributions"], matches=data["corpus"]["matches"],
                version=data["version"])
        return b


def build_baselines(conn: sqlite3.Connection) -> Baselines:
    """Aggregate every player-scoped role feature into per-role distributions."""
    match_ids = [r["match_id"] for r in conn.execute("SELECT match_id FROM matches")]
    dist: dict[str, dict[str, list[float]]] = {}
    for mid in match_ids:
        roles = player_roles(conn, mid)
        for row in conn.execute(
            "SELECT name, value FROM features WHERE match_id=? AND scope='player'", (mid,)
        ):
            feature, _, puuid = row["name"].partition(":")
            role = roles.get(puuid)
            if role is None:
                continue
            dist.setdefault(role, {}).setdefault(feature, []).append(row["value"])
    return Baselines(distributions=dist, matches=len(match_ids))


def build_from_corpus(match_ids: list[str] = CORPUS_IDS) -> Baselines:
    """Build baselines from a fresh, deterministic sim corpus (in-memory store).

    Independent of the user's local DB so the committed artifact is reproducible.
    """
    from src.features.run import compute_for_match
    from src.ingest.pipeline import normalize
    from src.riot.adapter import get_source
    from src.storage.init import init as init_db

    conn = init_db(":memory:")
    src = get_source("sim")
    for mid in match_ids:
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    try:
        return build_baselines(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true",
                       help="build from the deterministic corpus and write the artifact")
    group.add_argument("--show", action="store_true", help="summarize the committed artifact")
    args = ap.parse_args()

    if args.build:
        b = build_from_corpus()
        path = b.save()
        print(f"baseline {b.version}: {b.matches} matches -> {path}")
        for role in sorted(b.distributions):
            feats = b.distributions[role]
            print(f"  {role:11} {len(feats)} features, "
                  f"{min(len(v) for v in feats.values())}-{max(len(v) for v in feats.values())} samples each")
    else:
        b = Baselines.load()
        print(f"baseline {b.version}: {b.matches} matches")
        for role in sorted(b.distributions):
            for feat, vals in sorted(b.distributions[role].items()):
                mid = vals[len(vals) // 2]
                print(f"  {role:11} {feat:20} n={len(vals):<4} median={mid:.3f}")
