import { useJson } from "../../lib/data.js";
import {
  CHIP_LABEL,
  armbandHolder,
  fieldedPlayers,
  fmtPoints,
  roleLabel,
  standings,
} from "../../lib/fantasy.js";
import EntityMaps from "./EntityMaps.jsx";

/* One played week: who scored, who sat out, the armband, the chip and the hit, with
   every player's points opening into their trace. */
export default function FantasyWeek({ season, rivals, state, dir, weekKey }) {
  const entry = state.history.find((h) => h.key === weekKey);
  const { data: week } = useJson(`fantasy/points/${weekKey}.json`);

  if (!entry) {
    return (
      <p className="empty">
        This week hasn't been played yet. <a href="#/fantasy">Back to your season</a>.
      </p>
    );
  }
  if (!week) return <p className="empty">Loading…</p>;

  const event = season.events.find((e) => e.event_id === entry.event_id);
  const squad = entry.squad;
  const points = Object.fromEntries(Object.entries(week.entities).map(([e, v]) => [e, v.total]));
  const fielded = new Set(fieldedPlayers(squad, points, entry.chip));
  const band = armbandHolder(squad, points);
  const multiplier =
    entry.chip === "triple_captain"
      ? season.rules.chips.triple_captain.captain_multiplier
      : season.rules.squad.captain_multiplier;
  const upTo = state.history.slice(0, state.history.indexOf(entry) + 1);
  const table = standings({ ...state, history: upTo }, rivals);
  const me = table.find((t) => t.you);
  const isLatest = entry === state.history.at(-1);

  const status = (e, onBench) => {
    if (!(e in points)) return "Played no map";
    if (onBench) return fielded.has(e) ? (entry.chip === "bench_boost" ? "Bench Boost" : "Auto-subbed in") : "On the bench";
    return fielded.has(e) ? "Played" : "Played no map";
  };

  const row = (e, onBench = false) => {
    const person = dir.people[e];
    const p = week.entities[e];
    const counts = fielded.has(e) || person.kind === "coach";
    const shown = counts ? (points[e] ?? 0) * (e === band ? multiplier : 1) : 0;
    return (
      <li key={e} className={`fx-result${counts ? "" : " fx-result-out"}`}>
        <div className="fx-result-line">
          <span className="fx-slot-role">{roleLabel(person.role)}</span>
          <span className="fx-slot-name">
            <a href={`#/fantasy/player/${e}`}>{person.handle}</a>
            {e === squad.captain && <span className="fx-band">C</span>}
            {e === squad.vice && <span className="fx-band fx-band-vice">V</span>}
            <span className="fx-slot-team">{person.kind === "coach" ? "Coach" : status(e, onBench)}</span>
          </span>
          <span className="fx-result-pts mono">
            {fmtPoints(shown)}
            {e === band && counts && <span className="fx-sub"> ×{multiplier}</span>}
          </span>
        </div>
        <EntityMaps entity={e} label={person.handle} maps={p?.maps} dir={dir} />
      </li>
    );
  };

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">
            {event.name} · week {entry.week_num}
            {entry.chip ? ` · ${CHIP_LABEL[entry.chip]}` : ""}
          </div>
          <h1 className="page-title">{fmtPoints(entry.net)} points</h1>
          <p className="lede" style={{ margin: "8px 0 0" }}>
            Players {fmtPoints(entry.score.players)} · captain bonus {fmtPoints(entry.score.captain_bonus)} ·
            coaches {fmtPoints(entry.score.coaches)}
            {entry.hit ? ` · transfers −${entry.hit}` : ""}. You're {me.rank} of {table.length} in your league.
          </p>
        </div>
      </header>

      {isLatest && state.cursor < season.events.reduce((n, e) => n + e.weeks.length, 0) && (
        <a className="fx-cta section" href="#/fantasy/squad">
          On to the next week
        </a>
      )}

      <div className="section panel">
        <div className="section-title">Starters</div>
        <ul className="fx-results">{squad.starters.map((e) => row(e))}</ul>
        <div className="section-title fx-group">Bench</div>
        <ul className="fx-results">{squad.subs.map((e) => row(e, true))}</ul>
        <div className="section-title fx-group">Coaches</div>
        <ul className="fx-results">{squad.coaches.map((e) => row(e))}</ul>
        <p className="footnote">
          Every point was recomputed from the kill timeline before it was published. Open a map to
          see the rule behind each line and the rounds it came from.
        </p>
      </div>
    </>
  );
}
