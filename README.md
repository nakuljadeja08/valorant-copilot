# VALORANT Coaching Copilot

A multi-agent, explainability-first coaching pipeline for VALORANT competitive matches.

Instead of surfacing raw stats, the pipeline reconstructs **why a round was lost** — economy
deficit, utility spent too early, a site take that never had the numbers — and emits a
**decision trace** showing every step that led to each conclusion.

---

## Data status: simulated, pending production key

`val-match-v1` is not accessible with development or personal API keys. Per Riot's VALORANT
API launch policy, match data requires a **production key**, and RSO (player opt-in) requires
a production key as well.

This repo therefore ships a **match simulator** (`src/sim/`) that emits payloads conforming to
the documented `val-match-v1` response schema. Nothing here is scraped, and no unofficial or
community API is used.

The consequence is an intentional design constraint:

> **Every module downstream of `src/riot/adapter.py` is agnostic to whether a match came from
> the live API or the simulator.** Flipping `RIOT_DATA_SOURCE=live` in `.env` swaps the source
> with no other code change.

Live endpoints that *do* work on a development key are used for real: `val-content-v1`
(agents, maps, weapons) and `val-status-v1`. Simulated matches are grounded in those real
asset IDs, so the schema, the map pool, and the agent roster are all authentic.

## Architecture

```
                 ┌───────────────────┐
  val-content-v1 │  Content Cache    │  real, dev-key
  val-status-v1  │  (agents/maps)    │
                 └─────────┬─────────┘
                           │ grounds
                 ┌─────────▼─────────┐
   live ──┐      │   Match Adapter   │  single seam: live | sim
   sim  ──┘      └─────────┬─────────┘
                           │ raw val-match-v1 payloads
                 ┌─────────▼─────────┐
                 │  Ingest Pipeline  │  rate-limited, cached, resumable
                 └─────────┬─────────┘
                           │
                 ┌─────────▼─────────┐
                 │  Feature Store    │  economy curves, util timing, trades
                 └─────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌──────▼──────┐   ┌───────▼──────┐
   │ Analyst │      │  Economist  │   │   Watchdog   │
   └────┬────┘      └──────┬──────┘   └───────┬──────┘
        └──────────────────┼──────────────────┘
                    ┌──────▼──────┐
                    │Report Writer│  → debrief + decision trace
                    └─────────────┘
```

## Quickstart

```bash
cp .env.example .env          # add your dev key for content endpoints
pip install -r requirements.txt
python -m src.storage.init    # create schema
python -m src.riot.content    # pull real agents/maps/weapons
python -m src.ingest.pipeline --source sim --matches 200
python -m src.features.run --all
python -m src.features.report --match <id>   # print every feature + its source rows
python -m src.agents.debrief --match <id> --no-llm    # debrief, no API key needed
python -m src.export.bundle --matches 12              # static JSON for the dashboard
```

Then, for the dashboard:

```bash
cd web && npm install && npm run dev     # http://localhost:5173
npm test                                 # renders both routes against the real bundles
```

## Features

Every derived signal lives in the `features` table as `(match_id, round_num, scope, name,
value, inputs_json)`. `inputs_json` is lineage — the exact raw rows a value was computed
from — so later coaching claims can point back to evidence instead of asserting a number.
Run `python -m src.features.report --match <id>` to see this end to end.

