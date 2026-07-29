# Build Plan — VALORANT Coaching Copilot

Every phase ends with a **demoable artifact** and a **checklist**. A phase is not done
until every checklist item is checked. The production-key application gates on Phase 4.

Target cadence: Phases 2–3 are the bulk of the work. Phase 4 is deliberately thin so the
"one week" promised to Brian is achievable with a working, deployed, honest demo.

---

## Phase 0 — Foundation ✅ COMPLETE

**Goal:** A repo where the data source is swappable, rate limits are respected by
construction, and synthetic data is testable against known ground truth.

**Delivered:**
- Rate-limited client — dual sliding-window buckets (20/1s, 100/2min), keyed per routing
  value, 429 `Retry-After` handling, exponential backoff on 5xx, response cache
- `MatchSource` adapter seam — `live` | `sim` behind one config flag
- Schema-faithful simulator with causal economy model (spend differential + skill prior
  → round win probability), deterministic per match ID
- Normalized SQLite store (4 tables + ingest log), provenance column on every match
- Resumable, idempotent ingest pipeline
- 7 tests incl. `test_economy_effect_recoverable`

**Checklist:**
- [x] `pytest` green
- [x] Ingest 25 sim matches; re-run skips all 25
- [x] Repo pushed to GitHub (owner: nakuljadeja08)
- [x] `.env` gitignored; no key material in tracked files

---

## Phase 1 — Real content grounding ✅ COMPLETE

**Goal:** Every simulated match uses authentic Riot asset UUIDs. The pipeline provably
talks to the real API, not just to itself.

**Delivered:**
- `data/content.json` committed: 29 agents, 27 maps, active act, weapons/gameModes
- Simulator rewired to draw map/agent IDs from the content cache
- `src/riot/resolve.py`: UUID → display name for agents and maps

**Checklist:**
- [x] `data/content.json` contains ≥ 25 agents, ≥ 10 maps, an active act
- [x] Sim matches reference only IDs present in the content cache
- [x] `resolve.py` round-trips ID → name for every agent and map
- [x] Committed and pushed

---

## Phase 2 — Feature layer ✅ COMPLETE

**Goal:** Transform raw round rows into the derived signals every coaching claim will
cite. Features are computed by SQL + pandas, persisted, and each carries the row-level
lineage that the decision trace will later surface.

**Delivered:**
- `features` table `(match_id, round_num, scope, name, value, inputs_json)` — lineage is
  a first-class column
- `src/features/base.py` `Feature` protocol + `src/features/registry.py`
- Idempotent runner: `python -m src.features.run --match <id>` and `--all`
- Six features: buy classification (`buy_type`), economy curve (`spend`/`bank`/
  `spend_diff`/`spend_trend3`), loss-streak state machine (`loss_streak`, `broken_buy`),
  post-plant conversion (`plant_rate`, `win_after_plant`), pivotal-round detection
  (`pivotal_round`, `pivotal_round_swing`), trade efficiency (`trade_efficiency_sim_approx`,
  honestly labeled sim-approx)
- Validation suite: eco→win edge recovered within tolerance, buy-classifier force-buy
  spike on bonus rounds, lineage integrity (every `inputs_json` reference resolves to a
  real row), idempotent re-run across the full registry
- README `## Features` section: plain-language definitions for every signal

