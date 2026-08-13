"""R3: the RoleCoach agent — role claims phrased, traced, and Watchdog-verified.

One agent that dispatches by role to per-role rule packs. It does not re-derive
the mis-role thresholds — those live in R2c (`role_fit`) and are wrapped here — it
adds the other half: the *strengths* (top-quartile play) and the one cross-role
synergy claim, so a debrief reads as coaching, not just a list of faults.

Every player claim carries the within-role percentile and the baseline version, so
the decision trace is the full chain — raw rows -> role feature -> within-role
percentile (baseline vN) -> rule id -> conclusion — and the Watchdog can re-query
the percentile exactly as it re-reads any cited value. The cross-role claim is
team-scoped (no per-role peer set), so it fires on an absolute threshold instead.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.agents.base import SEVERITIES, Conclusion
from src.agents.role_fit import _ordinal, evaluate_role_fit
from src.agents.view import FeatureView
from src.features.baselines import Baselines
from src.features.queries import player_roles
from src.features.role import ROLE_APPROX
from src.riot.resolve import Role, default_resolver

AGENT = "RoleCoach"
TOP_QUARTILE = 75.0


@dataclass(frozen=True)
class StrengthRule:
    """A per-role positive claim: fires when a player is top-quartile within role."""

    id: str
    role: Role
    feature: str
    kind: str      # 'rate' -> whole percent, 'count' -> 2dp
    template: str  # {v} formatted value, {p} percentile
    threshold: float = TOP_QUARTILE

    def render_value(self, value: float) -> str:
        return f"{round(value * 100)}%" if self.kind == "rate" else f"{value:.2f}"


# Strengths — one or two per role, mirroring the R2c faults on the good side.
STRENGTH_RULES: list[StrengthRule] = [
    StrengthRule("role_coach.duelist_entry_leader", "duelist", "first_contact_rate",
                 "rate", "leading entries -- first contact in {v} of rounds, {p} among Duelists"),
    StrengthRule("role_coach.duelist_trade_secure", "duelist", "entry_trade_rate",
                 "rate", "entering with support -- {v} of entry deaths traded, {p} among Duelists"),
    StrengthRule("role_coach.initiator_assist_engine", "initiator", "assist_rate",
                 "rate", "driving setups -- assisted on {v} of rounds, {p} among Initiators"),
    StrengthRule("role_coach.controller_map_control", "controller", "utility_per_round",
                 "count", "strong map control -- {v} utility casts/round, {p} among Controllers"),
    StrengthRule("role_coach.sentinel_anchor", "sentinel", "survival_rate",
                 "rate", "anchoring the site -- survived {v} of rounds, {p} among Sentinels"),
    StrengthRule("role_coach.sentinel_solid_hold", "sentinel", "first_death_rate",
                 "rate", "hard to dislodge -- first to die in only {v} of rounds, {p} among Sentinels"),
]

# Cross-role synergy: team-scoped, so it can't use a within-role percentile — it
# fires on an absolute rate instead. role-approx (utility timing is inferred).
SUPPORT_BEFORE_ENTRY_FLOOR = 0.5


def _subject(resolver, agents: dict[str, str], puuid: str) -> str:
    name = resolver.agent_name(agents.get(puuid, ""))
    return f"{name} (you)" if puuid == "hero" else name


def analyze_roles(conn: sqlite3.Connection, match_id: str,
                  baseline: Baselines) -> list[Conclusion]:
    """Every role claim for a match: mis-role faults (R2c) + strengths + synergy."""
    view = FeatureView(conn, match_id)
    roles = player_roles(conn, match_id)
    resolver = default_resolver()
    agents = {r["puuid"]: r["character_id"] for r in conn.execute(
        "SELECT puuid, character_id FROM match_players WHERE match_id = ?", (match_id,))}

    out: list[Conclusion] = []

    # 1. Mis-role faults — reuse R2c detection, wrap each finding as a Conclusion.
    for f in evaluate_role_fit(view, roles, baseline):
        out.append(Conclusion(
            rule_id=f.rule_id, agent=AGENT, severity=f.severity,
            text=f"{_subject(resolver, agents, f.puuid)}: {f.text}",
            citations=list(f.citations),
            percentile=f.oriented_percentile, baseline_version=f.baseline_version,
        ))

    # 2. Strengths — top-quartile play, per role.
    for puuid, role in roles.items():
        for rule in STRENGTH_RULES:
            if rule.role != role:
                continue
            ref = view.match_value(f"{rule.feature}:{puuid}")
            if ref is None:
                continue
            res = baseline.percentile_within_role(role, rule.feature, ref.value)
            if res is None or res.oriented_percentile <= rule.threshold:
                continue
            p_label = f"{_ordinal(round(res.oriented_percentile))} pct"
            out.append(Conclusion(
                rule_id=rule.id, agent=AGENT, severity="info",
                text=f"{_subject(resolver, agents, puuid)}: "
                     f"{rule.template.format(v=rule.render_value(ref.value), p=p_label)}",
                citations=[ref],
                percentile=res.oriented_percentile, baseline_version=res.baseline_version,
            ))

    # 3. Cross-role synergy — team-scoped absolute threshold.
    for team in view.teams:
        ref = view.match_value(f"support_before_entry:{team}")
        if ref is None or ref.value >= SUPPORT_BEFORE_ENTRY_FLOOR:
            continue
        approx = " (role-approx)" if "support_before_entry" in ROLE_APPROX else ""
        out.append(Conclusion(
            rule_id="role_coach.cold_entries", agent=AGENT, severity="warning",
            text=(f"{team}: entries going in cold -- support utility preceded first contact "
                  f"in only {round(ref.value * 100)}% of {team}'s entry rounds{approx}; "
                  f"coordinate entries behind Initiator/Controller util."),
            citations=[ref],
        ))

    return sorted(out, key=lambda c: (SEVERITIES.index(c.severity), c.rule_id, c.text))