| Feature | What it means |
|---|---|
| `buy_type:{team}` | eco / force / half / full for a team's round, from the reconstructed team bank against fixed thresholds (`src/features/constants.py`, tuned against the sim's own credit distribution) |
| `spend:{team}`, `bank:{team}` | Per-round team spend and pre-buy bank |
| `spend_diff` | This round's spend differential (one team minus the other) |
| `spend_trend3:{team}` | Rolling 3-round mean of a team's spend — smooths round-to-round noise |
| `loss_streak:{team}` | Consecutive rounds lost entering this round, reconstructed from `rounds.winning_team` |
| `broken_buy:{team}` | Flags a round where the loss-bonus escalation should have funded a real buy (streak at the cap) but the team still classifies as eco/force |
| `plant_rate:{team}`, `win_after_plant:{team}` | Match-scoped: how often a team's attack rounds end in a plant, and how often a plant converts to a win. Side (attack/defense) is a documented convention, not data the sim tracks per round — see `attacking_team()` in `constants.py` |
| `pivotal_round`, `pivotal_round_swing` | The round with the largest swing in a lightweight win-probability proxy built from score state + economy differential — the round the Analyst will narrate |
| `trade_efficiency_sim_approx:{team}` | **sim-approx.** A team's share of a round's total kills, standing in for real trade-window detection (kill answered within N seconds of a teammate's death) — the sim has no death timestamps to compute the real thing |

## Agents and the decision trace

Rules produce conclusions; the LLM only phrases them. No claim in a debrief can
contain a number that isn't already in the store.

```
raw rows  ->  feature rows  ->  rule id  ->  conclusion  ->  debrief
   ^              ^                ^             ^
   |              |                |             └─ Watchdog re-queries every cited
   |              |                |                value before it reaches a report
   |              |                └─ 12 rules across Analyst / Economist
   |              └─ inputs_json lineage (Phase 2)
   └─ rounds / round_player_stats
```

Run `python -m src.agents.debrief --match <id> --trace-out trace.json` to see it end
to end: the debrief text, then a JSON trace where every sentence resolves to the
feature rows behind it and every feature row to the raw rounds behind *it*.

**The Watchdog** re-reads each cited value straight from SQLite and compares it to
what the rule saw. A mismatch — a recomputed feature, a changed threshold, a
corrupted row — marks the claim `unverified` and drops it from the report instead
of printing a stale number. `tests/test_agents.py` mutates the store to prove it
fires.

**The LLM layer is thin and optional.** `--no-llm` emits template text from the same
conclusions, so the demo runs with no API key and no network. With the LLM on, the
model may rephrase but never add a number: every numeral in its draft must already
appear in the trace, or the draft is rejected and the template version is used.
That's a post-check in code, not an instruction in the prompt.

| Rule | Fires when |
|---|---|
| `analyst.pivotal_round` | Always — names the round with the largest win-probability-proxy swing |
| `analyst.pivotal_broken_buy` | The team that lost the pivotal round did so on a broken buy |
| `analyst.pivotal_streak` | The pivotal round was entered on a 2+ round loss streak |
| `analyst.pivotal_trade_collapse` | Loser of the pivotal round took under 35% of its kills (`sim-approx`) |
| `analyst.post_plant_conversion` | Under half a team's plants converted to round wins |
| `analyst.plant_rate` | A team reached a plant in under half its attack rounds |
| `analyst.trade_efficiency` | Match-mean kill share under 45% against a 50% even split (`sim-approx`) |
| `economist.force_buy_frequency` | Over 30% of rounds classified `force` |
| `economist.consecutive_force` | Three or more force buys in consecutive rounds |
| `economist.broken_buy_count` | Two or more broken buys in the match |
| `economist.eco_conversion` | Always, per team — how many eco rounds were stolen |
| `economist.spend_disadvantage` | 1500+ credit cumulative spend deficit across the match |

Thresholds live in `src/agents/constants.py` and are calibrated against the
simulator's own distributions — internally consistent, not scouting-grade. One
drafted rule (bank misuse) is deliberately **not** shipped: the simulator never
spends under 55% of a full-buy bank, so it could never fire. That reasoning is
recorded in `constants.py` rather than shipped as a dead rule.

## Role coaching layer

A second workstream layered on the base pipeline (`ROLE_PLAN.md`): scoring each
player *as their role*. The whole reason it exists is one principle —

> **Role-relative, never cross-role.** A Sentinel is not a weak Duelist because
> their first-blood rate is low. Every player is scored against *role-appropriate
> expectations* and a *peer distribution of same-role players*. There is no shared
> leaderboard; cross-role output is about fit and synergy, not ranking.

Role is assigned deterministically from the agent (`src/riot/resolve.py`, `role_of`),
and an unknown agent raises rather than defaulting — a new agent shipping without a
role entry fails loudly instead of being coached as the wrong role. Off-role *play*
(a Duelist who lurks, a Sentinel who over-peeks) is a **finding**, not a mislabel —
surfacing that divergence is the most valuable thing this layer does.

**Honest boundaries.** Role value splits into what the API sees clearly and what it
can only proxy, and the labeling *is* the integrity signal:

- **Event-backed (strong)** — from the kill timeline (`round_kills`): first contact,
  first death, entry trades, multikills, assists, survival.
- **`role-approx` (weak proxy)** — `support_before_entry` infers "support set up the
  entry" from utility *cast counts*, because the API exposes counts, not timings. It
  carries a `role-approx` badge in code (`ROLE_APPROX`) and in the report.
- **Deferred (no data)** — anchor positioning, defensive hold trades, post-plant
  presence need positional or real attack/defend data the sim doesn't model. They're
  left unbuilt rather than faked.

| Role feature (`scope='player'`, `name:{puuid}`) | What it means |
|---|---|
| `first_contact_rate` | Involved in the round's opening kill (killer or victim) |
| `entry_success_rate` | Took the opening kill |
| `first_death_rate` | Took the opening death — **inverted** (low is good); the Sentinel signal |
| `entry_trade_rate` | Of the rounds they died on entry, how many were traded (entering *with* support vs. throwing). Emitted only when they actually died on entry |
| `multikill_rate` | Rounds with 2+ kills |
| `assist_rate` | Mean assists per round |
| `survival_rate` | Rounds they lived through |
| `utility_per_round` | Mean utility casts per round — Controller/Initiator cadence |
| `role_balance:{team}` | Distinct roles in the comp (composition) |
| `support_before_entry:{team}` | **`role-approx`.** Of the team's entry rounds, how many had a support-role utility cast that round |

**Peer baselines are a versioned artifact.** `src/features/baselines.py` builds
per-`(role, feature)` distributions across a deterministic corpus and writes
`data/baselines/role_baselines.json`. The version is a content hash of the
distributions themselves — same corpus in, same version out — so a debrief can cite
*which* baseline a percentile was scored against. `percentile_within_role()` returns
the number the UI shows; inverted metrics flip orientation so "higher reads better"
uniformly; a role/feature with no peers returns `None` rather than a fabricated rank.

**Role-fit detection** (`src/agents/role_fit.py`) is where the highest-value claims
come from: a player in the bottom quartile of *their role* on a signature feature is
flagged — a passive Duelist, an over-exposed Sentinel, a utility-starved Initiator.
Every flag cites the feature row (raw-row lineage) and the baseline version, setting
up the RoleCoach agent's Watchdog-verified trace.

```bash
python -m src.features.baselines --build          # (re)build the versioned baseline
python -m src.features.report --match <id> --by-role   # per-player role card + percentiles + flags
python -m src.agents.role_fit --match <id>        # just the mis-role flags
```

## Dashboard

**Live URL:** _not yet deployed — see `docs/TASKS.md` Phase 4._

The dashboard exists to make the trace legible, not to be a product. Match list →
match view (round timeline, economy chart, scoreboard) → debrief, where every claim
expands into the feature rows it cites and the raw rows each of those was computed
from. The same chain the CLI prints, with a disclosure triangle on it.

The match view carries a **base ↔ role toggle** (R4): _"Why the team lost"_ (the
economy/analyst debrief) ↔ _"How each player performed for their role."_ The role
lens shows a per-player card — role badge, a within-role percentile bar per feature,
and a one-line role-fit verdict — plus a composition/synergy strip and the role
debrief, where each claim expands into the same trace, now with the within-role
percentile and the baseline version it was scored against. Inferred metrics
(support-before-entry) carry a `role-approx` badge exactly where they appear, so a
reviewer sees which numbers are event-backed and which are proxies. Percentiles are
oriented — higher always reads better — so the one inverted metric (first death)
points the same way as the rest.

**There is no backend.** `python -m src.export.bundle` pre-generates static JSON from
the store — `web/public/data/index.json` plus one file per match — and the React app
fetches only those. A static host cannot leak an API key it was never given, and the
frontend has no code path that talks to Riot. The bundles are committed because
`data/*.db` is gitignored, so a clone (or a deploy build) has no store to regenerate
them from.

Bundles are byte-stable: no timestamps, every collection sorted. Re-exporting an
unchanged store produces identical files, so a diff in `web/public/data` always means
the data or the rules actually changed. `tests/test_export.py` pins that, along with
the bundle agreeing with the store and the trace being passed through verbatim rather
than reshaped for the UI.

Export defaults to template debriefs (`--llm` opts in), so the whole pipeline —
ingest through deployed page — runs with no API key.

```bash
python -m src.export.bundle --matches 12   # -> web/public/data
cd web && npm install && npm run build     # -> web/dist, deployable as-is
```

Deploy: `vercel.json` at the repo root builds `web/` and serves `web/dist` as a static
site. Any static host works — on Render, a Static Site with build command
`npm install --prefix web && npm run build --prefix web` and publish directory
`web/dist`. Routing is hash-based (`#/match/<id>`), so no rewrite rules are needed.

Charts use a palette validated for colorblind separation and surface contrast in both
light and dark. Round outcomes encode the winner by position as well as hue, and every
chart has a table view, so nothing is conveyed by color alone.

## Layout

| Path | Purpose |
|---|---|
| `src/riot/client.py` | Rate-limited HTTP client (20/1s, 100/2min, per-routing-value) |
| `src/riot/content.py` | `val-content-v1` fetch + cache |
| `src/riot/adapter.py` | The live/sim seam |
| `src/sim/generator.py` | Schema-faithful match simulator |
| `src/ingest/pipeline.py` | Resumable ingest into local store |
| `src/features/` | Round-level feature extraction |
| `src/features/role.py` | Role-scoped features (R2a) |
| `src/features/baselines.py` | Versioned per-role peer baselines + within-role percentiles (R2b) |
| `src/agents/role_fit.py` | Mis-role detection on within-role percentiles (R2c) |
| `src/agents/rules.py` | Rule registry — the deterministic core |
| `src/agents/watchdog.py` | Re-verifies every cited value against the store |
| `src/agents/trace.py` | Decision trace serialization |
| `src/agents/writer.py` | LLM phrasing layer + numeral post-check |
| `src/agents/debrief.py` | `python -m src.agents.debrief --match <id>` |
| `src/export/bundle.py` | Store → static JSON bundles for the dashboard |
| `web/` | React (Vite) dashboard — reads only the generated bundles |
| `web/public/data/` | Generated bundles, committed (the store itself is gitignored) |
| `src/storage/schema.sql` | Normalized match store |
| `docs/TASKS.md` | Build plan |

## License

MIT
