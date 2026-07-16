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
```

## Layout

| Path | Purpose |
|---|---|
| `src/riot/client.py` | Rate-limited HTTP client (20/1s, 100/2min, per-routing-value) |
| `src/riot/content.py` | `val-content-v1` fetch + cache |
| `src/riot/adapter.py` | The live/sim seam |
| `src/sim/generator.py` | Schema-faithful match simulator |
| `src/ingest/pipeline.py` | Resumable ingest into local store |
| `src/features/` | Round-level feature extraction |
| `src/agents/` | Analyst / Economist / Watchdog / Report Writer |
| `src/storage/schema.sql` | Normalized match store |
| `docs/TASKS.md` | Build plan |

## License

MIT
