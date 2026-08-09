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

## Phase 3 — Agents + decision trace ✅ COMPLETE

**Goal:** Rules produce conclusions; an LLM only phrases them. Every claim in a debrief
is traceable to feature rows, which are traceable to raw rounds. No hallucinated stats
by construction.

**Delivered:**

*3a. Deterministic core*
- `src/agents/rules.py` — rule registry; each rule declares `(id, agent, severity,
  inputs, evaluate)` and returns `Conclusion`s carrying the feature rows they cite
- `src/agents/view.py` — `FeatureView`, the rules' read-only snapshot of the store
- `Analyst` (7 rules) — pivotal-round narration, post-plant conversion, plant rate,
  trade efficiency
- `Economist` (5 rules) — force-buy frequency, consecutive forces, broken buys, eco
  conversion, cumulative spend disadvantage
- `Watchdog` — re-queries every cited value straight from SQL (never the view's
  snapshot) and compares; mismatch or missing row marks the claim `unverified` and
  excludes it. A conclusion never checked (`verified is None`) is excluded too.
- `src/agents/trace.py` — `raw rows → feature rows → rule id → conclusion`, serialized
  per match with no timestamps and every collection sorted, so it is byte-stable

*3b. LLM phrasing layer (thin, optional-off)*
- `src/agents/writer.py` — `claude-opus-5` at `effort: low`; `--no-llm` emits template
  text from the same conclusions, so the demo runs with no API key and no network
- Numeral post-check: every numeral in the draft must already appear in the trace, or
  the draft is rejected and the template version is used. Enforced in code, not
  requested in the prompt.
- Any API failure, refusal, or missing SDK falls back to template text with the reason
  printed rather than failing the debrief

*3c. Tests* — 23 new (`tests/test_agents.py`), 37 total
- Golden-file trace test + a byte-identical-across-runs determinism check;
  `python -m tests.regen_golden` regenerates after an intentional rule change
- Watchdog mutation tests: corrupted value, deleted row, claim citing nothing
- Numeral post-check: faithful rephrasing accepted, invented stat rejected,
  recomputed figure (0.31 → "31 percent") rejected
- LLM path driven through a stubbed client, so it is covered without credentials
- Registry coverage test asserts every rule fires somewhere in 40 sim matches

**Verified 2026-07-28:**
- `pytest` — 37/37 green
- 30 sim matches → 232 conclusions, 0 unverified, all 12 rules firing
- `python -m src.agents.debrief --match <id> --no-llm --trace-out t.json` → 8 verified
  conclusions citing 220 raw source rows, full chain resolving end to end

**Checklist:**
- [x] ≥ 10 rules across Analyst/Economist, each with trace output (12, all firing)
- [x] Watchdog verification pass runs on every debrief
- [x] `--no-llm` mode produces a complete (if dry) debrief
- [x] Numeral post-check active when LLM is on
- [x] Golden trace test green
- [x] Committed and pushed

**Notes on two judgment calls:**
1. `round_won:{team}` was added to the Phase 2 feature registry. The rules need round
   outcomes, and letting them read `rounds.winning_team` directly would give the
   Watchdog two verification paths and the trace two shapes. One extra feature keeps
   the "every claim cites a feature row" invariant intact.
2. A drafted `economist.bank_misuse` rule is **not** shipped. The simulator never
   spends under 55% of a full-buy bank, so no threshold could make it fire — it would
   have been a rule that always returns zero conclusions. The reasoning is recorded in
   `src/agents/constants.py`; revisit against real `val-match-v1` rounds.

**Not verified against live data:** the LLM path has never made a real API call — no
`ANTHROPIC_API_KEY` is configured in this environment. Its request shape, refusal
handling, and numeral rejection are covered by stubbed tests only.

---

## Phase 4 — Surface + ship + apply  ← *in progress: app built and redesigned, not yet deployed*

**Goal:** A public URL Riot can load. Thin by design — the dashboard sells the trace,
not itself.

**Delivered (4a — the app):**

- `src/export/bundle.py` — store → static JSON. `index.json` (match list + provenance)
  plus `match/<id>.json` (meta, players, round timeline, economy series, debrief, and
  the Phase 3 trace **verbatim**, not reshaped). No timestamps, every collection
  sorted, so re-export is byte-identical and a diff always means real change.
  Defaults to template debriefs; `--llm` opts in, so the whole path needs no API key.
- React (Vite) app in `web/`: match list → match view → debrief. Every claim expands
  into its feature rows, and each feature row into the raw rows behind it.
