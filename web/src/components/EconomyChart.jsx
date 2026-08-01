import { useState } from "react";

import { fmt, useWidth } from "../lib/data.js";

/* Two series, one y-axis (credits). Never a second axis: bank and spend are
   both credits, so they share the scale honestly; anything measured in other
   units gets its own chart rather than a twinned scale. */

const M = { top: 16, right: 68, bottom: 34, left: 54 };
const PLOT_H = 240;
const TEAMS = [
  { id: "Blue", color: "var(--team-blue)" },
  { id: "Red", color: "var(--team-red)" },
];

function niceCeil(value) {
  if (value <= 0) return 1000;
  const step = value > 20000 ? 5000 : value > 8000 ? 2000 : 1000;
  return Math.ceil(value / step) * step;
}

export default function EconomyChart({ rounds, pivotalRound }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const [showTable, setShowTable] = useState(false);

  const points = rounds.map((r) => ({
    round: r.round_num,
    winner: r.winning_team,
    Blue: r.economy.Blue.spend,
    Red: r.economy.Red.spend,
    buys: { Blue: r.economy.Blue.buy_type, Red: r.economy.Red.buy_type },
  }));

  const w = Math.max(width, 320);
  const innerW = Math.max(w - M.left - M.right, 80);
  const yMax = niceCeil(
    Math.max(...points.flatMap((p) => [p.Blue ?? 0, p.Red ?? 0]), 0),
  );
  const x = (i) => M.left + (points.length < 2 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const y = (v) => M.top + PLOT_H - (Math.max(v ?? 0, 0) / yMax) * PLOT_H;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f));
  const path = (team) =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)} ${y(p[team])}`).join(" ");

  const lastIdx = points.length - 1;
  const endGap = Math.abs(y(points[lastIdx]?.Blue) - y(points[lastIdx]?.Red));
  // End labels only when the lines separate at the right edge. Nudging collided
  // labels apart detaches them from their line, so they drop to legend+tooltip.
  const showEndLabels = endGap >= 16;

  const pivotIdx = points.findIndex((p) => p.round === pivotalRound);

  function pick(clientX, target) {
    const box = target.getBoundingClientRect();
    const rel = clientX - box.left - M.left;
    const i = Math.round((rel / innerW) * (points.length - 1));
    setActive(Math.min(Math.max(i, 0), lastIdx));
  }

  function onKeyDown(e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const next = (active ?? 0) + (e.key === "ArrowRight" ? 1 : -1);
    setActive(Math.min(Math.max(next, 0), lastIdx));
  }

  const a = active === null ? null : points[active];

  return (
    <section className="card">
      <div className="card-head">
        <h2 style={{ fontSize: 15 }}>Round spend</h2>
        <button className="table-toggle" onClick={() => setShowTable((v) => !v)}>
          {showTable ? "Chart view" : "Table view"}
        </button>
      </div>
      <p className="card-sub">
        Credits each team spent entering each round, summed across its five players.
      </p>

      <div className="legend" style={{ marginBottom: 8 }}>
        {TEAMS.map((t) => (
          <span className="key" key={t.id}>
            <span className="key-line" style={{ background: t.color }} aria-hidden="true" />
            {t.id}
          </span>
        ))}
        {pivotIdx >= 0 && (
          <span className="key" style={{ color: "var(--muted)" }}>
            <span
              className="key-line"
              style={{ background: "var(--axis)", width: 2, height: 12 }}
              aria-hidden="true"
            />
            Pivotal round (R{pivotalRound})
          </span>
        )}
      </div>

      {showTable ? (
        <EconomyTable points={points} />
      ) : (
        <div className="plot-wrap" ref={ref}>
          <svg
            width={w}
            height={M.top + PLOT_H + M.bottom}
            role="img"
            tabIndex={0}
            aria-label={`Line chart of credits spent per round by Blue and Red across ${points.length} rounds. Use the table view for exact values.`}
            onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
            onPointerLeave={() => setActive(null)}
            onKeyDown={onKeyDown}
            onFocus={() => setActive((v) => v ?? 0)}
            onBlur={() => setActive(null)}
            style={{ display: "block", touchAction: "pan-y" }}
          >
            {/* gridlines: solid hairlines, one step off the surface */}
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={M.left}
                  x2={M.left + innerW}
                  y1={y(t)}
                  y2={y(t)}
                  stroke="var(--grid)"
                  strokeWidth="1"
                />
                <text
                  x={M.left - 10}
                  y={y(t) + 4}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {t.toLocaleString("en-US")}
                </text>
              </g>
            ))}

            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={y(0)}
              y2={y(0)}
              stroke="var(--axis)"
              strokeWidth="1"
            />

            {pivotIdx >= 0 && (
              <line
                x1={x(pivotIdx)}
                x2={x(pivotIdx)}
                y1={M.top}
                y2={M.top + PLOT_H}
                stroke="var(--axis)"
                strokeWidth="2"
              />
            )}

            {/* x ticks: every other round, so labels never collide */}
            {points.map((p, i) =>
              i % 2 === 0 ? (
                <text
                  key={p.round}
                  x={x(i)}
                  y={M.top + PLOT_H + 20}
                  textAnchor="middle"
                  fontSize="11"
                  fill="var(--muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {p.round}
                </text>
              ) : null,
            )}
            <text
              x={M.left + innerW / 2}
              y={M.top + PLOT_H + 34}
              textAnchor="middle"
              fontSize="11"
              fill="var(--muted)"
            >
              round
            </text>

            {a && (
              <line
                x1={x(active)}
                x2={x(active)}
                y1={M.top}
                y2={M.top + PLOT_H}
                stroke="var(--axis)"
                strokeWidth="1"
              />
            )}

            {TEAMS.map((t) => (
              <path
                key={t.id}
                d={path(t.id)}
                fill="none"
                stroke={t.color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}

            {/* end markers carry a 2px surface ring so they stay legible where
                the two lines cross */}
            {TEAMS.map((t) => (
              <circle
                key={t.id}
                cx={x(lastIdx)}
                cy={y(points[lastIdx]?.[t.id])}
                r="4"
                fill={t.color}
                stroke="var(--surface)"
                strokeWidth="2"
              />
            ))}

            {showEndLabels &&
              TEAMS.map((t) => (
                <text
                  key={t.id}
                  x={x(lastIdx) + 10}
                  y={y(points[lastIdx]?.[t.id]) + 4}
                  fontSize="11"
                  fill="var(--ink-2)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {fmt(points[lastIdx]?.[t.id])}
                </text>
              ))}

            {a &&
              TEAMS.map((t) => (
                <circle
                  key={t.id}
                  cx={x(active)}
                  cy={y(a[t.id])}
                  r="4"
                  fill={t.color}
                  stroke="var(--surface)"
                  strokeWidth="2"
                />
              ))}
          </svg>

          {a && (
            <div
              className="tooltip"
              style={{
                left: Math.min(Math.max(x(active) - 74, 0), Math.max(w - 160, 0)),
                top: 0,
              }}
            >
              <div className="tooltip-title">
                Round {a.round}
                {a.winner ? ` · ${a.winner} won` : ""}
              </div>
              {TEAMS.map((t) => (
                <div className="tooltip-row" key={t.id}>
                  <span className="tooltip-name">
                    <span
                      className="key-line"
                      style={{ background: t.color }}
                      aria-hidden="true"
                    />
                    {t.id}
                    {a.buys[t.id] ? ` · ${a.buys[t.id]}` : ""}
                  </span>
                  <span className="tooltip-val">{fmt(a[t.id])}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function EconomyTable({ points }) {
  return (
    <div className="table-scroll">
      <table>
        <caption className="card-sub" style={{ textAlign: "left", captionSide: "top" }}>
          Credits spent per round
        </caption>
        <thead>
          <tr>
            <th scope="col">Round</th>
            <th scope="col">Blue spend</th>
            <th scope="col">Blue buy</th>
            <th scope="col">Red spend</th>
            <th scope="col">Red buy</th>
            <th scope="col">Won by</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.round}>
              <td>{p.round}</td>
              <td>{fmt(p.Blue)}</td>
              <td>{p.buys.Blue ?? "—"}</td>
              <td>{fmt(p.Red)}</td>
              <td>{p.buys.Red ?? "—"}</td>
              <td>{p.winner ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