**Verified 2026-07-28:**
- 100 sim matches ingested (the sim's `matchlist_for` default window), features run in
  ~1.4s producing 28,906 rows; re-run reproduces the identical count (idempotent)
- `pytest` — 14/14 green
- `python -m src.features.report --match <id>` prints the full table with lineage

**Checklist:**
- [x] `features` table populated for 100 sim matches (the sim's default matchlist
      window) well under 60s — see note below on the 200-match target
- [x] All six features implemented with lineage
- [x] Validation suite green, including eco-recovery within tolerance
- [x] Feature runner is idempotent (re-run produces identical rows)
- [x] README section: feature definitions in plain language
- [x] Committed and pushed

**Known gap (non-blocking):** `SimSource.matchlist` (`src/sim/generator.py:49`,
`matchlist_for(puuid, n=100)`) hardcodes a 100-match window per puuid; passing
`--matches 200` to the ingest pipeline can't exceed that ceiling because the pipeline
only slices an already-capped list. Fine for one demo puuid — revisit if Phase 3/4 needs
a larger corpus (e.g. thread `n` through `--matches`, or ingest under multiple puuids).

---

## Phase 3 — Agents + decision trace  ← *next up, the differentiator*

**Goal:** Rules produce conclusions; an LLM only phrases them. Every claim in a debrief
is traceable to feature rows, which are traceable to raw rounds. No hallucinated stats
by construction.

**Work items:**

*3a. Deterministic core*
- `src/agents/rules.py`: rule registry — each rule declares `(inputs: feature names,
  fire condition, conclusion template, severity)`
- `Analyst`: pivotal-round narration rules ("lost R14 on a broken buy after 2-streak")
- `Economist`: buy-discipline rules (force-buy cost, eco conversion, bank misuse)
- `Watchdog`: cross-checks — every conclusion's cited features re-queried against the
  store; any mismatch marks the claim `unverified` and excludes it from the report
- Decision trace object: `raw rows → feature rows → rule id → conclusion`, serialized
  to JSON per match

*3b. LLM phrasing layer (thin, optional-off)*
- `ReportWriter`: takes verified conclusions + trace, produces the plain-language
  debrief; temperature low; a `--no-llm` flag emits template text so the demo runs
  without any API key
- Prompt contract: the model may rephrase, never add numbers — enforced by a
  post-check that every numeral in output exists in the trace

*3c. Tests*
- Golden-file test: fixed sim match → identical trace JSON every run
- Watchdog catches a deliberately corrupted claim (mutation test)
- Numeral post-check rejects an LLM output containing an invented stat

**Demoable artifact:** `python -m src.agents.debrief --match <id>` → debrief text +
expandable JSON trace where every sentence links to its evidence.

**Checklist:**
- [ ] ≥ 10 rules across Analyst/Economist, each with trace output
- [ ] Watchdog verification pass runs on every debrief
- [ ] `--no-llm` mode produces a complete (if dry) debrief
- [ ] Numeral post-check active when LLM is on
- [ ] Golden trace test green
- [ ] Committed and pushed

---

## Phase 4 — Surface + ship + apply

**Goal:** A public URL Riot can load. Thin by design — the dashboard sells the trace,
not itself.

**Work items:**
- React app (Vite): match list → match view (round timeline, economy chart) →
  debrief panel with expandable decision trace per claim
- Data path: pre-generate JSON bundles from the store at build time (no backend needed
  for v1 → free static hosting, zero key exposure)
- Provenance banner on every page: "Simulated data conforming to val-match-v1 schema —
  production key application pending" — the honesty is the pitch
- Deploy: Vercel or Render free tier
- Submit production application: description names endpoints (val-match, val-content,
  val-status, account-v1), the RSO opt-in plan, and the live URL
- Reply to Brian with the URL + repo link

**Checklist:**
- [ ] Live URL loads a full debrief with trace on desktop + mobile
- [ ] Provenance banner visible on every view
- [ ] No API key anywhere in the frontend bundle or repo history
- [ ] Production application submitted (screenshot saved)
- [ ] Email to Brian sent
- [ ] README updated with live URL

---

## Standing rules (all phases)

- Never commit key material; `.env` stays gitignored
- Every phase ends in a pushed commit with a message describing *why*, not just *what*
- Anything sim-approximated is labeled `sim-approx` in code and UI — no fake precision
- Aggregate by default; individual data only for the consenting player (Riot policy)

## Current status

Phase 0 ✅ → Phase 1 ✅ → Phase 2 ✅ → **Phase 3 next** (agents + decision trace) → 4.
