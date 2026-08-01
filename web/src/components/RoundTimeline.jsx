import { useState } from "react";

import { fmt } from "../lib/data.js";

/* Who won each round, and what they walked in with.
   The winner is encoded by POSITION (which team's band is filled) as well as by
   hue, so the strip does not rely on color alone; the buy type is printed in the
   band, so no value is gated behind the tooltip. */

const COL = 36;
const GAP = 2;
const RAIL = 62;
const BUY_ABBR = { eco: "ECO", force: "FRC", half: "HLF", full: "FUL" };

export default function RoundTimeline({ rounds, pivotalRound }) {
  const [active, setActive] = useState(null);
  const [showTable, setShowTable] = useState(false);

  const a = active === null ? null : rounds[active];

  function onKeyDown(e, i) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const next = Math.min(Math.max(i + (e.key === "ArrowRight" ? 1 : -1), 0), rounds.length - 1);
    setActive(next);
    e.currentTarget.parentElement.children[next]?.focus();
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2 style={{ fontSize: 15 }}>Round timeline</h2>
        <button className="table-toggle" onClick={() => setShowTable((v) => !v)}>
          {showTable ? "Timeline view" : "Table view"}
        </button>
      </div>
      <p className="card-sub">
        A filled band is a round won. The label is that team&apos;s buy classification.
      </p>

      {showTable ? (
        <RoundTable rounds={rounds} />
      ) : (
        <div className="timeline-scroll">
          <div style={{ position: "relative", display: "flex" }}>
            <div className="timeline-rail" style={{ width: RAIL }}>
              <div className="rail-spacer" />
              <div className="rail-pivot" />
              <div className="rail-label">
                <span className="key-dot blue" aria-hidden="true" />
                Blue
              </div>
              <div className="rail-label">
                <span className="key-dot red" aria-hidden="true" />
                Red
              </div>
            </div>

            <div className="timeline" role="group" aria-label="Round outcomes">
              {rounds.map((r, i) => (
                <button
                  className="round-col"
                  key={r.round_num}
                  tabIndex={i === (active ?? 0) ? 0 : -1}
                  aria-label={`Round ${r.round_num}, won by ${r.winning_team ?? "nobody"}, ${r.round_result ?? "unknown result"}`}
                  onPointerEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  onKeyDown={(e) => onKeyDown(e, i)}
                  onPointerLeave={() => setActive(null)}
                >
                  <span className="round-num">{r.round_num}</span>
                  <span className="round-pivot">
                    {r.round_num === pivotalRound && <span aria-hidden="true" />}
                  </span>
                  {["Blue", "Red"].map((team) => (
                    <span
                      key={team}
                      className={[
                        "band",
                        r.winning_team === team ? "won" : "",
                        team === "Blue" ? "b" : "r",
                      ].join(" ")}
                    >
                      {BUY_ABBR[r.economy[team].buy_type] ?? ""}
                    </span>
                  ))}
                </button>
              ))}
            </div>

            {a && (
              <div
                className="tooltip"
                style={{
                  left: Math.min(RAIL + active * (COL + GAP), RAIL + (rounds.length - 4) * (COL + GAP)),
                  top: 62,
                }}
              >
                <div className="tooltip-title">
                  Round {a.round_num}
                  {a.round_num === pivotalRound ? " · pivotal" : ""}
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-name">Won by</span>
                  <span className="tooltip-val">{a.winning_team ?? "—"}</span>
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-name">Result</span>
                  <span className="tooltip-val">{a.round_result ?? "—"}</span>
                </div>
                {a.plant_site && (
                  <div className="tooltip-row">
                    <span className="tooltip-name">Plant</span>
                    <span className="tooltip-val">site {a.plant_site}</span>
                  </div>
                )}
                {["Blue", "Red"].map((team) => (
                  <div className="tooltip-row" key={team}>
                    <span className="tooltip-name">
                      <span
                        className={`key-dot ${team === "Blue" ? "blue" : "red"}`}
                        aria-hidden="true"
                      />
                      {team} bank
                    </span>
                    <span className="tooltip-val">{fmt(a.economy[team].bank)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function RoundTable({ rounds }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Round</th>
            <th scope="col">Won by</th>
            <th scope="col" className="tl">
              Result
            </th>
            <th scope="col">Plant site</th>
            <th scope="col">Blue buy</th>
            <th scope="col">Red buy</th>
          </tr>
        </thead>
        <tbody>
          {rounds.map((r) => (
            <tr key={r.round_num}>
              <td>{r.round_num}</td>
              <td>{r.winning_team ?? "—"}</td>
              <td className="tl">{r.round_result ?? "—"}</td>
              <td>{r.plant_site ?? "—"}</td>
              <td>{r.economy.Blue.buy_type ?? "—"}</td>
              <td>{r.economy.Red.buy_type ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
