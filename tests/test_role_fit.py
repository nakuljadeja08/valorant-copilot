"""R2c: role-fit detection fires on off-role behavior and stays honest.

The load-bearing property (plan checklist): a rule fires when a player is injected
with off-role behavior, and does not when they play to role. Plus the guards —
findings cite lineage and the baseline version, only fire for their own role, and
come back in a deterministic order.
"""

import pytest

from src.agents.role_fit import ROLE_FIT_RULES, evaluate_role_fit
from src.agents.view import FeatureView
from src.features.baselines import build_from_corpus
from src.features.queries import player_roles
from src.features.run import compute_for_match
from src.ingest.pipeline import normalize
from src.riot.adapter import get_source
from src.storage.init import init as init_db

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


@pytest.fixture(scope="module")
def baseline():
    return build_from_corpus([f"rf-base-{i}" for i in range(40)])


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    conn = init_db(str(tmp_path_factory.mktemp("rolefit") / "r.db"))
    src = get_source("sim")
    for i in range(20):
        mid = f"rf-{i}"
        normalize(conn, src.match(mid), "sim")
        compute_for_match(conn, mid)
    return conn


def _find_player_of_role(conn, role: str) -> tuple[str, str]:
    """Return (match_id, puuid) of some player with the given role."""
    for r in conn.execute("SELECT match_id FROM matches"):
        mid = r["match_id"]
        for puuid, pr in player_roles(conn, mid).items():
            if pr == role:
                return mid, puuid
    raise AssertionError(f"no {role} found in the store")


def _set_feature(conn, mid, feature, puuid, value):
    with conn:
        conn.execute(
            "UPDATE features SET value=? WHERE match_id=? AND scope='player' AND name=?",
            (value, mid, f"{feature}:{puuid}"),
        )


def _findings(conn, mid, baseline):
    return evaluate_role_fit(FeatureView(conn, mid), player_roles(conn, mid), baseline)


def test_injected_passive_duelist_fires(store, baseline):
    mid, puuid = _find_player_of_role(store, "duelist")
    _set_feature(store, mid, "first_contact_rate", puuid, 0.0)
    fired = [f for f in _findings(store, mid, baseline)
             if f.rule_id == "role_fit.duelist_passive_entry" and f.puuid == puuid]
    assert fired, "a duelist with zero first-contact should be flagged passive"
    assert fired[0].oriented_percentile < 25.0


def test_on_role_duelist_does_not_fire_passive(store, baseline):
    mid, puuid = _find_player_of_role(store, "duelist")
    _set_feature(store, mid, "first_contact_rate", puuid, 0.9)  # elite entry
    fired = [f for f in _findings(store, mid, baseline)
             if f.rule_id == "role_fit.duelist_passive_entry" and f.puuid == puuid]
    assert not fired


def test_injected_overexposed_sentinel_fires(store, baseline):
    mid, puuid = _find_player_of_role(store, "sentinel")
    _set_feature(store, mid, "first_death_rate", puuid, 0.9)  # dies first constantly
    fired = [f for f in _findings(store, mid, baseline)
             if f.rule_id == "role_fit.sentinel_overexposed" and f.puuid == puuid]
    assert fired, "a sentinel dying first every round should be flagged over-exposed"


def test_findings_cite_lineage_and_baseline(store, baseline):
    mid, puuid = _find_player_of_role(store, "duelist")
    _set_feature(store, mid, "first_contact_rate", puuid, 0.0)
    for f in _findings(store, mid, baseline):
        assert f.baseline_version == baseline.version
        assert f.citations, "every finding must cite the feature row it fired on"
        assert f.citations[0].inputs, "the cited feature must carry raw-row lineage"


def test_rules_only_fire_for_their_own_role(store, baseline):
    role_of_rule = {r.id: r.role for r in ROLE_FIT_RULES}
    for r in store.execute("SELECT match_id FROM matches"):
        for f in _findings(store, r["match_id"], baseline):
            assert f.role == role_of_rule[f.rule_id]


def test_findings_are_deterministically_ordered(store, baseline):
    mid, puuid = _find_player_of_role(store, "sentinel")
    _set_feature(store, mid, "first_death_rate", puuid, 0.9)
    findings = _findings(store, mid, baseline)
    keys = [(SEVERITY_RANK[f.severity], f.rule_id, f.puuid) for f in findings]
    assert keys == sorted(keys)


def test_detection_is_non_vacuous_across_the_corpus(store, baseline):
    total = sum(len(_findings(store, r["match_id"], baseline))
                for r in store.execute("SELECT match_id FROM matches"))
    assert total > 0, "bottom-quartile players exist; some flags must fire"
