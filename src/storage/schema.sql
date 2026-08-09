-- Normalized store for val-match-v1 payloads.
-- Column names mirror the API's field names so the mapping stays auditable.

CREATE TABLE IF NOT EXISTS matches (
    match_id        TEXT PRIMARY KEY,
    map_id          TEXT NOT NULL,
    game_length_ms  INTEGER,
    game_start_ms   INTEGER,
    queue_id        TEXT,
    season_id       TEXT,
    is_completed    INTEGER,
    source          TEXT NOT NULL,        -- 'sim' | 'live'  (provenance is never lost)
    -- The player whose matchlist produced this row, when they are in the roster.
    -- Without it there is no "your team", and every coaching number would have to
    -- be phrased from a side (Blue/Red) rather than from the player's own point of
    -- view. NULL is legitimate: bulk ingest with no focal player, or a puuid that
    -- does not appear in the match.
    hero_puuid      TEXT,
    ingested_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id        TEXT NOT NULL REFERENCES matches(match_id),
    puuid           TEXT NOT NULL,
    team_id         TEXT NOT NULL,
    character_id    TEXT NOT NULL,        -- agent
    competitive_tier INTEGER,
    score           INTEGER,
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    PRIMARY KEY (match_id, puuid)
);

CREATE TABLE IF NOT EXISTS rounds (
    match_id        TEXT NOT NULL REFERENCES matches(match_id),
    round_num       INTEGER NOT NULL,
    winning_team    TEXT,
    round_result    TEXT,                 -- Eliminated | Bomb detonated | Bomb defused | Round timer expired
    round_ceremony  TEXT,
    plant_site      TEXT,
    plant_ms        INTEGER,
    defuse_ms       INTEGER,
    PRIMARY KEY (match_id, round_num)
);

CREATE TABLE IF NOT EXISTS round_player_stats (
    match_id        TEXT NOT NULL,
    round_num       INTEGER NOT NULL,
    puuid           TEXT NOT NULL,
    loadout_value   INTEGER,              -- economy: what they walked in with
    spent           INTEGER,
    remaining       INTEGER,
    armor_id        TEXT,
    weapon_id       TEXT,
    kills           INTEGER,
    damage          INTEGER,
    score           INTEGER,
    PRIMARY KEY (match_id, round_num, puuid)
);

-- Ingest bookkeeping: makes the pipeline resumable across dev-key expiry.
CREATE TABLE IF NOT EXISTS ingest_log (
    match_id        TEXT PRIMARY KEY,
    status          TEXT NOT NULL,        -- pending | done | failed
    attempts        INTEGER DEFAULT 0,
    last_error      TEXT,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Derived signals every coaching claim cites. inputs_json is lineage: the source
-- rows (as {table, match_id, round_num, ...} references) a value was computed
-- from, so the Phase 3 decision trace can point from a claim back to raw rows.
-- round_num uses -1 as the sentinel for match-scoped (not per-round) features,
-- since SQLite doesn't enforce PK uniqueness across NULLs the way idempotent
-- re-runs need.
CREATE TABLE IF NOT EXISTS features (
    match_id        TEXT NOT NULL REFERENCES matches(match_id),
    round_num       INTEGER NOT NULL DEFAULT -1,
    scope           TEXT NOT NULL,        -- 'match' | 'round' | 'team_round' | ...
    name            TEXT NOT NULL,
    value           REAL,
    inputs_json     TEXT NOT NULL,
    computed_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id, round_num, scope, name)
);

CREATE INDEX IF NOT EXISTS idx_players_puuid ON match_players(puuid);
CREATE INDEX IF NOT EXISTS idx_rounds_match ON rounds(match_id);
CREATE INDEX IF NOT EXISTS idx_rps_puuid ON round_player_stats(puuid);
CREATE INDEX IF NOT EXISTS idx_features_match ON features(match_id);
