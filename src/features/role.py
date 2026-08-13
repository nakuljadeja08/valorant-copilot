"""Role-scoped features (R2a).

Every player gets the same event-backed rates, computed identically regardless of
role — role is a *tag* for grouping, not an input to the value, so the numbers stay
honest and R2b can place any player as a percentile within their own role.

Strong (event-backed, from the kill timeline):
  first_contact_rate  — involved in the round's opening kill (killer or victim)
  entry_success_rate  — took the opening kill
  first_death_rate    — took the opening death  (Sentinel signal; low is good)
  entry_trade_rate    — of the rounds they died on entry, how many were traded
  multikill_rate      — rounds with 2+ kills
  assist_rate         — mean assists per round
  survival_rate       — rounds they lived through
  utility_per_round   — mean utility casts per round (Controller/Initiator cadence)

Cross-role (team scope):
  role_balance          — distinct roles in the comp (composition)
  support_before_entry  — of the team's entry rounds, how many had a support
                          (initiator/controller) utility cast that round. ROLE-APPROX:
                          the API exposes cast *counts*, not timings, so "before the
                          entry" is a proxy, not observed precedence.

Deferred (need data the sim/API does not model): anchor_positioning and
post-plant presence (no positional snapshots), defensive hold_trade_rate (no real
attack/defend side — only the structural `attacking_team` convention). Faking
precision on those would violate the layer's honesty stance; they wait for live data.
"""

from __future__ import annotations

import sqlite3

from src.features.base import FeatureRow
from src.features.queries import (
    KillEvent,
    kills_by_round,
    player_roles,
    rounds_ordered,
    team_puuids,
)

SUPPORT_ROLES = ("initiator", "controller")

# Weak-proxy features that must carry a `role-approx` badge in report/UI: the value
# is inferred, not event-backed. Everything else here is event- or count-backed.
ROLE_APPROX = {"support_before_entry"}


def _round_refs(match_id: str, round_nums: list[int]) -> list[dict]:
    return [{"table": "rounds", "match_id": match_id, "round_num": rn} for rn in round_nums]


def _rps_ref(match_id: str, round_num: int, puuid: str) -> dict:
    return {"table": "round_player_stats", "match_id": match_id,
            "round_num": round_num, "puuid": puuid}


