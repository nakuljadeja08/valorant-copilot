"""Shared thresholds and conventions used across Phase 2b features.

Buy-classification thresholds are tuned against the sim's actual team-loadout
distribution (see docs/README feature section for the empirical percentiles
used to place the cut points), not against real-match economy figures, since
the simulator's credit trajectory (800 start / 9000 cap / escalating loss
bonus) is modeled per-team rather than per-player.
"""

from __future__ import annotations

# Team-round bank (sum of the 5 players' loadout_value, i.e. credits available
# before this round's buy) -> buy classification. Ordered low to high.
BUY_THRESHOLDS = [
    (2000, "eco"),
    (3400, "force"),
    (4200, "half"),
    (float("inf"), "full"),
]

# Stable numeric encoding for the categorical buy type, since FeatureRow.value
# is REAL. The report/agents layer decodes via BUY_CODES.
BUY_CODES = {"eco": 0.0, "force": 1.0, "half": 2.0, "full": 3.0}
BUY_NAMES = {v: k for k, v in BUY_CODES.items()}


def classify_buy(team_loadout: float) -> str:
    for threshold, label in BUY_THRESHOLDS:
        if team_loadout < threshold:
            return label
    return "full"  # unreachable: last threshold is inf


# Side convention: the sim does not record which team attacked/defended a given
# round (no bomb-planter identity, no per-round side field). Real competitive
# VALORANT swaps sides after 12 rounds with no overtime side-swap modeled here
# (the sim caps at 24 rounds / first-to-13, matching regulation length). We
# impose a deterministic convention -- Red attacks rounds 0-11, Blue attacks
# 12+ -- so post-plant features have a side to key off. This is a structural
# assumption, not a fidelity approximation, and is documented here as the
# single place it's encoded.
FIRST_HALF_ROUNDS = 12


def attacking_team(round_num: int) -> str:
    return "Red" if round_num < FIRST_HALF_ROUNDS else "Blue"


def other_team(team_id: str) -> str:
    return "Blue" if team_id == "Red" else "Red"
