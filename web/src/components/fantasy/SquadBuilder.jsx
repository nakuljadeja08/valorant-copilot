import { useEffect, useMemo, useRef, useState } from "react";

import { loadJson, useJson } from "../../lib/data.js";
import {
  CHIPS,
  CHIP_LABEL,
  ROLES,
  autoPick,
  carryOver,
  chipAvailable,
  fmtPoints,
  fmtPrice,
  lockWeek,
  pendingTransfers,
  poolFor,
  roleLabel,
  squadCost,
  validateSquad,
} from "../../lib/fantasy.js";
import RoleGlyph from "../RoleGlyph.jsx";
import { dateOf } from "./FantasyHub.jsx";
import { regionLabel } from "./FantasyLanding.jsx";
import { totalsFrom, usePlayedWeeks } from "./usePlayed.js";

const ROLE_FILTERS = ["all", ...ROLES, "coach"];

/* Build and lock this match week's squad. The draft is saved as you edit, so a reload
   never loses a half-built squad. Rule errors come from validateSquad, the same
   function the shared cases check against Python. */
export default function SquadBuilder({ season, state, setState, dir, weeks }) {
  const week = weeks[state.cursor];
  const { data: players } = useJson(`fantasy/players/${week?.event_id ?? season.events[0].event_id}.json`);
  const played = usePlayedWeeks(state.history.map((h) => h.key));
  const totals = useMemo(() => totalsFrom(played), [played]);
  const [role, setRole] = useState("all");
  const [team, setTeam] = useState("all");
  const [sort, setSort] = useState("price");
  const [query, setQuery] = useState("");
  const [swapping, setSwapping] = useState(null);
  const [locking, setLocking] = useState(false);
  const poolRef = useRef(null);

  const pool = useMemo(
    () => (players && week ? poolFor(players, week.event, state.region) : null),
    [players, week, state.region],
  );

  // A new event: keep whoever is still available, drop the rest.
  useEffect(() => {
    if (!pool || !week?.first) return;
    const kept = carryOver(state.draft, pool);
    if (JSON.stringify(kept) !== JSON.stringify(state.draft)) setState({ ...state, draft: kept });
  }, [pool]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!week) {
    return (
      <p className="empty">
        The season is over. <a href="#/fantasy">See the final table</a>.
      </p>
    );
  }
  if (!pool) return <p className="empty">Loading…</p>;

  const rules = season.rules;
  const kind = week.event.kind;
  const draft = state.draft;
  const setDraft = (d) => setState({ ...state, draft: d });
  const inSquad = new Set([...draft.starters, ...draft.subs, ...draft.coaches]);
  const errors = validateSquad(draft, pool, rules, kind);
  const cost = squadCost(draft, pool);
  const budget = rules.squad.budget[kind];
  const transfers = pendingTransfers(state, week, rules);
  const order = season.events.map((e) => e.event_id);
  const teamName = (id) => dir.teams[id]?.name ?? id;

  const canAdd = (e) =>
    pool[e].kind === "coach"
      ? draft.coaches.length < rules.squad.coaches
      : draft.starters.length < rules.squad.starters || draft.subs.length < rules.squad.subs;

  const add = (e) => {
    if (pool[e].kind === "coach") return setDraft({ ...draft, coaches: [...draft.coaches, e] });
    if (draft.starters.length < rules.squad.starters) {
      return setDraft({ ...draft, starters: [...draft.starters, e] });
    }
    return setDraft({ ...draft, subs: [...draft.subs, e] });
  };

  const remove = (e) => {
    const drop = (xs) => xs.filter((x) => x !== e);
    setSwapping(null);
    setDraft({
      starters: drop(draft.starters),
      subs: drop(draft.subs),
      coaches: drop(draft.coaches),
      captain: draft.captain === e ? null : draft.captain,
      vice: draft.vice === e ? null : draft.vice,
    });
  };

  // Click Swap on one player, then on one in the other group, to trade places.
  const swap = (e) => {
    if (!swapping) return setSwapping(e);
    const a = swapping;
    setSwapping(null);
    if (a === e) return;
    const starterA = draft.starters.includes(a);
    if (starterA === draft.starters.includes(e)) return setSwapping(e);
    const [s, b] = starterA ? [a, e] : [e, a];
    const starters = draft.starters.map((x) => (x === s ? b : x));
    setDraft({
      ...draft,
      starters,
      subs: draft.subs.map((x) => (x === b ? s : x)),
      captain: starters.includes(draft.captain) ? draft.captain : null,
      vice: starters.includes(draft.vice) ? draft.vice : null,
    });
  };

  const armband = (e, which) => {
    const other = which === "captain" ? "vice" : "captain";
    setDraft({ ...draft, [which]: e, [other]: draft[other] === e ? null : draft[other] });
  };

  const toggleChip = (c) => setState({ ...state, chip: state.chip === c ? null : c });

  const lock = async () => {
    setLocking(true);
    try {
      const points = await loadJson(`fantasy/points/${week.key}.json`);
      setState(lockWeek(state, season, points, rules));
      window.location.hash = `#/fantasy/week/${week.key}`;
    } finally {
      setLocking(false);
    }
  };

  const teams = [...new Set(Object.values(pool).map((p) => p.team_id))].sort((a, b) =>
    teamName(a).localeCompare(teamName(b)),
  );
  const q = query.trim().toLowerCase();
  const rows = Object.values(pool)
    .filter((p) => (role === "all" ? true : role === "coach" ? p.kind === "coach" : p.listed_role === role))
    .filter((p) => team === "all" || p.team_id === team)
    .filter((p) => !q || p.handle.toLowerCase().includes(q) || teamName(p.team_id).toLowerCase().includes(q))
    .sort((a, b) =>
      sort === "points"
        ? (totals[b.entity_id] ?? 0) - (totals[a.entity_id] ?? 0) || b.price - a.price
        : b.price - a.price || a.handle.localeCompare(b.handle),
    );

  // An empty seat sends you to the pool, filtered to what the squad still needs.
  const browse = (r) => {
    setRole(r);
    poolRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };

  const seat = (e, slot) => {
    const p = pool[e];
    const captain = draft.captain === e;
    const vice = draft.vice === e;
    return (
      <li
        key={e}
        className={`fx-seat fx-seat-${slot}${captain ? " fx-seat-captain" : ""}${swapping === e ? " fx-swapping" : ""}`}
      >
        <div className="fx-seat-screen">
          {p.kind === "coach" ? <CoachGlyph /> : <RoleGlyph role={p.listed_role} size={slot === "starter" ? 40 : 30} />}
          <span className="fx-seat-role">{roleLabel(p.listed_role)}</span>
          {(captain || vice) && <span className={`fx-band${vice ? " fx-band-vice" : ""}`}>{captain ? "C" : "V"}</span>}
        </div>
        <div className="fx-seat-body">
          <a className="fx-seat-name" href={`#/fantasy/player/${e}`}>
            {p.handle}
          </a>
          <span className="fx-seat-team">{teamName(p.team_id)}</span>
          <span className="fx-seat-price mono">{fmtPrice(p.price)}</span>
        </div>
        <div className="fx-seat-actions">
          {slot === "starter" && (
            <>
              <button type="button" className="table-toggle" aria-pressed={captain} onClick={() => armband(e, "captain")} aria-label={`Make ${p.handle} captain`} title="Captain">
                C
              </button>
              <button type="button" className="table-toggle" aria-pressed={vice} onClick={() => armband(e, "vice")} aria-label={`Make ${p.handle} vice-captain`} title="Vice-captain">
                V
              </button>
            </>
          )}
          {slot !== "coach" && (
            <button
              type="button"
              className="table-toggle"
              aria-pressed={swapping === e}
              onClick={() => swap(e)}
              aria-label={slot === "starter" ? `Swap ${p.handle} with a sub` : `Swap ${p.handle} onto the stage`}
              title="Swap"
            >
              ⇄
            </button>
          )}
          <button type="button" className="table-toggle" onClick={() => remove(e)} aria-label={`Remove ${p.handle}`} title="Remove">
            ✕
          </button>
        </div>
      </li>
    );
  };

  const emptySeats = (slot, n, hints) =>
    Array.from({ length: n }, (_, i) => {
      const want = hints[i] ?? hints.at(-1);
      return (
        <li key={`empty-${slot}-${i}`} className={`fx-seat fx-seat-${slot} fx-seat-empty`}>
          <button type="button" className="fx-seat-add" onClick={() => browse(want.filter)}>
            <span className="fx-seat-plus" aria-hidden="true">
              +
            </span>
            <span>{want.label}</span>
          </button>
        </li>
      );
    });

  // Starters sit on stage by role, left to right, so the desk reads like a lineup.
  const onStage = [...draft.starters].sort(
    (a, b) => ROLES.indexOf(pool[a].listed_role) - ROLES.indexOf(pool[b].listed_role),
  );
  const listedRoles = new Set(draft.starters.map((e) => pool[e].listed_role));
  const starterHints = [
    ...rules.squad.required_roles
      .filter((r) => !listedRoles.has(r))
      .map((r) => ({ label: `Add ${r}`, filter: r })),
    { label: "Add any role", filter: "all" },
  ];

  const complete =
    draft.starters.length === rules.squad.starters &&
    draft.subs.length === rules.squad.subs &&
    draft.coaches.length === rules.squad.coaches;

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">
            {week.event.kind === "international" ? "Any qualified team" : `${regionLabel(state.region)} teams only`} · deadline{" "}
            {dateOf(week.deadline_ms)} (simulated)
          </div>
          <h1 className="page-title">
            {week.event.name} · week {week.week_num}
          </h1>
        </div>
      </header>

      <div className="fx-builder">
        <section className="panel fx-squad" aria-label="Your squad">
          <div className="panel-head">
            <div className="section-title">Your squad</div>
            <button
              type="button"
              className="table-toggle"
              onClick={() => setDraft(autoPick(pool, rules, kind) ?? draft)}
            >
              Auto-pick
            </button>
          </div>

          <div className={`fx-budget${cost > budget ? " over" : ""}`}>
            <div className="fx-budget-bar" aria-hidden="true">
              <span style={{ width: `${Math.min(100, (cost / budget) * 100)}%` }} />
            </div>
            <span className="mono">
              {fmtPrice(cost)} / {budget} credits
            </span>
          </div>

          <div className="fx-stage" aria-label="Starting five">
            <div className="fx-stage-label">
              <span>On stage</span>
              <span className="fx-sub">starters score · captain ×{rules.squad.captain_multiplier}</span>
            </div>
            <ul className="fx-stage-seats">
              {onStage.map((e) => seat(e, "starter"))}
              {emptySeats("starter", rules.squad.starters - draft.starters.length, starterHints)}
            </ul>
            <div className="fx-desk" aria-hidden="true" />
          </div>

          <div className="fx-dugout">
            <div className="fx-dugout-group">
              <div className="eyebrow">Bench · auto-sub order</div>
              <ul className="fx-dugout-seats">
                {draft.subs.map((e) => seat(e, "sub"))}
                {emptySeats("sub", rules.squad.subs - draft.subs.length, [{ label: "Add sub", filter: "all" }])}
              </ul>
            </div>
            <div className="fx-dugout-group">
              <div className="eyebrow">Coaches · both score</div>
              <ul className="fx-dugout-seats">
                {draft.coaches.map((e) => seat(e, "coach"))}
                {emptySeats("coach", rules.squad.coaches - draft.coaches.length, [{ label: "Add coach", filter: "coach" }])}
              </ul>
            </div>
          </div>
          {swapping && (
            <p className="footnote">
              {draft.starters.includes(swapping) ? "Now pick a sub to bring on stage." : "Now pick a starter to swap out."}
            </p>
          )}

          <div className="fx-controls">
          <div className="fx-transfers">
            {transfers.free === null ? (
              <span>Free rebuild: change as many as you like this week.</span>
            ) : (
              <span>
                Transfers: {transfers.made} made, {transfers.free} free
                {transfers.hit ? <strong className="tone-bad"> · −{transfers.hit} points</strong> : null}
              </span>
            )}
          </div>

          <div className="chip-row fx-chips">
            <span className="chip-label">Chips</span>
            {CHIPS.map((c) => {
              const ok = chipAvailable(state, c, week.event_id, order, rules);
              return (
                <button
                  key={c}
                  type="button"
                  role="switch"
                  className="chip"
                  aria-checked={state.chip === c}
                  disabled={!ok}
                  onClick={() => toggleChip(c)}
                  title={ok ? undefined : "Already used this half of the season"}
                >
                  {CHIP_LABEL[c]}
                </button>
              );
            })}
          </div>

          {errors.length > 0 && (
            <ul className="fx-errors" aria-label={complete ? "Rule problems" : "Still to do"}>
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}

          <button type="button" className="fx-cta" disabled={errors.length > 0 || locking} onClick={lock}>
            {locking ? "Playing…" : "Lock squad and play the week"}
          </button>
          </div>
        </section>

        <section className="panel fx-pool" aria-label="Player pool" ref={poolRef}>
          <div className="panel-head">
            <div className="section-title">Pool</div>
            <span className="panel-meta">{rows.length} shown</span>
          </div>
          <div className="chip-row" style={{ marginBottom: 10 }}>
            <span role="radiogroup" aria-label="Filter by role" className="chip-row">
              {ROLE_FILTERS.map((r) => (
                <button key={r} type="button" role="radio" className="chip" aria-checked={role === r} onClick={() => setRole(r)}>
                  {r === "all" ? "All" : roleLabel(r === "coach" ? null : r)}
                </button>
              ))}
            </span>
          </div>
          <div className="chip-row" style={{ marginBottom: 10 }}>
            <select className="chip" value={team} aria-label="Filter by team" onChange={(e) => setTeam(e.target.value)}>
              <option value="all">All teams</option>
              {teams.map((t) => (
                <option key={t} value={t}>
                  {teamName(t)}
                </option>
              ))}
            </select>
            <select className="chip" value={sort} aria-label="Sort" onChange={(e) => setSort(e.target.value)}>
              <option value="price">Sort: price</option>
              <option value="points">Sort: season points</option>
            </select>
            <input
              className="chip fx-search"
              type="search"
              placeholder="Search"
              aria-label="Search players and teams"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="table-scroll">
            <table className="fx-table fx-pool-table">
              <thead>
                <tr>
                  <th className="tl">Name</th>
                  <th className="tl">Role</th>
                  <th>Price</th>
                  <th>Pts</th>
                  <th>
                    <span className="visually-hidden">Pick</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const delta = p.previous_price === null ? 0 : p.price - p.previous_price;
                  return (
                    <tr key={p.entity_id} className={inSquad.has(p.entity_id) ? "fx-picked" : undefined}>
                      <td className="tl">
                        <a href={`#/fantasy/player/${p.entity_id}`}>{p.handle}</a>
                        <div className="fx-sub">{teamName(p.team_id)}</div>
                      </td>
                      <td className="tl">{roleLabel(p.listed_role)}</td>
                      <td className="mono">
                        {fmtPrice(p.price)}
                        {delta !== 0 && (
                          <span className={delta > 0 ? "tone-good fx-delta" : "tone-bad fx-delta"}>
                            {delta > 0 ? "▲" : "▼"}
                          </span>
                        )}
                      </td>
                      <td className="mono">{fmtPoints(totals[p.entity_id] ?? 0)}</td>
                      <td>
                        {inSquad.has(p.entity_id) ? (
                          <button type="button" className="table-toggle" onClick={() => remove(p.entity_id)}>
                            Drop
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="table-toggle"
                            disabled={!canAdd(p.entity_id)}
                            onClick={() => add(p.entity_id)}
                            aria-label={`Add ${p.handle}`}
                          >
                            Add
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="footnote">
            Prices are set before each event and move on form. Pts are season points from the weeks
            you've played.
          </p>
        </section>
      </div>
    </>
  );
}

/** Coaches have no agent, so their screen shows a tactics board instead of a role. */
function CoachGlyph() {
  return (
    <span className="role-glyph" style={{ "--glyph": "var(--ink-muted)" }} aria-hidden="true">
      <svg width="30" height="30" viewBox="0 0 28 28" fill="none">
        <path
          d="M2 2 L26 2 L26 20 L20 26 L2 26 Z"
          fill="color-mix(in srgb, var(--glyph) 12%, transparent)"
          stroke="color-mix(in srgb, var(--glyph) 55%, transparent)"
          strokeWidth="1"
        />
        <path d="M7 8 L11 12 M11 8 L7 12" stroke="var(--glyph)" strokeWidth="1.8" />
        <circle cx="19" cy="18" r="2.6" stroke="var(--glyph)" strokeWidth="1.8" />
        <path d="M11 15 Q13 20 16.5 18.5" stroke="var(--glyph)" strokeWidth="1.5" strokeDasharray="2 1.6" />
      </svg>
    </span>
  );
}
