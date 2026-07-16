# Build Plan

Ordered so that there is a demoable artifact at the end of every phase, and so the
production-key application can be submitted the moment Phase 3 lands.

---

## Phase 0 — Foundation  ✅ scaffolded

- [x] Repo structure, `.env.example`, requirements
- [x] Rate-limited client (20/1s, 100/2min, per-routing-value buckets, 429/5xx backoff)
- [x] Live/sim adapter seam
- [x] Normalized schema with `source` provenance column
- [x] Schema-faithful match simulator with causal economy model
- [ ] `python -m src.storage.init` — schema bootstrap
- [ ] Pytest: limiter honors both buckets under concurrency

## Phase 1 — Real content grounding

Everything here uses **real** dev-key data. This is the part that proves the pipeline
talks to Riot for real, not just to itself.

- [ ] `val-content-v1` fetch → `data/content.json` (agents, maps, weapons, seasons, gameModes)
- [ ] `val-status-v1` fetch → platform status
- [ ] Rewire simulator to use real UUIDs from the content cache
- [ ] Cache invalidation on `Last-Modified` / act rollover

## Phase 2 — Ingest + features

- [ ] `src/ingest/pipeline.py` — resumable ingest, writes `ingest_log`, idempotent upserts
- [ ] Normalizer: `val-match-v1` payload → 4 tables
- [ ] Feature: **economy curve** per team per round (loadout, spent, remaining, buy classification: full/half/eco/force)
- [ ] Feature: **loss-streak / bonus-round state machine**
- [ ] Feature: **plant state** and post-plant conversion rate
- [ ] Feature: **trade windows** (deaths within N seconds of a teammate death)
- [ ] Validation: assert the recovered eco→loss relationship matches the injected one
      *(this is the test that makes synthetic data defensible)*

## Phase 3 — Agents + decision trace

- [ ] `Analyst` — round classification, identifies pivotal rounds
- [ ] `Economist` — buy discipline, force-buy cost, eco round conversion
- [ ] `Watchdog` — sanity-checks other agents' claims against the store, flags unsupported conclusions
- [ ] `ReportWriter` — post-match debrief in plain language
- [ ] **Decision Trace** — every claim carries: source rows → feature → rule fired → conclusion
- [ ] Hard constraints enforced in Python *before* any LLM call (no hallucinated stats)

## Phase 4 — Surface + ship

- [ ] React dashboard: match list → round timeline → decision trace panel
- [ ] Deploy to a real public URL (Vercel/Render free tier is fine)
- [ ] README banner: data provenance stated plainly
- [ ] **Submit production key application** with the live URL
- [ ] Reply to Brian with the link

---

## Data inventory

### Available now (development key)

| Endpoint | Gives us | Used for |
|---|---|---|
| `val-content-v1` | agents, maps, weapons, acts, game modes | Grounding sim in real IDs; UI labels |
| `val-status-v1` | platform status, incidents | Health widget; proves live integration |
| `account-v1` | puuid by Riot ID | Player lookup |

### Blocked until production key

| Endpoint | Gives us | Substitute |
|---|---|---|
| `val-match-v1/matches/{id}` | full match + roundResults + per-round economy | Simulator |
| `val-match-v1/matchlists/by-puuid/{puuid}` | player match history | Simulator |
| `val-match-v1/recent-matches/by-queue/{q}` | recent competitive matches | Simulator |
| RSO OAuth | player opt-in linking | Not needed pre-approval |

### Constraints to design around

- Match history is a **bounded window**, not an archive → local store accumulates over time
- Dev key **expires every 24h** → key from env, never hardcoded; pipeline resumable mid-run
- Rate limits are **per routing value** → limiter keyed by host
- Riot policy: **no personal profiles or scouting tools** without player opt-in → aggregate by
  default, individual data only for the consenting player

---

## Open questions

- Production application "Product URL" needs a live, loadable page → Phase 4 gates the application
- Does the debrief need an LLM at all, or do deterministic rules + templates tell a stronger
  data-engineering story? (Leaning: rules produce the trace, LLM only phrases it)
