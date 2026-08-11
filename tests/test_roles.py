"""R1: role resolution.

Three properties matter and each gets a test:
  - every agent in the content cache maps to exactly one role (no silent gaps)
  - an unknown agent UUID fails loudly rather than defaulting to a role
  - agent -> role round-trips for a full sim roster, case-insensitively
"""

import pytest

from src.riot.adapter import get_source
from src.riot.resolve import (
    AGENT_ROLE,
    UnknownAgentError,
    default_resolver,
    role_of,
)

ROLES = {"duelist", "initiator", "controller", "sentinel"}


def test_every_content_agent_has_exactly_one_role():
    r = default_resolver()
    unmapped = [aid for aid in r.agent_ids if aid.lower() not in
                {k.lower() for k in AGENT_ROLE}]
    assert not unmapped, f"agents missing a role: {unmapped}"
    # And every mapped value is a legal role.
    assert set(AGENT_ROLE.values()) <= ROLES


def test_roster_composition_matches_live_classification():
    # 8 duelists / 7 initiators / 7 controllers / 7 sentinels, per the live roster.
    counts = {role: sum(v == role for v in AGENT_ROLE.values()) for role in ROLES}
    assert counts == {
        "duelist": 8, "initiator": 7, "controller": 7, "sentinel": 7
    }


def test_unknown_agent_raises_loudly():
    with pytest.raises(UnknownAgentError):
        role_of("00000000-0000-0000-0000-000000000000")


def test_lookup_is_case_insensitive():
    sample = next(iter(AGENT_ROLE))
    assert role_of(sample) == role_of(sample.lower()) == role_of(sample.upper())


def test_sim_roster_round_trips_to_roles():
    src = get_source("sim")
    match = src.match(src.matchlist("hero")[0])
    resolver = default_resolver()
    for p in match["players"]:
        cid = p["characterId"]
        role = resolver.agent_role(cid)
        assert role in ROLES
        assert role == role_of(cid)  # method and function agree
