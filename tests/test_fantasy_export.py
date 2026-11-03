"""F3 fantasy bundles: byte-stable, lossless against the store, and verified-only."""

from __future__ import annotations

import json

import pytest

import src.fantasy.export as fx
from src.fantasy.export import decode_refs, export
from src.fantasy.scoring import score_season
from src.fantasy.source import SimProSeasonSource
from src.fantasy.store import load_season, open_store


@pytest.fixture(scope="module")
def season(tmp_path_factory):
    conn = open_store(str(tmp_path_factory.mktemp("export") / "season.db"))
    conn.execute("PRAGMA synchronous=OFF")
    load_season(conn, SimProSeasonSource(1337))
    score_season(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def bundle(season, tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle")
    result = export(season, out)
    return out, result


def _files(root):
    return {str(f.relative_to(root)): f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_re_export_is_byte_identical(season, bundle, tmp_path):
    out, _ = bundle
    export(season, tmp_path)
    assert _files(tmp_path) == _files(out)


def test_one_file_per_map_week_and_event(season, bundle):
    out, result = bundle
    count = lambda sql: season.execute(sql).fetchone()[0]  # noqa: E731
    assert len(list((out / "traces").glob("*.json"))) == count("SELECT COUNT(*) FROM series_maps")
    assert len(list((out / "points").glob("*.json"))) == count("SELECT COUNT(*) FROM match_weeks")
    assert len(list((out / "players").glob("*.json"))) == count("SELECT COUNT(*) FROM events")
    assert result["excluded"] == 0


def test_traces_decode_to_the_stored_lineage(season, bundle):
    """The compact form loses nothing: every component rebuilds its store row exactly."""
    out, _ = bundle
    stored = {(r["match_id"], r["name"]): r for r in season.execute(
        "SELECT match_id, name, value, inputs_json FROM features WHERE scope='fantasy'")}
    checked = 0
    for path in sorted((out / "traces").glob("*.json")):
        trace = _load(path)
        for entity, p in trace["points"].items():
            for c in p["components"]:
                row = stored[(trace["match_id"], f"fp_{c['rule']}:{entity}")]
                head, *refs = json.loads(row["inputs_json"])
                assert (c["rule"], c["count"], c["points_each"], c["value"]) == (
                    head["rule"], head["count"], head["points_each"], row["value"])
                key = lambda r: json.dumps(r, sort_keys=True)  # noqa: E731
                assert sorted(map(key, decode_refs(c["rows"], trace, entity))) == sorted(map(key, refs))
                checked += 1
    assert checked == sum(1 for (_, name) in stored if not name.partition(":")[0].endswith("total"))


def test_kill_indexes_point_at_the_entitys_own_kills(bundle):
    out, _ = bundle
    trace = _load(next((out / "traces").glob("*.json")))
    index = {p["puuid"]: i for i, p in enumerate(trace["players"])}
    for entity, p in trace["points"].items():
        for c in p["components"]:
            if c["rule"] == "kill":
                assert all(trace["kills"][k][2] == index[entity] for k in c["rows"]["kills"])
            if c["rule"] == "death":
                assert all(trace["kills"][k][3] == index[entity] for k in c["rows"]["kills"])
            if c["rule"] == "assist":
                assert all(index[entity] in trace["kills"][k][4] for k in c["rows"]["assists"])


def test_totals_add_up_from_map_to_week(bundle):
    out, _ = bundle
    traces = {t["match_id"]: t for t in map(_load, (out / "traces").glob("*.json"))}
    for t in traces.values():
        for p in t["points"].values():
            assert p["total"] == pytest.approx(sum(c["value"] for c in p["components"]))

    for path in (out / "points").glob("*.json"):
        week = _load(path)
        played = [t for t in traces.values()
                  if (t["event_id"], t["week_num"]) == (week["event_id"], week["week_num"])]
        assert set(week["entities"]) == {e for t in played for e in t["points"]}
        for entity, e in week["entities"].items():
            assert e["total"] == pytest.approx(sum(traces[m["match_id"]]["points"][entity]["total"]
                                                   for m in e["maps"]))
            assert e["total"] == pytest.approx(sum(e["by_rule"].values()))


def test_pools_match_prices_and_brackets(season, bundle):
    out, _ = bundle
    s = _load(out / "season.json")
    for i, event in enumerate(s["events"]):
        pool = _load(out / "players" / f"{event['event_id']}.json")
        priced = season.execute("SELECT COUNT(*) FROM event_prices WHERE event_id=?",
                                (event["event_id"],)).fetchone()[0]
        assert len(pool["pool"]) == priced
        brackets = {t["team_id"]: t["bracket"] for t in event["entries"]}
        assert all(p["bracket"] == brackets[p["team_id"]] for p in pool["pool"])
        if i == 0:
            assert all(p["previous_price"] is None for p in pool["pool"])
        if event["kind"] == "international":
            assert {p["bracket"] for p in pool["pool"]} == {"global"}


def test_season_carries_provenance_and_no_ground_truth(bundle):
    out, _ = bundle
    s = _load(out / "season.json")
    assert s["provenance"]["fictional"] is True and s["provenance"]["sources"] == ["sim"]
    assert all("rating" not in t for t in s["teams"])
    assert all("skill" not in p for p in s["players"])
    assert any(e["assumed"] for e in s["events"])


def test_corrupted_point_is_left_out_and_listed(season, tmp_path):
    row = season.execute(
        """SELECT f.match_id, f.name, s.event_id, s.week_num FROM features f
           JOIN series_maps sm ON sm.match_id = f.match_id JOIN series s ON s.series_id = sm.series_id
           WHERE f.scope='fantasy' AND f.name LIKE 'fp_kill:%' LIMIT 1""").fetchone()
    entity = row["name"].partition(":")[2]
    try:
        season.execute("UPDATE features SET value = value + 2 WHERE match_id=? AND name=?",
                       (row["match_id"], row["name"]))
        result = export(season, tmp_path)
    finally:
        season.execute("UPDATE features SET value = value - 2 WHERE match_id=? AND name=?",
                       (row["match_id"], row["name"]))
        season.commit()

    assert result["excluded"] == 1
    trace = _load(tmp_path / "traces" / f"{row['match_id']}.json")
    assert entity not in trace["points"]
    week = _load(tmp_path / "points" / f"{row['event_id']}-w{row['week_num']}.json")
    assert [e["name"] for e in week["excluded"]] == [row["name"]]
    assert all(m["match_id"] != row["match_id"] for m in week["entities"].get(entity, {}).get("maps", []))


def test_stale_files_are_removed(season, tmp_path):
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "vct27-gone.json").write_text("{}")
    export(season, tmp_path)
    assert not (tmp_path / "traces" / "vct27-gone.json").exists()


def test_refuses_the_coaching_bundle_directory(season, tmp_path):
    (tmp_path / "index.json").write_text("{}")
    with pytest.raises(SystemExit, match="coaching index"):
        export(season, tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / "index.json"]


def test_size_budget(season, bundle, tmp_path, monkeypatch):
    _, result = bundle
    assert result["bytes"] <= fx.SIZE_BUDGET_BYTES
    monkeypatch.setattr(fx, "SIZE_BUDGET_BYTES", 1024)
    with pytest.raises(SystemExit, match="budget"):
        export(season, tmp_path)


def test_refuses_an_unscored_store(tmp_path):
    with pytest.raises(SystemExit, match="no points"):
        export(open_store(str(tmp_path / "empty.db")), tmp_path / "out")