- Round timeline (winner by **position** as well as hue, buy type printed in-band) and
  a two-series economy chart with crosshair, tooltip, keyboard nav, and a table view.
  Palette validated for CVD separation and surface contrast in light and dark; nothing
  is conveyed by color alone.
- Provenance banner rendered by the app shell rather than by each page, so no route can
  omit it. Text ships inside the bundle, with the store it describes.
- No backend and no credentials in the frontend: the app's only I/O is `fetch` against
  its own static JSON.
- Tests: 13 Python (`tests/test_export.py` — bundle agrees with the store, trace passed
  through verbatim, byte-identical re-export) + 6 jsdom render tests (`web/test/`)
  that mount both routes against the real bundles and expand every claim's trace.

**Verified 2026-08-01:**
- `pytest` — 50/50 green (37 from Phases 0–3, 13 new)
- `cd web && npm test` — 6/6 green; `npm run build` clean (212 kB JS, 66 kB gzipped)
- 12 matches exported → 97 verified claims, 0 dropped by the Watchdog; re-export
  reproduces identical bytes

**Everything in 4a above is a record of 2026-08-01, not current fact.** 4b replaced the
light-first palette, the single match-list route, and the four-stat KPI row, and grew the
export to a third shape (`agents.json`) plus a `season` block at `BUNDLE_VERSION` 2. What
carried over unchanged: the byte-stable export property, the trace passed through
verbatim, provenance rendered by the shell, and claim-level trace expansion.

**Delivered (4b — the redesign):** branch `frontend_changes`

Implements `Dashboard Redesign Options.dc.html` (a design doc with four
mockups): direction **1a Command Center** as the overview, with the agent pipeline from
**1c Agent Ops** promoted to its own route, and **1d** as the match view. Visual language
follows Riot's brand system — angular Fist-derived geometry, condensed uppercase display
type, square corners, depth from surface steps and hairlines rather than shadows.

*Data layer (`BUNDLE_VERSION` 1 → 2)*
- `build_index()` gains a `season` block — record, win rate, force-buy rate, broken buys,
  kill share, per-buy-type round conversion, critical count, per-agent finding totals.
  All derived from the already-built match bundles, so no new SQL and no second
  definition of any metric the match view also shows.
- Per-match `force_rate` (for the trend chart) and a one-line `verdict`. Verdicts are
  templated from the trace, never LLM-phrased — `export()` defaults to no-LLM and
  re-export has to stay byte-identical. Counts come from the bundle's own rows, never
  from regexing numerals out of claim text, which would couple them to rule prose.
- `win_prob_proxy:{team}` emitted per round. `pivotal_round.py` already built this series
  and discarded all but the argmax. Both sides are emitted so no consumer has to know the
  feature's reference team is `sorted(teams)[0]`.
- `trade_efficiency_sim_approx` reaches JSON for the first time, keyed
  `kill_share_sim_approx` so the caveat cannot be dropped downstream.
- `hero_puuid` persisted through ingest, giving "your record" a referent. Guarded: a
  puuid absent from the roster is stored as NULL rather than attributing a record to a
  side at random. `init()` gained a migration step, since `schema.sql` is
  `CREATE TABLE IF NOT EXISTS` and a new column was invisible to existing stores.
- New `agents.json`. All 93 verified claims are ~36KB of text, three times the whole
  index, and `index.json` is fetched by every route — splitting them dropped the index
  from 12.9KB to 10.6KB.

*Frontend*
- `styles.css` (717 lines, light-first) split into `src/styles/{tokens,fonts,base,chrome,
  charts,views}.css` behind a barrel import. Vite inlines them, so it is still one
  stylesheet at runtime and adds no dependency.
- **Dark is now the base**, light is derived, and a header toggle persists the choice to
  `localStorage`. An inline script in `index.html` applies it pre-paint; only `light`
  needs setting, so a visitor with no stored preference paints correctly even if the
  script never runs. Light preserves the surface ladder's *ordering* rather than
  inverting it, and leans harder on hairlines because the compressed range weakens the
  steps.
