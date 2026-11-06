/* Fantasy game rules and season state, as pure functions.

   The squad rules mirror src/fantasy/squads.py line for line, and both run the shared
   cases in tests/fixtures/fantasy_cases.json, so the browser and the Python scorer can't
   disagree on what is legal or what a week is worth. Every number comes from the rules
   block in season.json; nothing here hard-codes a points value.

   No React and no I/O, so node's test runner imports this file directly. */

export const ROLES = ["duelist", "initiator", "controller", "sentinel"];
export const CHIPS = ["triple_captain", "bench_boost"];
export const CHIP_LABEL = { triple_captain: "Triple Captain", bench_boost: "Bench Boost" };

const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
const sum = (xs) => xs.reduce((a, b) => a + b, 0);

/** Reasons a squad is illegal, or an empty list. `prices` is one event's pool, keyed by
 *  entity id and already limited to the bracket the manager may pick from. */
export function validateSquad(squad, prices, rules, eventKind = "regional") {
  const r = rules.squad;
  const errors = [];
  const players = [...squad.starters, ...squad.subs];
  const everyone = [...players, ...squad.coaches];

  if (squad.starters.length !== r.starters) errors.push(`needs ${r.starters} starters`);
  if (squad.subs.length !== r.subs) errors.push(`needs ${r.subs} subs`);
  if (squad.coaches.length !== r.coaches) errors.push(`needs ${r.coaches} coaches`);
  if (new Set(everyone).size !== everyone.length) errors.push("the same person is picked twice");

  const unknown = everyone.filter((e) => !has(prices, e));
  if (unknown.length) {
    errors.push(`not available in this bracket: ${[...new Set(unknown)].sort().join(", ")}`);
    return errors;
  }

  if (players.some((p) => prices[p].kind !== "player")) errors.push("a coach is in a player slot");
  if (squad.coaches.some((c) => prices[c].kind !== "coach")) errors.push("a player is in a coach slot");

  const listed = new Set(squad.starters.map((p) => prices[p].listed_role));
  const missing = r.required_roles.filter((role) => !listed.has(role)).sort();
  if (missing.length) errors.push(`starters are missing: ${missing.join(", ")}`);

  const over = (ids, limit) => {
    const counts = {};
    for (const e of ids) counts[prices[e].team_id] = (counts[prices[e].team_id] ?? 0) + 1;
    return Object.values(counts).some((n) => n > limit);
  };
  if (over(players, r.max_players_per_team)) {
    errors.push(`more than ${r.max_players_per_team} players from one team`);
  }
  if (over(squad.coaches, r.max_coaches_per_team)) {
    errors.push(`more than ${r.max_coaches_per_team} coach from one team`);
  }

  const cost = squadCost(squad, prices);
  const budget = r.budget[eventKind];
  if (cost > budget) errors.push(`costs ${cost}, budget is ${budget}`);

  if (!squad.starters.includes(squad.captain) || !squad.starters.includes(squad.vice)) {
    errors.push("captain and vice-captain must be starters");
  } else if (squad.captain === squad.vice) {
    errors.push("captain and vice-captain must be different players");
  }
  return errors;
}

export function squadCost(squad, prices) {
  return sum(
    [...squad.starters, ...squad.subs, ...squad.coaches].map((e) => prices[e]?.price ?? 0),
  );
}

/** One match week. `points` holds only people who played, so absence means no map.
 *  Auto-sub, armband and chips follow score_week in src/fantasy/squads.py. */
export function scoreWeek(squad, points, rules, chip = null) {
  if (chip !== null && !CHIPS.includes(chip)) throw new Error(`unknown chip ${chip}`);
  const fielded = squad.starters.filter((p) => has(points, p));
  const bench = squad.subs.filter((p) => has(points, p));
  if (chip === "bench_boost") {
    fielded.push(...bench);
  } else {
    const missing = squad.starters.filter((p) => !has(points, p)).length;
    fielded.push(...bench.slice(0, missing));
  }

  const players = sum(fielded.map((p) => points[p]));
  const multiplier =
    chip === "triple_captain"
      ? rules.chips.triple_captain.captain_multiplier
      : rules.squad.captain_multiplier;
  const armband = has(points, squad.captain)
    ? squad.captain
    : has(points, squad.vice)
      ? squad.vice
      : null;
  const bonus = armband ? points[armband] * (multiplier - 1) : 0;
  const coaches = sum(squad.coaches.map((c) => points[c] ?? 0));
  return { players, captain_bonus: bonus, coaches, total: players + bonus + coaches };
}

/** Who scored for the squad this week, for the results view. Same order of rules as
 *  scoreWeek, so the rows always add up to its total. */
