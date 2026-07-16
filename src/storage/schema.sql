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

CREATE INDEX IF NOT EXISTS idx_players_puuid ON match_players(puuid);
CREATE INDEX IF NOT EXISTS idx_rounds_match ON rounds(match_id);
CREATE INDEX IF NOT EXISTS idx_rps_puuid ON round_player_stats(puuid);
