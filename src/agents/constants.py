"""Rule firing thresholds.

Separated from the rules themselves for the same reason the Phase 2b thresholds
live in `src/features/constants.py`: a coach arguing with a claim should be able
to see, and change, the number that produced it without reading rule code.

These are tuned against the simulator's own distributions, not against real
competitive VALORANT. They are defensible as *internally consistent*, not as
scouting-grade thresholds -- see the provenance note in the README.
"""

from __future__ import annotations

# --- Economist -------------------------------------------------------------

# Share of rounds classified `force` above which buy discipline is called out.
FORCE_BUY_RATE = 0.30

# Number of broken buys (loss bonus should have funded a real buy, team still
# classified eco/force) that escalates from noise to a critical finding.
BROKEN_BUY_COUNT = 2

# Length of a run of back-to-back force buys that stops being a read and starts
# being a spiral. Fires on ~35% of team-matches in the sim.
CONSECUTIVE_FORCE_RUN = 3

# Cumulative spend deficit (credits) across the whole match worth reporting.
# Deliberately cumulative, not a per-round mean: the sim's per-round spend
# differential is near-symmetric and averages out to noise (median 40 credits),
# so a per-round threshold either never fires or fires on nothing meaningful.
# Summed across a match the signal survives -- 1500 credits is roughly a third of
# a team's full-buy round, and fires on ~23% of sim matches.
SPEND_DEFICIT_MATCH = 1500

# --- Deliberately not implemented ------------------------------------------
#
# "Bank misuse" -- a team walking into a round with a full-buy bank and saving
# most of it -- is a real coaching finding and was drafted as a rule. It is not
# shipped because the simulator cannot produce it: across every sim match, the
# lowest spend-to-bank ratio on a full-buy round is 0.55, so any threshold that
# would catch a genuine save catches nothing at all. Shipping it would mean a
# rule that always returns zero conclusions and never produces trace output.
# Revisit when the pipeline is reading real val-match-v1 rounds.

# --- Analyst ---------------------------------------------------------------

# Plants that fail to convert to round wins, below this rate, is a finding.
WIN_AFTER_PLANT_RATE = 0.5

# Attack rounds that reach a plant, below this rate, is a finding.
PLANT_RATE = 0.5

# Match-mean share of round kills below which a team was out-traded.
# 0.5 is parity, so this is a real deficit, not a rounding artifact.
TRADE_SHARE_MATCH = 0.45

# Kill share in the pivotal round below which the team was simply out-fought.
TRADE_SHARE_PIVOTAL = 0.35

# Loss streak entering the pivotal round that makes the economy the story.
PIVOTAL_STREAK = 2
