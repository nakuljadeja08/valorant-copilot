"""R2b: per-role baselines are reproducible, honest, and correctly versioned.

The baseline is what every within-role percentile is scored against, so the load-
bearing properties get tests: same corpus -> same version and same percentiles;
percentiles behave at the endpoints; inverted metrics flip orientation; a missing
peer set returns None rather than a fabricated comparison; and the *committed*
artifact stays in sync with the code that builds it.
"""

import pytest

from src.features.baselines import (
    BASELINE_PATH,
    Baselines,
    build_from_corpus,
)


@pytest.fixture(scope="module")
def baseline():
    # A small deterministic corpus — enough peers per role, fast to build.
    return build_from_corpus([f"bl-test-{i}" for i in range(40)])


def test_build_is_reproducible(baseline):
    again = build_from_corpus([f"bl-test-{i}" for i in range(40)])
    assert again.version == baseline.version
    # And percentiles agree for a probe value.
    a = baseline.percentile_within_role("duelist", "first_contact_rate", 0.3)
    b = again.percentile_within_role("duelist", "first_contact_rate", 0.3)
    assert a.percentile == b.percentile


def test_percentile_endpoints_and_monotonicity(baseline):
    samples = baseline.distributions["duelist"]["first_contact_rate"]
    lo, hi = samples[0], samples[-1]
    assert baseline.percentile_within_role("duelist", "first_contact_rate", lo - 1).percentile == 0.0
    assert baseline.percentile_within_role("duelist", "first_contact_rate", hi + 1).percentile == 100.0
    # Non-decreasing across the range.
    prev = -1.0
    for v in (lo, (lo + hi) / 2, hi):
        p = baseline.percentile_within_role("duelist", "first_contact_rate", v).percentile
        assert p >= prev
        prev = p


def test_inverted_feature_flips_orientation(baseline):
    r = baseline.percentile_within_role("sentinel", "first_death_rate", 0.05)
    assert r.inverted is True
    assert r.oriented_percentile == pytest.approx(100.0 - r.percentile)


def test_non_inverted_feature_is_unflipped(baseline):
    r = baseline.percentile_within_role("duelist", "first_contact_rate", 0.3)
    assert r.inverted is False
    assert r.oriented_percentile == r.percentile


def test_missing_peer_set_returns_none(baseline):
    assert baseline.percentile_within_role("duelist", "no_such_feature", 0.5) is None
    assert baseline.percentile_within_role("no_such_role", "first_contact_rate", 0.5) is None


def test_save_load_round_trip(baseline, tmp_path):
    path = tmp_path / "b.json"
    baseline.save(path)
    loaded = Baselines.load(path)
    assert loaded.version == baseline.version
    assert loaded.matches == baseline.matches
    probe = baseline.percentile_within_role("duelist", "entry_success_rate", 0.2)
    assert loaded.percentile_within_role("duelist", "entry_success_rate", 0.2).percentile == probe.percentile


def test_baselines_reflect_role_separation(baseline):
    def median(role, feat):
        s = baseline.distributions[role][feat]
        return s[len(s) // 2]
    # The role separation from R2e/R2a must survive into the peer baselines.
    assert median("duelist", "first_contact_rate") > median("sentinel", "first_contact_rate")
    assert median("sentinel", "first_death_rate") < median("duelist", "first_death_rate")


def test_committed_artifact_is_in_sync_with_code():
    """The checked-in baseline must match a fresh build from the canonical corpus.

    If this fails, rebuild: `python -m src.features.baselines --build`. A stale
    artifact would score players against a distribution the code no longer produces.
    """
    if not BASELINE_PATH.exists():
        pytest.skip("no committed baseline artifact")
    committed = Baselines.load()
    fresh = build_from_corpus()
    assert committed.version == fresh.version, (
        "committed baseline is stale — rerun `python -m src.features.baselines --build`")
