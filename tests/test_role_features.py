"""R2a-2: role features are non-vacuous and honest through the feature store.

R2e proved the *simulator* separates roles; these prove the separation survives
the round trip into computed `features` rows — the thing coaching claims will
actually read. Plus the guards that keep the numbers honest: rates stay in range,
and entry_trade_rate only exists where the player actually died on entry.
"""

from collections import defaultdict

import pytest

from src.features.queries import player_roles
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

ROLES = ("duelist", "initiator", "controller", "sentinel")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    conn = init_db(str(tmp_path_factory.mktemp("rolefeat") / "r.db"))
    src = get_source("sim")
    for i in range(90):
        mid = f"rolefeat-{i}"
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    return conn


def _mean_by_role(conn, feature: str) -> dict[str, float]:
    """Average of a player-scoped feature, grouped by the player's role."""
    sums = defaultdict(float)
    counts = defaultdict(int)
    for mid in [r["match_id"] for r in conn.execute("SELECT match_id FROM matches")]:
        roles = player_roles(conn, mid)
        for r in conn.execute(
            "SELECT name, value FROM features WHERE match_id=? AND scope='player' "
            "AND name LIKE ?", (mid, f"{feature}:%"),
        ):
            puuid = r["name"].split(":", 1)[1]
            role = roles.get(puuid)
            if role:
                sums[role] += r["value"]
                counts[role] += 1
    return {role: sums[role] / counts[role] for role in ROLES if counts[role]}


def test_duelists_lead_first_contact_through_the_store(store):
    m = _mean_by_role(store, "first_contact_rate")
    assert m["duelist"] > m["sentinel"] * 1.5
    assert m["duelist"] > m["initiator"] > m["sentinel"]


def test_sentinels_have_the_lowest_first_death_rate(store):
    m = _mean_by_role(store, "first_death_rate")
    assert m["sentinel"] == min(m.values())
    assert m["sentinel"] < m["duelist"]


def test_support_roles_lead_utility_and_assists(store):
    util = _mean_by_role(store, "utility_per_round")
    assert util["initiator"] > util["duelist"]
    assert util["controller"] > util["duelist"]
    assists = _mean_by_role(store, "assist_rate")
    assert assists["initiator"] > assists["duelist"]


def test_rate_features_stay_in_unit_range(store):
    unit_rate_features = (
        "first_contact_rate", "entry_success_rate", "first_death_rate",
        "entry_trade_rate", "multikill_rate", "survival_rate",
    )
    for feat in unit_rate_features:
        for r in store.execute(
            "SELECT value FROM features WHERE scope='player' AND name LIKE ?", (f"{feat}:%",)
        ):
            assert 0.0 <= r["value"] <= 1.0, f"{feat} out of [0,1]: {r['value']}"


def test_entry_trade_rate_only_exists_where_they_died_on_entry(store):
    """A player with an entry_trade_rate row must have a positive first_death_rate —
    otherwise the rate has no denominator and shouldn't have been emitted."""
    for mid in [r["match_id"] for r in store.execute("SELECT match_id FROM matches")]:
        fd = {r["name"].split(":", 1)[1]: r["value"] for r in store.execute(
            "SELECT name, value FROM features WHERE match_id=? AND name LIKE 'first_death_rate:%'",
            (mid,))}
        for r in store.execute(
            "SELECT name FROM features WHERE match_id=? AND name LIKE 'entry_trade_rate:%'", (mid,)
        ):
            puuid = r["name"].split(":", 1)[1]
            assert fd.get(puuid, 0) > 0, f"entry_trade_rate for {puuid} with no entry deaths"


def test_role_balance_and_synergy_are_well_formed(store):
    for r in store.execute("SELECT name, value FROM features WHERE name LIKE 'role_balance:%'"):
        assert 1 <= r["value"] <= 4
    for r in store.execute("SELECT value FROM features WHERE name LIKE 'support_before_entry:%'"):
        assert 0.0 <= r["value"] <= 1.0
