# Build Plan — Role-Centric Coaching Layer

Companion to `docs/PLAN.md`. This workstream adds **role-aware player coaching** on top of
the base pipeline. Each role phase (R1–R4) hooks into the base phase it extends, so nothing
here reorders the core build — it layers.

**Core design principle:** never rank across roles on the same metric. A Sentinel is not a
weak Duelist because their first-blood rate is low. Every player is scored *against
role-appropriate expectations* and *against a peer distribution of same-role players*.
Cross-role output is about **fit and synergy**, not a shared leaderboard. This principle is
the whole reason the layer exists — it's the anti-"naive stats" stance applied to players.

---

## Honest boundaries — read before building

Role value splits into what `val-match-v1` sees clearly and what it can only proxy. State
this openly in the README and UI; the labeling *is* the integrity signal.

**Strong signals (event-backed):**
- Duelist entry — first-contact and first-blood fall out of the kill timeline directly.
- Sentinel exposure — first-death rate is directly measurable (low is good, inverted metric).
- Economy discipline per role — `spent` / `loadoutValue` per player per round.
- Aim conversion — headshot / bodyshot / legshot breakdown per round.

**Weak proxies (label `role-approx`, low confidence):**
- Initiator setup value — inferred from utility casts *preceding* the team's first kill.
  We never see "recon dart revealed 2 enemies," only the cast and what happened after.
- Controller vision denial — inferred from smoke-cast cadence and survival, not from any
  "vision blocked" event. Largely invisible.
- Sentinel flank deterrence — a flank that never happened leaves no trace. Proxied via
  positioning snapshots at plant/defuse and late-round survival.

**Not available at all:** continuous movement, crosshair placement, reaction time. Role
coaching stays at the *decision* level — which is where the API is honest anyway.

**Role ≠ played style.** "Role" is assigned from the agent (`characterId`). A player *can*
off-role — a Duelist who lurks passively, a Sentinel who over-peeks. Detecting that
divergence is one of the most valuable things this layer does, but it means every claim is
"relative to what this agent's role expects," not "relative to what the player intended."

---

## R1 — Role resolution  (extends Phase 1)

**Goal:** Every player row carries a role, derived deterministically from their agent.

**Work items:**
1. Curated `AGENT_ROLE` constant: `characterId` (UUID) → `{duelist | initiator |
   controller | sentinel}`. Seed from Riot's published agent role classifications; keep it
   as a maintained constant (content-v1 does not reliably expose role). Verify the roster
   against the live agent list rather than hardcoding from memory — new agents ship often.
2. Extend `src/riot/resolve.py`: `role_of(character_id) -> Role`, plus a guard that fails
   loudly on an unknown agent UUID rather than silently defaulting.
3. Add `role` as a resolvable attribute on the player view so downstream features can scope
   by it without re-deriving.

**Demoable artifact:** `resolve.py` prints, for a sim match, each player's agent → role.

**Checklist:**
- [x] Every agent UUID in the content cache maps to exactly one role
- [x] Unknown-agent guard raises (tested with a bogus UUID)
- [x] Round-trips: agent → role for all agents in `content.json`

---

## R2 — Role-scoped features + peer baselines  (extends Phase 2)

**Goal:** Per-role derived signals with lineage, plus per-role distributions so any player
can be placed as a percentile *within their role*.

**Work items:**

*R2a. Role-scoped features* — all `scope='player'`, tagged with role, same `Feature`
protocol and `inputs_json` lineage as the base features.

- **Duelist:** `first_contact_rate`, `entry_success_rate` (won the opening duel),
  `entry_trade_rate` (when they die on entry, was it traded — measures entrying *with*
  support vs. throwing), `multikill_rate`.
- **Initiator:** `utility_precedence` (util casts before team's first kill in a round —
  `role-approx`), `assist_rate`, `setup_conversion` (rounds where their util preceded a won
  fight — `role-approx`).
- **Controller:** `smoke_cadence` (utility casts per round), `survival_rate`,
  `post_plant_presence`. All lean on cadence/survival, not vision — labeled `role-approx`.
- **Sentinel:** `first_death_rate` (inverted), `late_round_survival`, `hold_trade_rate` on
  defense, `anchor_positioning` from plant/defuse snapshots (`role-approx`).
- **Cross-role (team scope):** `role_balance` (comp composition), `support_before_entry`
  (did initiator/controller util precede Duelist entries — the synergy signal that makes
  the two-role comparison meaningful).

*R2b. Peer baselines*
- Compute per-role distributions across the sim corpus for every role feature.
- `percentile_within_role(player, feature)` → the number the UI actually shows.
- Store baselines as a versioned artifact (they shift as the sim/data changes) so a debrief
  can cite *which* baseline it was scored against — lineage extends to the comparison, not
  just the raw value.

*R2c. Role-fit / mis-role detection*
- A small rule set flagging behavior that diverges from role expectation: Duelist with
  bottom-quartile first-contact, Sentinel with top-quartile first-death, Initiator hoarding
  utility. These become the highest-value coaching claims.

*R2d. Validation*
- Role features are non-vacuous *only if the simulator generates role-differentiated
  behavior* — see R2e. Test that, in sim data, Duelists show measurably higher first-contact
  than Sentinels; if that separation is absent, the features are noise.
- Lineage integrity: every role-feature row's `inputs_json` references existing rows.
- Baseline reproducibility: same corpus → same percentiles.