export function fieldedPlayers(squad, points, chip = null) {
  const bench = squad.subs.filter((p) => has(points, p));
  if (chip === "bench_boost") return [...squad.starters.filter((p) => has(points, p)), ...bench];
  const missing = squad.starters.filter((p) => !has(points, p)).length;
  return [...squad.starters.filter((p) => has(points, p)), ...bench.slice(0, missing)];
}

export function armbandHolder(squad, points) {
  if (has(points, squad.captain)) return squad.captain;
  if (has(points, squad.vice)) return squad.vice;
  return null;
}

export function transfersMade(previous, squad) {
  const before = new Set([...previous.starters, ...previous.subs, ...previous.coaches]);
  return [...squad.starters, ...squad.subs, ...squad.coaches].filter((e) => !before.has(e))
    .length;
}

export function transferHit(made, free, rules) {
  return Math.max(0, made - free) * rules.transfers.hit;
}

export function freeTransfersNext(free, made, rules) {
  const t = rules.transfers;
  return Math.min(t.max_banked, Math.max(0, free - made) + t.free_per_week);
}

export function chipHalf(eventId, eventOrder, rules) {
  const split = eventOrder.indexOf(rules.chips.second_half_from);
  return eventOrder.indexOf(eventId) >= split ? 2 : 1;
}

/* ------------------------------------------------------------- season state */

export const STATE_VERSION = 1;

/** Every match week in calendar order. The replay walks this list one entry at a time. */
export function weekList(season) {
  return season.events.flatMap((e, eventIdx) =>
    e.weeks.map((w) => ({
      key: `${e.event_id}-w${w.week_num}`,
      event_id: e.event_id,
      event: e,
      eventIdx,
      week_num: w.week_num,
      deadline_ms: w.deadline_ms,
      first: w.week_num === e.weeks[0].week_num,
    })),
  );
}

export function newState(region) {
  return {
    version: STATE_VERSION,
    region,
    cursor: 0,
    free: null, // null on an event's first week: a free rebuild
    chipsUsed: { triple_captain: [], bench_boost: [] },
    history: [],
    draft: emptyDraft(),
    chip: null,
  };
}

export function emptyDraft() {
  return { starters: [], subs: [], coaches: [], captain: null, vice: null };
}

/** Which bracket a manager picks from at this event. */
export function bracketFor(event, region) {
  return event.kind === "international" ? "global" : region;
}

/** The pool a manager may pick from, keyed by entity id. */
export function poolFor(players, event, region) {
  const bracket = bracketFor(event, region);
  return Object.fromEntries(
    players.pool.filter((p) => p.bracket === bracket).map((p) => [p.entity_id, p]),
  );
}

export function chipAvailable(state, chip, eventId, eventOrder, rules) {
  const half = chipHalf(eventId, eventOrder, rules);
  return state.chipsUsed[chip].filter((h) => h === half).length < rules.chips.uses_per_half;
}

/** The squad this event last locked, which transfers are counted against. */
export function lastLocked(state, eventId) {
  for (let i = state.history.length - 1; i >= 0; i--) {
    if (state.history[i].event_id === eventId) return state.history[i].squad;
  }
  return null;
}

/** Keep whoever is still available when an event changes, so the rebuild starts from
 *  the last squad rather than from nothing. */
export function carryOver(draft, pool) {
  const keep = (ids) => ids.filter((e) => has(pool, e));
  const starters = keep(draft.starters);
  return {
    starters,
    subs: keep(draft.subs),
    coaches: keep(draft.coaches),
    captain: starters.includes(draft.captain) ? draft.captain : null,
    vice: starters.includes(draft.vice) ? draft.vice : null,
  };
}

/** What locking the draft would cost in transfers, before anything is committed. */
export function pendingTransfers(state, week, rules) {
  if (week.first) return { made: 0, free: null, hit: 0 };
  const previous = lastLocked(state, week.event_id);
  const made = previous ? transfersMade(previous, state.draft) : 0;
  return { made, free: state.free, hit: transferHit(made, state.free, rules) };
}

/** Lock the draft for the current week and play it. Returns the next state. */
export function lockWeek(state, season, weekPoints, rules) {
  const weeks = weekList(season);
  const week = weeks[state.cursor];
  const order = season.events.map((e) => e.event_id);
  const { made, free, hit } = pendingTransfers(state, week, rules);
  const points = Object.fromEntries(
    Object.entries(weekPoints.entities).map(([e, v]) => [e, v.total]),
  );
  const score = scoreWeek(state.draft, points, rules, state.chip);

  const chipsUsed = { ...state.chipsUsed };
  if (state.chip) chipsUsed[state.chip] = [...chipsUsed[state.chip], chipHalf(week.event_id, order, rules)];

  const next = weeks[state.cursor + 1];
  return {
    ...state,
    cursor: state.cursor + 1,
    free: !next || next.first ? null : week.first ? rules.transfers.free_per_week : freeTransfersNext(free, made, rules),
    chipsUsed,
    chip: null,
    history: [
      ...state.history,
      {
        key: week.key,
        event_id: week.event_id,
        week_num: week.week_num,
        squad: state.draft,
        chip: state.chip,
        made,
        hit,
        score,
        net: score.total - hit,
      },
    ],
  };
}