- Two reds: `#FF4655` (Riot's official VALORANT red) for identity only — logo, active
  nav, focus ring — because it measures 3.24:1 on the light card and cannot carry data;
  a per-mode red for data ink. Blue/Red pass contrast and CVD separation in both modes.
  The four-colour status set does **not** pass as a categorical palette and is never used
  as one: status always ships with a text label (`CRIT`/`WARN`/`PASS`) or a border
  position.
- Four routes: `#/` overview, `#/agents`, `#/matches`, `#/match/<id>`. A bare fragment
  falls back to the overview; a match keeps Matches lit with a back link to it.
- Fonts self-hosted (Barlow Condensed / Barlow / JetBrains Mono, all OFL — the stack the
  mockup itself used). Licensed Tungsten/DIN Next drop into a gitignored
  `web/src/fonts/licensed/` and take over via the token stacks. They are **not** committed:
  this repo is public and that would be redistribution most EULAs prohibit.

*Honesty decisions made during the redesign*
- The 1d hero chart is labelled **"Momentum index"**, not "Win probability". The feature
  states outright that the value "is not a calibrated probability". The axis reads
  0.0/0.5/1.0 rather than percentages — a percent sign is what makes a reader treat a
  number as a probability — and the disclaimer ships in the bundle so page copy cannot
  drift from the feature. A test asserts all of it.
- The mockup's headline record of **7–5 was Blue's**, not the focal player's. With
  `hero_puuid` persisted the honest figure is **6–6**, and that is what ships.
- Fixed a latent bug: `SimMatchSource.match()` dropped the puuid on the way to
  `build_match()`, so `--puuid X` produced rosters that never contained X.

**Verified 2026-08-09:**
- `pytest` — 67/67 green (50 from 4a, 17 new)
- `cd web && npm test` — 17/17 green; `npm run build` clean (238 kB JS, 72 kB gzipped)
- **Eyeballed in real Chrome** (headless, 1360px) — all four routes in both themes, no
  console errors beyond a pre-existing `favicon.ico` 404. This closes 4a's "not verified
  in a real browser" gap for desktop. **Mobile still not eyeballed**; the CSS has
  breakpoints at 900px and 720px but they have not been looked at on a device.

**Bundle/store drift found (pre-existing, not introduced here):** the Phase-4a bundles
committed on 2026-08-01 report 97 verified claims across a match set that does not match
the local `data/copilot.db` — the store already contained different matches before any 4b
work began. Re-exporting from the current store yields 12 matches / 93 verified claims,
which is what is committed now. Worth a CI check that re-runs the export and diffs against
the tree, so the committed bundles cannot silently drift from the store again.

**Not done — these need the account holder:**
- Deploy to Vercel/Render (`vercel.json` is in place; needs a `vercel` login + link)
- Submit the production application: endpoints named (val-match, val-content,
  val-status, account-v1), the RSO opt-in plan, and the live URL
- Reply to Brian with the URL + repo link
- Merge `frontend_changes` (4 commits, unpushed) into `main`

**Checklist:**
- [x] Match list → match view → debrief, with an expandable trace per claim
- [x] Bundles pre-generated at build time; no backend, no key in the frontend
- [x] Provenance banner on every view (rendered by the shell, not per page)
- [x] Export is idempotent and byte-stable; covered by tests
- [x] Redesign per `Dashboard Redesign Options.dc.html` (1a + 1c pipeline + 1d)
- [x] Light/dark theme toggle, persisted, applied before first paint
- [x] Fonts self-hosted — no third-party request at runtime, enforced by a test
- [x] Every chart has a table-view twin — asserted structurally, so it stays true as
      charts are added
- [x] Desktop rendering eyeballed in a real browser (all four routes, both themes)
- [ ] Mobile rendering eyeballed on a device
- [ ] Live URL loads a full debrief with trace on desktop + mobile
- [x] No API key anywhere in the frontend bundle or repo history — `web/dist` scanned
      clean; `git log --all -S RGAPI-` finds only the `.env.example` placeholder, and
      `.env` has never been tracked
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

Phase 0 ✅ → Phase 1 ✅ → Phase 2 ✅ → Phase 3 ✅ → **Phase 4 in progress**: the app, the
export path, and the Riot-flavoured redesign (4b) are built, tested, and eyeballed on
desktop. Deploying, applying, and emailing Brian are the remaining steps and all three
need the account holder.

Live on `frontend_changes`, 4 commits, unpushed:

| Commit | Subject |
|---|---|
| `a2fa330` | data: season aggregates, verdicts, momentum proxy series, `hero_puuid` |
| `34a5eb0` | web: Riot-flavoured redesign — Command Center, 1d match view, theme toggle |
| `ce6be05` | web: make the header nav actually navigate |
| `91fca1d` | web: split Overview, Agents and Matches into real routes |

Tests: **67 Python + 17 web**, all green.

Open items that do not need the account holder:
- Mobile layout has never been looked at (breakpoints exist at 900px and 720px)
- A CI check that re-runs `python -m src.export.bundle` and diffs against the tree,
  so committed bundles cannot drift from the store (see the drift note in 4b)
- `favicon.ico` 404s; the app has never had one
