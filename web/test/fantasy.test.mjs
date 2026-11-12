/* The browser's fantasy rules against the shared cases that tests/test_fantasy_cases.py
 * runs against the Python implementation. Both must pass, so neither can drift.
 *
 * Run: npm test  (from web/)
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";

import {
  autoPick,
  chipHalf,
  freeTransfersNext,
  lockWeek,
  newState,
  poolFor,
  scoreWeek,
  standings,
  transferHit,
  transfersMade,
  validateSquad,
  weekList,
} from "../src/lib/fantasy.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");
const data = path.join(repo, "web", "public", "data", "fantasy");
const json = async (p) => JSON.parse(await readFile(p, "utf-8"));

const cases = await json(path.join(repo, "tests", "fixtures", "fantasy_cases.json"));
const rules = cases.rules;

describe("shared squad cases", () => {
  for (const c of cases.validate) {
    it(`validate: ${c.name}`, () => {
      assert.deepEqual(validateSquad(c.squad, cases.prices, rules, c.event_kind), c.errors);
    });
  }
  for (const c of cases.score) {
    it(`score: ${c.name}`, () => {
      assert.deepEqual(scoreWeek(c.squad, c.points, rules, c.chip), c.expected);
    });
  }
  for (const c of cases.transfers) {
    it(`transfers: ${c.name}`, () => {
      const made = transfersMade(c.previous, c.squad);
      assert.deepEqual(
        [made, transferHit(made, c.free, rules), freeTransfersNext(c.free, made, rules)],
        [c.made, c.hit, c.free_next],
      );
    });
  }
  for (const c of cases.chip_half) {
    it(`chip half: ${c.event_id}`, () => {
      assert.equal(chipHalf(c.event_id, c.event_order, rules), c.half);
    });
  }
});

describe("season replay on the exported bundles", () => {
  it("scores every rival exactly as the Python export did", async () => {
    const season = await json(path.join(data, "season.json"));
    const rivals = await json(path.join(data, "rivals.json"));
    for (const w of weekList(season)) {
      const week = await json(path.join(data, "points", `${w.key}.json`));
      const points = Object.fromEntries(
        Object.entries(week.entities).map(([e, v]) => [e, v.total]),
      );
      for (const m of rivals.managers) {
        const squad = rivals.squads[w.event_id][m.manager_id];
        assert.equal(
          scoreWeek(squad, points, season.rules).total,
          rivals.scores[m.manager_id][w.key],
          `${m.manager_id} ${w.key}`,
        );
      }
    }
  });

  it("plays a whole season end to end with auto-picked squads, transfers and chips", async () => {
    const season = await json(path.join(data, "season.json"));
    const rivals = await json(path.join(data, "rivals.json"));
    const r = season.rules;
    let seed = 7;
    const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

    let state = newState("emea");
    const weeks = weekList(season);
    for (const w of weeks) {
      const players = await json(path.join(data, "players", `${w.event_id}.json`));
      const pool = poolFor(players, w.event, state.region);
      if (w.first) {
        state = { ...state, draft: autoPick(pool, r, w.event.kind, rand) };
        assert.ok(state.draft, `no legal squad at ${w.key}`);
      }
      assert.deepEqual(validateSquad(state.draft, pool, r, w.event.kind), []);
      if (w.key === "kickoff-w2") state = { ...state, chip: "triple_captain" };
      if (w.key === "champions-w2") state = { ...state, chip: "bench_boost" };
      if (w.key === "kickoff-w3") {
        // One transfer: swap the first sub for a same-role player not in the squad.
        const out = state.draft.subs[0];
        const role = pool[out].listed_role;
        const teamCount = (t) =>
          [...state.draft.starters, ...state.draft.subs].filter((p) => pool[p].team_id === t).length;
        const inn = Object.values(pool).find(
          (p) =>
            p.kind === "player" &&
            p.listed_role === role &&
            ![...state.draft.starters, ...state.draft.subs].includes(p.entity_id) &&
            p.price <= pool[out].price &&
            teamCount(p.team_id) < r.squad.max_players_per_team,
        );
        state = { ...state, draft: { ...state.draft, subs: [inn.entity_id, state.draft.subs[1]] } };
      }
      const before = state.free;
      const week = await json(path.join(data, "points", `${w.key}.json`));
      state = lockWeek(state, season, week, r);
      const last = state.history.at(-1);
      if (w.key === "kickoff-w3") {
        assert.equal(last.made, 1);
        assert.equal(last.hit, Math.max(0, 1 - before) * r.transfers.hit);
      }
      if (w.first) assert.equal(last.hit, 0, "an event's first week is a free rebuild");
    }

    assert.equal(state.cursor, weeks.length);
    assert.deepEqual(state.chipsUsed, { triple_captain: [1], bench_boost: [2] });
    const table = standings(state, rivals);
    assert.equal(table.length, 9);
    assert.equal(table.filter((t) => t.you).length, 1);
    assert.deepEqual(
      table.map((t) => t.rank),
      [1, 2, 3, 4, 5, 6, 7, 8, 9],
    );
  });
});