/** Cumulative points for you and every rival in your region, after the weeks played. */
export function standings(state, rivals, myName = "Your squad") {
  const played = state.history.map((h) => h.key);
  const rows = rivals.managers
    .filter((m) => m.region === state.region)
    .map((m) => ({
      id: m.manager_id,
      name: m.name,
      you: false,
      total: sum(played.map((k) => rivals.scores[m.manager_id][k] ?? 0)),
      last: played.length ? rivals.scores[m.manager_id][played[played.length - 1]] ?? 0 : null,
    }));
  rows.push({
    id: "you",
    name: myName,
    you: true,
    total: sum(state.history.map((h) => h.net)),
    last: state.history.length ? state.history[state.history.length - 1].net : null,
  });
  rows.sort((a, b) => b.total - a.total || Number(b.you) - Number(a.you) || a.name.localeCompare(b.name));
  return rows.map((r, i) => ({ ...r, rank: i + 1 }));
}

/** A random legal squad from the pool, for the Auto-pick button. Mirrors random_squad in
 *  src/fantasy/balance.py: one of each role, a free pick, two subs, two coaches. */
export function autoPick(pool, rules, eventKind, rand = Math.random) {
  const pick = (xs) => xs[Math.floor(rand() * xs.length)];
  const entries = Object.values(pool);
  const players = entries.filter((p) => p.kind === "player").map((p) => p.entity_id).sort();
  const coaches = entries.filter((p) => p.kind === "coach").map((p) => p.entity_id).sort();
  for (let attempt = 0; attempt < 5000; attempt++) {
    const starters = rules.squad.required_roles.map((role) =>
      pick(players.filter((p) => pool[p].listed_role === role)),
    );
    const rest = players.filter((p) => !starters.includes(p));
    const extra = [];
    while (extra.length < 3) {
      const p = pick(rest);
      if (!extra.includes(p)) extra.push(p);
    }
    const chosenCoaches = [];
    while (chosenCoaches.length < rules.squad.coaches) {
      const c = pick(coaches);
      if (!chosenCoaches.includes(c)) chosenCoaches.push(c);
    }
    const all = [...starters, extra[0]];
    const byPrice = [...all].sort((a, b) => pool[b].price - pool[a].price || a.localeCompare(b));
    const squad = {
      starters: all,
      subs: extra.slice(1),
      coaches: chosenCoaches,
      captain: byPrice[0],
      vice: byPrice[1],
    };
    if (!validateSquad(squad, pool, rules, eventKind).length) return squad;
  }
  return null;
}

/** Turn one entity's points on one map into the claim shape TraceView renders, so a
 *  fantasy point opens the same decision trace a coaching claim does. */
export function pointsAsClaim(trace, entity, label) {
  const p = trace.points[entity];
  const who = (i) => trace.players[i]?.puuid;
  const evidence = p.components.map((c) => {
    const rows = [];
    for (const i of c.rows.kills ?? []) {
      const [round, ordinal, killer, victim] = trace.kills[i];
      rows.push({ table: "round_kills", round_num: round, kill_ordinal: ordinal, puuid: c.rule === "death" || c.rule === "first_death" ? who(killer) : who(victim) });
    }
    for (const i of c.rows.assists ?? []) {
      const [round, ordinal, , victim] = trace.kills[i];
      rows.push({ table: "round_kill_assists", round_num: round, kill_ordinal: ordinal, puuid: who(victim) });
    }
    for (const n of c.rows.rounds ?? []) rows.push({ table: "rounds", round_num: n });
    for (const o of c.rows.other ?? []) rows.push(o);
    return {
      feature: { name: `fp_${c.rule}:${entity}`, scope: "fantasy", round_num: -1, value: c.value },
      source_rows: rows,
    };
  });
  return {
    rule_id: `fantasy.${trace.rules_version}`,
    agent: "Scorer",
    severity: "info",
    claim: `${label}: ${fmtPoints(p.total)} points on ${trace.map_name} (map ${trace.map_num}).`,
    verified: true,
    unverified_reason: null,
    evidence,
  };
}

export const fmtPoints = (n) =>
  n === null || n === undefined ? "—" : Number.isInteger(n) ? String(n) : n.toFixed(1);

export const fmtPrice = (n) => (n === null || n === undefined ? "—" : n.toFixed(1));

export const roleLabel = (r) => (r ? r[0].toUpperCase() + r.slice(1) : "Coach");
