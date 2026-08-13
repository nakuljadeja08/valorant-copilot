"""R2c: role-fit / mis-role detection.

The highest-value coaching claims aren't "you had a bad game" — they're "you
played *against your role*." A Duelist who never takes first contact, a Sentinel
who dies first every round, an Initiator who never uses utility: each is only
visible once a player is scored against *same-role* peers (R2b). So every rule
here fires off a within-role percentile, never a raw value or a cross-role
comparison.

Orientation is unified through `oriented_percentile`: a flag fires when a player
sits in the bottom quartile of *goodness* for their role on a signature feature —
which for the inverted metric (first_death_rate) means a high raw value. That
keeps the rule conditions uniform and the intent legible.

These findings are deliberately kept separate from the base `Conclusion`/Watchdog
machinery: R3 wraps them into the RoleCoach agent, carries the percentile into the
decision trace, and has the Watchdog re-query it. R2c is just the detection.

Usage:
    python -m src.agents.role_fit --match <id>
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from src.agents.base import SEVERITIES
from src.agents.view import FeatureRef, FeatureView
from src.features.baselines import BASELINE_PATH, Baselines
from src.features.queries import player_roles
from src.riot.resolve import Role

# Bottom quartile of within-role goodness. A player below this on a signature
# feature is playing measurably off-role for that metric.
BOTTOM_QUARTILE = 25.0


def _ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', 23 -> '23rd'."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@dataclass(frozen=True)
class RoleFitRule:
    id: str
    role: Role
    feature: str
    severity: str
    kind: str      # 'rate' -> whole percent, 'count' -> 2dp (utility casts/round)
    template: str  # uses {v} (formatted value) and {p} (oriented percentile)
    threshold: float = BOTTOM_QUARTILE

    def render_value(self, value: float) -> str:
        return f"{round(value * 100)}%" if self.kind == "rate" else f"{value:.2f}"


# The small rule set — one or two signature checks per role. R3 expands these into
# full per-role packs; this is the detection core they build on.
ROLE_FIT_RULES: list[RoleFitRule] = [
    RoleFitRule(
        id="role_fit.duelist_passive_entry", role="duelist",
        feature="first_contact_rate", severity="warning", kind="rate",
        template=("passive for a Duelist -- took first contact in only {v} of rounds, "
                  "bottom quartile among Duelists ({p})"),
    ),
    RoleFitRule(
        id="role_fit.duelist_dry_entry", role="duelist",
        feature="entry_trade_rate", severity="warning", kind="rate",
        template=("entering without support -- only {v} of entry deaths were traded, "
                  "bottom quartile among Duelists ({p})"),
    ),
    RoleFitRule(
        id="role_fit.sentinel_overexposed", role="sentinel",
        feature="first_death_rate", severity="warning", kind="rate",
        template=("over-exposed for a Sentinel -- first to die in {v} of rounds, "
                  "worst quartile among Sentinels ({p})"),
    ),
    RoleFitRule(
        id="role_fit.initiator_utility_starved", role="initiator",
        feature="utility_per_round", severity="info", kind="count",
        template=("under-using kit for an Initiator -- {v} utility casts/round, "
                  "bottom quartile among Initiators ({p}); the team's setups run through this"),
    ),
    RoleFitRule(
        id="role_fit.controller_thin_smokes", role="controller",
        feature="utility_per_round", severity="info", kind="count",
        template=("thin map control for a Controller -- {v} utility casts/round, "
                  "bottom quartile among Controllers ({p})"),
    ),
]


@dataclass
class RoleFitFinding:
    rule_id: str
    puuid: str
    role: Role
    feature: str
    value: float
    oriented_percentile: float
    baseline_version: str
    severity: str
    text: str
    citations: list[FeatureRef] = field(default_factory=list)


def evaluate_role_fit(view: FeatureView, roles: dict[str, Role],
                      baseline: Baselines) -> list[RoleFitFinding]:
    """Flag every player who sits in the bottom quartile of their role on a rule's
    signature feature. Deterministic order: severity, then rule id, then puuid."""
    findings: list[RoleFitFinding] = []
    for puuid, role in roles.items():
        for rule in ROLE_FIT_RULES:
            if rule.role != role:
                continue
            ref = view.match_value(f"{rule.feature}:{puuid}")
            if ref is None:
                continue  # feature absent (e.g. entry_trade_rate for a player who never died on entry)
            res = baseline.percentile_within_role(role, rule.feature, ref.value)
            if res is None or res.oriented_percentile >= rule.threshold:
                continue
            p_label = f"{_ordinal(round(res.oriented_percentile))} pct"
            findings.append(RoleFitFinding(
                rule_id=rule.id, puuid=puuid, role=role, feature=rule.feature,
                value=ref.value, oriented_percentile=res.oriented_percentile,
                baseline_version=res.baseline_version, severity=rule.severity,
                text=rule.template.format(v=rule.render_value(ref.value), p=p_label),
                citations=[ref],
            ))
    return sorted(
        findings,
        key=lambda f: (SEVERITIES.index(f.severity), f.rule_id, f.puuid),
    )


def role_fit_for_match(conn, match_id: str, baseline: Baselines | None = None
                       ) -> list[RoleFitFinding]:
    """Convenience: assemble the view/roles/baseline and evaluate for one match."""
    if baseline is None:
        baseline = Baselines.load()
    return evaluate_role_fit(FeatureView(conn, match_id), player_roles(conn, match_id), baseline)


if __name__ == "__main__":
    from src.features.run import compute_for_match
    from src.riot.resolve import default_resolver
    from src.storage.init import init as init_db

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    args = ap.parse_args()

    conn = init_db()
    if not conn.execute("SELECT 1 FROM matches WHERE match_id=?", (args.match,)).fetchone():
        raise SystemExit(f"match {args.match!r} not found -- ingest it first")
    compute_for_match(conn, args.match)
    if not BASELINE_PATH.exists():
        raise SystemExit("no baseline artifact -- run `python -m src.features.baselines --build`")

    resolver = default_resolver()
    agents = {r["puuid"]: r["character_id"] for r in conn.execute(
        "SELECT puuid, character_id FROM match_players WHERE match_id=?", (args.match,))}
    findings = role_fit_for_match(conn, args.match)
    print(f"Role-fit flags - match {args.match}  ({len(findings)} found)")
    for f in findings:
        who = "you" if f.puuid == "hero" else f.puuid[:8]
        print(f"  [{f.severity:<8}] {resolver.agent_name(agents.get(f.puuid,''))} ({f.role}) "
              f"[{who}]: {f.text}")