*R2e. Simulator role-awareness*  ← **the biggest new work; gates everything above**
- The current sim is a causal *economy* model. To make role features mean anything, extend
  it so agents are assigned roles and behavior distributions differ by role: Duelists
  weighted toward first contact, Initiators emit utility before engagements, Sentinels have
  lower first-death and hold late, Controllers cast smokes early and survive.
- Everything role-behavioral stays labeled `sim-approx` until live data. This is fine — the
  prototype's job is to prove the *shape* of the analysis, not the numbers.

**Demoable artifact:** `python -m src.features.report --match <id> --by-role` prints, per
player: role, each role feature, its within-role percentile, the baseline version, and the
source rows.

**Checklist:**
- [x] Role features implemented for all four roles, each with lineage  *(R2a; position/side-based ones — anchor_positioning, defensive hold_trade, post-plant presence — deferred: no data)*
- [ ] Peer baselines computed and versioned; percentile lookup works
- [x] Sim shows real role separation (Duelist vs. Sentinel first-contact gap)  *(R2e)*
- [ ] Role-fit rules fire on injected off-role behavior
- [x] Everything sim-derived labeled `sim-approx` / `role-approx` as appropriate  *(R2a: `ROLE_APPROX` badge on `support_before_entry`; rest are event/count-backed)*
- [ ] README: role feature definitions + the "role-relative, not cross-role" principle
- [ ] Committed and pushed

---

## R3 — RoleCoach agent + role decision traces  (extends Phase 3)

**Goal:** Role claims phrased in plain language, every one traceable to role features →
baselines → raw rounds, and re-verified by the Watchdog exactly like the base agents.

**Work items:**

*R3a. Deterministic core*
- `src/agents/role_coach.py`: one `RoleCoach` that dispatches by role to per-role rule
  packs (keeps the agent count sane vs. four separate coaches). Each rule declares
  `(role, input features, fire condition, conclusion template, severity)`.
- Rule packs, ~3–5 rules each:
  - *Duelist:* "entered first in only N% of rounds — passive for the role"; "won entries but
    N% were un-traded — entrying without support."
  - *Initiator:* "utility preceded the team's first kill in N% of rounds"; assist-driven
    impact framing.
  - *Controller:* smoke discipline, survival, post-plant presence.
  - *Sentinel:* first-death exposure, late-round holds.
  - *Cross-role:* "Duelists took first contact but support util preceded it in only N% —
    coordinate entries" (the two-role synergy claim).
- Decision trace extended: `raw rows → role feature → within-role percentile (baseline vN)
  → rule id → conclusion`. The percentile is part of the trace, so "40th percentile among
  Duelists" is auditable back to the distribution it came from.

*R3b. LLM phrasing (thin, reuses base contract)*
- Same `ReportWriter` and numeral post-check — the model may rephrase, never invent numbers
  or percentiles. `--no-llm` still emits template text so the demo runs keyless.

*R3c. Tests*
- Golden trace: fixed sim match → identical role debrief JSON.
- Watchdog catches a corrupted role claim (percentile re-queried, mismatch → `unverified`).
- Numeral post-check rejects an invented percentile.

**Demoable artifact:** `python -m src.agents.debrief --match <id> --by-role` → per-player
role debrief with an expandable trace where every sentence links role claim → feature →
baseline → rounds.

**Checklist:**
- [ ] Rule packs for all four roles + at least one cross-role synergy rule
- [ ] Percentiles carried in the trace and re-verified by Watchdog
- [ ] `--no-llm` produces a complete role debrief
- [ ] Golden role-trace test green
- [ ] Committed and pushed

---

## R4 — Role surface  (extends Phase 4)

**Goal:** The dashboard lets a player see themselves *as their role*, with the trace intact.

**Work items:**
- Per-player **role card**: role badge, within-role percentile bars per feature, a one-line
  role-fit verdict, and the expandable decision trace under each claim.
- Toggle on the match view: "why the team lost" (base) ↔ "how each player performed for
  their role" (this layer).
- A comp/synergy strip: role balance + the support-before-entry signal, so the Duelist ↔
  Initiator relationship is visible, not buried.
- Provenance/`role-approx` badges render on the weak-proxy metrics specifically, not just
  globally — so a Riot reviewer sees exactly which claims are inference vs. event-backed.

**Checklist:**
- [ ] Role card loads with percentiles + trace on desktop and mobile
- [ ] Base ↔ role toggle works on the match view
- [ ] `role-approx` badges appear on Controller/Sentinel inference metrics
- [ ] No new key exposure; still static-bundle build
- [ ] README updated with role-layer screenshots

---

## Standing rules (role layer)

- Never rank across roles on a shared metric — percentiles are always within-role.
- Weak-proxy metrics (Initiator setup, Controller vision, Sentinel flank) carry a
  `role-approx` badge in code and UI. No fake precision on inference.
- Role is agent-derived; off-role *play* is a finding, not an error — surface it, don't
  correct the label.
- Baselines are versioned and cited in every trace that uses a percentile.

## Sequencing

R1 is ~30 min (a constant + a resolver method). R2e (simulator role-awareness) is the real
cost and gates R2–R4 — do it first inside R2, before writing the features that depend on it.
R3 reuses the base agent/Watchdog/LLM machinery, so it's mostly rules. R4 is thin by design.

**Demo-flair option (optional, not required):** split `RoleCoach` into four named coaches
(Duelist/Initiator/Controller/Sentinel). More on-theme for a Valorant audience, more code —
skip for the prototype unless time allows.
