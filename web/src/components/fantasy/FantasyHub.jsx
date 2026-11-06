import { CHIPS, CHIP_LABEL, chipAvailable, fmtPoints, standings } from "../../lib/fantasy.js";
import Tile from "../Tile.jsx";
import { regionLabel } from "./FantasyLanding.jsx";

export const dateOf = (ms) => new Date(ms).toISOString().slice(0, 10);

/* Where the season stands: your total, your rank, what's next, and every week so far. */
export default function FantasyHub({ season, rivals, state, setState, weeks }) {
  const next = weeks[state.cursor];
  const done = !next;
  const table = standings(state, rivals);
  const me = table.find((t) => t.you);
  const order = season.events.map((e) => e.event_id);
  const chipEvent = next?.event_id ?? order.at(-1);
  const chipsLeft = CHIPS.filter((c) => chipAvailable(state, c, chipEvent, order, season.rules));

  const reset = () => {
    if (window.confirm("Start a new season? Your squads and points will be cleared.")) setState(null);
  };

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">{regionLabel(state.region)} · simulated VCT 2027</div>
          <h1 className="page-title">Your season</h1>
        </div>
      </header>

      <div className="section kpi-grid fx-kpis">
        <Tile label="Season points" value={fmtPoints(me.total)} foot={`${state.history.length} weeks played`} tone="good" />
        <Tile label="League rank" value={`${me.rank} / ${table.length}`} foot={`${regionLabel(state.region)} league`} />
        <Tile
          label="Last week"
          value={fmtPoints(me.last)}
          foot={state.history.length ? state.history.at(-1).key : "nothing played yet"}
        />
        <Tile
          label="Chips left"
          value={chipsLeft.length}
          foot={chipsLeft.length ? chipsLeft.map((c) => CHIP_LABEL[c]).join(", ") : "none this half"}
        />
      </div>

      <div className="section panel fx-next">
        {done ? (
          <>
            <div className="section-title">Season complete</div>
            <p className="lede">
              You finished {me.rank} of {table.length} with {fmtPoints(me.total)} points.
            </p>
          </>
        ) : (
          <>
            <div className="panel-head">
              <div>
                <div className="eyebrow">Next up</div>
                <div className="section-title">
                  {next.event.name} · week {next.week_num}
                </div>
              </div>
              <span className="panel-meta">deadline {dateOf(next.deadline_ms)} (simulated)</span>
            </div>
            <p className="lede">
              {next.first
                ? `A new event, so this week is a free rebuild${
                    next.event.kind === "international"
                      ? `, and you can pick from every qualified team.`
                      : ` from ${regionLabel(state.region)} teams.`
                  }`
                : `${state.free} free transfer${state.free === 1 ? "" : "s"} available. Each extra one costs ${season.rules.transfers.hit} points.`}
            </p>
            <a className="fx-cta" href="#/fantasy/squad">
              {state.history.length ? "Pick this week's squad" : "Build your squad"}
            </a>
          </>
        )}
      </div>

      <div className="section fx-two">
        <div className="panel">
          <div className="panel-head">
            <div className="section-title">League</div>
            <span className="panel-meta">you vs 8 simulated rivals</span>
          </div>
          <div className="table-scroll">
            <table className="fx-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th className="tl">Manager</th>
                  <th>Last</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {table.map((r) => (
                  <tr key={r.id} className={r.you ? "fx-you" : undefined}>
                    <td>{r.rank}</td>
                    <td className="tl">{r.name}</td>
                    <td>{fmtPoints(r.last)}</td>
                    <td>{fmtPoints(r.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote">{rivals.note}</p>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="section-title">Your weeks</div>
            <span className="panel-meta">
              {state.history.length} of {weeks.length}
            </span>
          </div>
          {state.history.length ? (
            <div className="table-scroll">
              <table className="fx-table">
                <thead>
                  <tr>
                    <th className="tl">Week</th>
                    <th>Points</th>
                    <th>Hit</th>
                    <th className="tl">Chip</th>
                  </tr>
                </thead>
                <tbody>
                  {[...state.history].reverse().map((h) => (
                    <tr key={h.key}>
                      <td className="tl">
                        <a href={`#/fantasy/week/${h.key}`}>{h.key}</a>
                      </td>
                      <td>{fmtPoints(h.net)}</td>
                      <td>{h.hit ? `−${h.hit}` : "—"}</td>
                      <td className="tl">{h.chip ? CHIP_LABEL[h.chip] : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">No weeks played yet.</p>
          )}
        </div>
      </div>

      <button type="button" className="table-toggle" onClick={reset}>
        Start a new season
      </button>
    </>
  );
}
