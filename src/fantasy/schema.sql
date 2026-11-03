-- Fantasy season tables. These live beside the match tables from
-- src/storage/schema.sql, in a separate store (see src/fantasy/store.py), because the
-- coaching export reads every row of `matches`.

CREATE TABLE IF NOT EXISTS pro_teams (
    team_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    region          TEXT NOT NULL,
    tier            TEXT NOT NULL,        -- partner | visitor | open
    rating          REAL                  -- sim ground truth; a real source has none
);

CREATE TABLE IF NOT EXISTS pro_players (
    puuid           TEXT PRIMARY KEY,
    handle          TEXT NOT NULL,
    region          TEXT NOT NULL,
    base_role       TEXT NOT NULL,        -- the role they normally play
    skill           REAL                  -- sim ground truth; a real source has none
);

CREATE TABLE IF NOT EXISTS pro_coaches (
    coach_id        TEXT PRIMARY KEY,
    handle          TEXT NOT NULL,
    team_id         TEXT NOT NULL REFERENCES pro_teams(team_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    ordinal         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,        -- regional | international
    starts_on       TEXT NOT NULL,
    ends_on         TEXT NOT NULL,
    format_json     TEXT NOT NULL,        -- carries `assumed` so the UI can label it
    field_json      TEXT NOT NULL,
    cities_json     TEXT NOT NULL
);

-- A fantasy match week inside an event. The deadline is its first scheduled series.
CREATE TABLE IF NOT EXISTS match_weeks (
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    week_num        INTEGER NOT NULL,
    deadline_ms     INTEGER NOT NULL,
    PRIMARY KEY (event_id, week_num)
);

-- Who entered an event. `bracket` is the region, or 'global' at international events.
CREATE TABLE IF NOT EXISTS event_teams (
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    team_id         TEXT NOT NULL REFERENCES pro_teams(team_id),
    bracket         TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    placement       INTEGER NOT NULL,     -- 1 = champion; tied exits share a placement
    qualified_via   TEXT NOT NULL,
    PRIMARY KEY (event_id, team_id)
);

-- Rosters are per event: a player's team can change between events, never during one.
CREATE TABLE IF NOT EXISTS event_rosters (
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    team_id         TEXT NOT NULL REFERENCES pro_teams(team_id),
    puuid           TEXT NOT NULL REFERENCES pro_players(puuid),
    PRIMARY KEY (event_id, puuid)
);

-- Fantasy prices and squad-building roles, fixed for an event. `entity_id` is a puuid
-- or coach_id. listed_role is NULL for coaches.
CREATE TABLE IF NOT EXISTS event_prices (
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    entity_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,        -- player | coach
    team_id         TEXT NOT NULL REFERENCES pro_teams(team_id),
    price           REAL NOT NULL,
    listed_role     TEXT,
    PRIMARY KEY (event_id, entity_id)
);

CREATE TABLE IF NOT EXISTS series (
    series_id       TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    bracket         TEXT NOT NULL,
    stage           TEXT NOT NULL,        -- upper | lower | final
    round_num       INTEGER NOT NULL,
    week_num        INTEGER NOT NULL,
    scheduled_ms    INTEGER NOT NULL,
    best_of         INTEGER NOT NULL,
    team_a          TEXT NOT NULL REFERENCES pro_teams(team_id),
    team_b          TEXT NOT NULL REFERENCES pro_teams(team_id),
    maps_a          INTEGER NOT NULL,
    maps_b          INTEGER NOT NULL,
    winner          TEXT NOT NULL REFERENCES pro_teams(team_id)
);

-- Links a val-match-v1 map (one row of `matches`) to its series and real teams, since
-- the payload itself only knows Red and Blue.
CREATE TABLE IF NOT EXISTS series_maps (
    series_id       TEXT NOT NULL REFERENCES series(series_id),
    map_num         INTEGER NOT NULL,
    match_id        TEXT NOT NULL REFERENCES matches(match_id),
    red_team        TEXT NOT NULL REFERENCES pro_teams(team_id),
    blue_team       TEXT NOT NULL REFERENCES pro_teams(team_id),
    winner          TEXT NOT NULL REFERENCES pro_teams(team_id),
    PRIMARY KEY (series_id, map_num)
);

CREATE INDEX IF NOT EXISTS idx_series_event ON series(event_id, bracket, round_num);
CREATE INDEX IF NOT EXISTS idx_series_maps_match ON series_maps(match_id);