class RolePlayerFeatures:
    """Per-player role rates, scope='player', keyed `<feature>:<puuid>`."""

    name = "role_player"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        round_nums = [r["round_num"] for r in rounds]
        n = len(round_nums)
        if n == 0:
            return []
        kbr = kills_by_round(conn, match_id)
        roles = player_roles(conn, match_id)

        # Utility casts per (round, puuid) — for volume and lineage.
        util: dict[tuple[int, str], int] = {}
        for row in conn.execute(
            """SELECT round_num, puuid,
                      COALESCE(grenade_casts,0)+COALESCE(ability1_casts,0)+COALESCE(ability2_casts,0) u
               FROM round_player_stats WHERE match_id = ?""",
            (match_id,),
        ):
            util[(row["round_num"], row["puuid"])] = row["u"]

        rounds_refs = _round_refs(match_id, round_nums)
        rows: list[FeatureRow] = []

        def player(puuid: str) -> None:
            fc = es = fd = entry_traded = multik = survived = assists = util_total = 0
            fc_refs: list[dict] = []
            es_refs: list[dict] = []
            fd_refs: list[dict] = []
            trade_refs: list[dict] = []
            mk_refs: list[dict] = []
            death_refs: list[dict] = []
            assist_refs: list[dict] = []
            util_refs: list[dict] = []

            for rn in round_nums:
                events: list[KillEvent] = kbr.get(rn, [])
                util_total += util.get((rn, puuid), 0)
                util_refs.append(_rps_ref(match_id, rn, puuid))

                if events:
                    first = events[0]
                    if puuid in (first.killer, first.victim):
                        fc += 1
                        fc_refs.append(first.ref(match_id))
                    if first.killer == puuid:
                        es += 1
                        es_refs.append(first.ref(match_id))
                    if first.victim == puuid:
                        fd += 1
                        fd_refs.append(first.ref(match_id))
                        # Traded if the very next kill answered the entry fragger.
                        if len(events) > 1 and events[1].traded and events[1].victim == first.killer:
                            entry_traded += 1
                            trade_refs += [first.ref(match_id), events[1].ref(match_id)]
                        else:
                            trade_refs.append(first.ref(match_id))

                my_kills = [e for e in events if e.killer == puuid]
                if len(my_kills) >= 2:
                    multik += 1
                    mk_refs += [e.ref(match_id) for e in my_kills]

                my_deaths = [e for e in events if e.victim == puuid]
                if my_deaths:
                    death_refs += [e.ref(match_id) for e in my_deaths]
                else:
                    survived += 1

                for e in events:
                    if puuid in e.assistants:
                        assists += 1
                        assist_refs += e.assist_refs(match_id)

            def row(feat: str, value: float, extra_refs: list[dict]) -> None:
                rows.append(FeatureRow(
                    match_id=match_id, scope="player", name=f"{feat}:{puuid}",
                    value=value, inputs=rounds_refs + extra_refs,
                ))

            row("first_contact_rate", fc / n, fc_refs)
            row("entry_success_rate", es / n, es_refs)
            row("first_death_rate", fd / n, fd_refs)
            row("multikill_rate", multik / n, mk_refs)
            row("assist_rate", assists / n, assist_refs)
            row("survival_rate", survived / n, death_refs)
            row("utility_per_round", util_total / n, util_refs)
            # Entry-trade is only defined when the player actually died on entry;
            # emitting it otherwise would invent a denominator.
            if fd > 0:
                rows.append(FeatureRow(
                    match_id=match_id, scope="player",
                    name=f"entry_trade_rate:{puuid}", value=entry_traded / fd,
                    inputs=trade_refs,
                ))

        for puuid in roles:
            player(puuid)
        return rows


class RoleSynergyFeatures:
    """Cross-role team-scope features: composition and support→entry synergy."""

    name = "role_synergy"

    def compute(self, conn: sqlite3.Connection, match_id: str) -> list[FeatureRow]:
        rounds = rounds_ordered(conn, match_id)
        round_nums = [r["round_num"] for r in rounds]
        if not round_nums:
            return []
        kbr = kills_by_round(conn, match_id)
        roles = player_roles(conn, match_id)
        teams = team_puuids(conn, match_id)

        util: dict[tuple[int, str], int] = {}
        for row in conn.execute(
            """SELECT round_num, puuid,
                      COALESCE(grenade_casts,0)+COALESCE(ability1_casts,0)+COALESCE(ability2_casts,0) u
               FROM round_player_stats WHERE match_id = ?""",
            (match_id,),
        ):
            util[(row["round_num"], row["puuid"])] = row["u"]

        rows: list[FeatureRow] = []
        for team, members in teams.items():
            mp_refs = [{"table": "match_players", "match_id": match_id, "puuid": p}
                       for p in members]

            distinct_roles = {roles[p] for p in members if p in roles}
            rows.append(FeatureRow(
                match_id=match_id, scope="team", name=f"role_balance:{team}",
                value=float(len(distinct_roles)), inputs=mp_refs,
            ))

            supports = [p for p in members if roles.get(p) in SUPPORT_ROLES]
            entries = qualifying = 0
            refs: list[dict] = list(mp_refs)
            for rn in round_nums:
                events = kbr.get(rn, [])
                if not events or events[0].killer not in members:
                    continue  # team didn't take first contact this round
                entries += 1
                refs.append(events[0].ref(match_id))
                if any(util.get((rn, p), 0) > 0 for p in supports):
                    qualifying += 1
                refs += [_rps_ref(match_id, rn, p) for p in supports]
            # Undefined with no entries — a team that never took first contact.
            if entries > 0:
                rows.append(FeatureRow(
                    match_id=match_id, scope="team", name=f"support_before_entry:{team}",
                    value=qualifying / entries, inputs=refs,
                ))
        return rows
