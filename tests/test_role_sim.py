"""R2e: the simulator must generate role-*differentiated* behaviour.

Role features (first-contact, first-death, setup) are only non-vacuous if the sim
actually separates roles. These tests are the gate the plan calls for: in sim data
duelists must take first contact measurably more than sentinels, sentinels must
take the opening death measurably *less* (their inverted strong signal), and the
support roles must out-cast the entry roles on utility. If any separation collapses,
the downstream role features are noise and this fails loudly.
"""

from collections import defaultdict

from src.sim.generator import MatchGenerator, _role_of

ROLES = ("duelist", "initiator", "controller", "sentinel")


def _aggregate(n_matches: int = 160, seed: int = 3):
    """Per-role rates across many sim rounds: first-contact, first-death, utility."""
    g = MatchGenerator(seed=seed)
    played = defaultdict(int)
    first_contact = defaultdict(int)
    first_death = defaultdict(int)
    multikill = defaultdict(int)
    util_casts = defaultdict(float)

    for i in range(n_matches):
        m = g.build_match(f"rolesep-{i}")
        role = {p["puuid"]: _role_of(p["characterId"]) for p in m["players"]}
        for r in m["roundResults"]:
            events = []
            for ps in r["playerStats"]:
                played[role[ps["puuid"]]] += 1
                if len(ps["kills"]) >= 2:
                    multikill[role[ps["puuid"]]] += 1
                a = ps["ability"]
                util_casts[role[ps["puuid"]]] += (
                    a["grenadeCasts"] + a["ability1Casts"] + a["ability2Casts"]
                )
                for k in ps["kills"]:
                    events.append((k["timeSinceRoundStartMillis"], k["killer"], k["victim"]))
            if not events:
                continue
            events.sort()
            _, first_killer, first_victim = events[0]
            first_contact[role[first_killer]] += 1
            first_contact[role[first_victim]] += 1
            first_death[role[first_victim]] += 1

    def rate(counter):
        return {r: counter[r] / played[r] for r in ROLES}

    return {
        "first_contact": rate(first_contact),
        "first_death": rate(first_death),
        "multikill": rate(multikill),
        "utility": rate(util_casts),
    }


def test_duelists_take_first_contact_more_than_sentinels():
    rates = _aggregate()["first_contact"]
    # A comfortable margin, not a hairline — the separation is meant to be obvious.
    assert rates["duelist"] > rates["sentinel"] * 1.5
    # Monotonic-ish: entry roles above anchor roles.
    assert rates["duelist"] > rates["initiator"] > rates["sentinel"]


def test_sentinels_take_the_opening_death_least():
    rates = _aggregate()["first_death"]
    assert rates["sentinel"] < rates["duelist"]
    assert rates["sentinel"] == min(rates.values())


def test_support_roles_out_cast_entry_roles_on_utility():
    rates = _aggregate()["utility"]
    assert rates["initiator"] > rates["duelist"]
    assert rates["controller"] > rates["duelist"]


def test_duelists_multikill_most():
    rates = _aggregate()["multikill"]
    assert rates["duelist"] == max(rates.values())


def test_kill_timeline_is_emitted_and_schema_faithful():
    g = MatchGenerator(seed=42)
    m = g.build_match("timeline-shape")
    seen_kill = False
    for r in m["roundResults"]:
        for ps in r["playerStats"]:
            assert "ability" in ps and "kills" in ps
            for k in ps["kills"]:
                seen_kill = True
                assert k["killer"] == ps["puuid"]  # nested under the killer
                assert {"killer", "victim", "assistants",
                        "timeSinceRoundStartMillis"} <= set(k)
    assert seen_kill, "no kill events emitted"
