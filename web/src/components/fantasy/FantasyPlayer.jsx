import { useEffect, useState } from "react";

import { loadJson } from "../../lib/data.js";
import { fmtPoints, fmtPrice, roleLabel } from "../../lib/fantasy.js";
import EntityMaps from "./EntityMaps.jsx";
import { usePlayedWeeks } from "./usePlayed.js";

/* One player or coach: price at each event, and points from the weeks you've played.
   Later weeks stay hidden so the replay keeps its results to itself. */
export default function FantasyPlayer({ season, state, dir, entity }) {
  const person = dir.people[entity];
  const played = usePlayedWeeks((state?.history ?? []).map((h) => h.key));
  const [prices, setPrices] = useState(null);

  useEffect(() => {
    let live = true;
    Promise.all(season.events.map((e) => loadJson(`fantasy/players/${e.event_id}.json`))).then(
      (pools) => {
        if (!live) return;
        setPrices(
          pools.map((p, i) => ({
            event: season.events[i],
            row: p.pool.find((x) => x.entity_id === entity) ?? null,
          })),
        );
      },
    );
    return () => {
      live = false;
    };
  }, [season, entity]);

  if (!person) return <p className="empty">No player or coach with that id.</p>;

  const weeks = (state?.history ?? [])
    .map((h) => ({ key: h.key, data: played[h.key]?.entities[entity] }))
    .filter((w) => w.data);
  const total = weeks.reduce((n, w) => n + w.data.total, 0);
  const teamId = person.team_id ?? prices?.findLast((p) => p.row)?.row.team_id;

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">
            {roleLabel(person.role)} · {dir.teams[teamId]?.name ?? "No team this season"} · fictional
          </div>
          <h1 className="page-title">{person.handle}</h1>
          <p className="lede" style={{ margin: "8px 0 0" }}>
            {state
              ? `${fmtPoints(total)} points across the ${state.history.length} weeks you've played.`
              : "Start a season to see points as the weeks are played."}
          </p>
        </div>
      </header>

      <div className="section fx-two">
        <div className="panel">
          <div className="section-title">Price by event</div>
          <div className="table-scroll">
            <table className="fx-table">
              <thead>
                <tr>
                  <th className="tl">Event</th>
                  <th className="tl">Team</th>
                  <th className="tl">Role</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {(prices ?? []).map(({ event, row }) => (
                  <tr key={event.event_id}>
                    <td className="tl">{event.name}</td>
                    <td className="tl">{row ? dir.teams[row.team_id]?.name : "Didn't qualify"}</td>
                    <td className="tl">{row ? roleLabel(row.listed_role) : "—"}</td>
                    <td className="mono">{row ? fmtPrice(row.price) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="section-title">Points by week</div>
          {weeks.length ? (
            <ul className="fx-results">
              {weeks.map((w) => (
                <li key={w.key} className="fx-result">
                  <div className="fx-result-line">
                    <span className="fx-slot-name">
                      <a href={`#/fantasy/week/${w.key}`}>{w.key}</a>
                    </span>
                    <span className="fx-result-pts mono">{fmtPoints(w.data.total)}</span>
                  </div>
                  <EntityMaps entity={entity} label={person.handle} maps={w.data.maps} dir={dir} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">No points in the weeks played so far.</p>
          )}
        </div>
      </div>
    </>
  );
}
