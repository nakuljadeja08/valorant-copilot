import { useState } from "react";

import { useJson } from "../../lib/data.js";
import { fmtPoints, pointsAsClaim } from "../../lib/fantasy.js";
import ClaimCard from "../TraceView.jsx";

/* One entity's maps in one week, each opening into the same decision trace the
   coaching claims use: points -> scoring rule -> feature row -> raw rounds. Traces
   are fetched per map, only when opened. */
export default function EntityMaps({ entity, label, maps, dir }) {
  const [open, setOpen] = useState(false);
  if (!maps?.length) return null;

  return (
    <div className="fx-maps">
      <button type="button" className="disclose" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide maps" : `Show ${maps.length} map${maps.length === 1 ? "" : "s"} and where the points came from`}
      </button>
      {open && maps.map((m) => <MapTrace key={m.match_id} matchId={m.match_id} entity={entity} label={label} dir={dir} />)}
    </div>
  );
}

function MapTrace({ matchId, entity, label, dir }) {
  const { data: trace, error } = useJson(`fantasy/traces/${matchId}.json`);
  if (error) return <p className="footnote">Could not load this map's trace.</p>;
  if (!trace) return <p className="footnote">Loading map…</p>;
  if (!trace.points[entity]) return <p className="footnote">No verified points on this map.</p>;

  const p = trace.points[entity];
  // The opponent, from the side this entity was on: players by the map's roster,
  // coaches by their team.
  const side =
    trace.players.find((x) => x.puuid === entity)?.side ??
    (trace.teams.Red === dir.people[entity]?.team_id ? "Red" : "Blue");
  const opponent = dir.teams[trace.teams[side === "Red" ? "Blue" : "Red"]]?.name;
  return (
    <div className="fx-map">
      <div className="fx-map-head">
        <span className="section-title">
          {trace.map_name} · map {trace.map_num}
        </span>
        <span className="fx-sub fx-map-vs">
          vs {opponent} · {trace.winner === trace.teams[side] ? "won" : "lost"}
        </span>
        <span className="mono">{fmtPoints(p.total)} pts</span>
      </div>
      <ul className="fx-breakdown">
        {p.components.map((c) => (
          <li key={c.rule}>
            <span>{c.rule.replace(/_/g, " ")}</span>
            <span className="mono">
              {c.count} × {c.points_each} = {fmtPoints(c.value)}
            </span>
          </li>
        ))}
      </ul>
      <ClaimCard conclusion={pointsAsClaim(trace, entity, label)} />
    </div>
  );
}
