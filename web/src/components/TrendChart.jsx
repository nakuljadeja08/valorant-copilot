import { useState } from "react";

import { pct, useWidth } from "../lib/data.js";

/* Force-buy rate per match, against the habit threshold.

   Structure is copied from EconomyChart deliberately: same margin object, same
   x()/y() scales, same pointer + arrow-key selection, same tooltip, same table
   twin. One chart idiom in the app, not four.

   Outcome is encoded twice — fill AND shape (circle won, diamond lost). A
   twelve-point series split red/green by fill alone is the textbook CVD
   failure, and the two markers here sit right on top of each other. */

const M = { top: 16, right: 46, bottom: 30, left: 44 };
const PLOT_H = 168;

export default function TrendChart({ matches, threshold = 0.3 }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const [showTable, setShowTable] = useState(false);

  const points = matches
    .filter((m) => m.force_rate !== null && m.force_rate !== undefined)
    .map((m) => ({
      id: m.match_id,
      map: m.map_name,
      rate: m.force_rate,
      won: m.winner && m.hero_team ? m.winner === m.hero_team : null,
    }));

  const w = Math.max(width, 320);
  const innerW = Math.max(w - M.left - M.right, 80);
  const yMax = Math.max(0.6, Math.ceil(Math.max(...points.map((p) => p.rate), 0) * 10) / 10);
  const last = points.length - 1;
  const x = (i) => M.left + (points.length < 2 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const y = (v) => M.top + PLOT_H - (Math.max(v, 0) / yMax) * PLOT_H;

  const over = points.filter((p) => p.rate > threshold).length;

  function pick(clientX, target) {
    const box = target.getBoundingClientRect();
    const i = Math.round(((clientX - box.left - M.left) / innerW) * last);
    setActive(Math.min(Math.max(i, 0), last));
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && active !== null) {
      window.location.hash = `#/match/${points[active].id}`;
      return;
    }
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setActive(Math.min(Math.max((active ?? 0) + (e.key === "ArrowRight" ? 1 : -1), 0), last));
  }

  const a = active === null ? null : points[active];

  if (!points.length) return null;

  return (
    <section className="panel" data-chart="force-trend">
      <div className="panel-head">
        <h2 className="section-title">Force-buy rate per match</h2>
        <button className="table-toggle" onClick={() => setShowTable((v) => !v)}>
          {showTable ? "Chart view" : "Table view"}
        </button>
      </div>

      {showTable ? (
        <TrendTable points={points} threshold={threshold} />
      ) : (
        <div className="plot-wrap" ref={ref}>
          <svg
            width={w}
            height={M.top + PLOT_H + M.bottom}
            role="img"
            tabIndex={0}
            aria-label={`Line chart of force-buy rate across ${points.length} matches against a ${pct(threshold)} threshold. ${over} matches are over the line. Use the table view for exact values.`}
            onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
            onPointerLeave={() => setActive(null)}
            onKeyDown={onKeyDown}
            onFocus={() => setActive((v) => v ?? 0)}
            onBlur={() => setActive(null)}
            style={{ display: "block", touchAction: "pan-y" }}
          >
            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={y(0)}
              y2={y(0)}
              stroke="var(--axis)"
              strokeWidth="1"
            />
            <text x={M.left - 8} y={y(0) + 4} textAnchor="end" fontSize="10" fill="var(--ink-faint)">
              0
            </text>
            <text
              x={M.left - 8}
              y={y(yMax) + 4}
              textAnchor="end"
              fontSize="10"
              fill="var(--ink-faint)"
            >
              {pct(yMax)}
            </text>

            {/* habit threshold */}
            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={y(threshold)}
              y2={y(threshold)}
              stroke="var(--warn)"
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <text x={M.left + innerW + 6} y={y(threshold) + 4} fontSize="10" fill="var(--warn)">
              {pct(threshold)}
            </text>

            <path
              d={points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)} ${y(p.rate)}`).join(" ")}
              fill="none"
              stroke="var(--ink-muted)"
              strokeWidth="2"
              strokeLinejoin="round"
            />

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

            {points.map((p, i) =>
              p.won === false ? (
                <path
                  key={p.id}
                  d={`M${x(i)} ${y(p.rate) - 5} l-5 5 5 5 5 -5 z`}
                  fill="var(--bad)"
                  stroke="var(--surface-panel)"
                  strokeWidth="1.5"
                />
              ) : (
                <circle
                  key={p.id}
                  cx={x(i)}
                  cy={y(p.rate)}
                  r="4"
                  fill={p.won ? "var(--good)" : "var(--ink-neutral)"}
                  stroke="var(--surface-panel)"
                  strokeWidth="1.5"
                />
              ),
            )}
          </svg>

          {a && (
            <div
              className="tooltip"
              style={{ left: Math.min(Math.max(x(active) - 74, 0), Math.max(w - 160, 0)), top: 0 }}
            >
              <div className="tooltip-title">
                {a.map}
                {a.won === null ? "" : a.won ? " · won" : " · lost"}
              </div>
              <div className="tooltip-row">
                <span className="tooltip-name">Force-buy rate</span>
                <span className="tooltip-val">{pct(a.rate)}</span>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="legend" style={{ marginTop: 8 }}>
        <span className="key">
          <span className="key-dot" style={{ background: "var(--good)" }} aria-hidden="true" />
          won
        </span>
        <span className="key">
          <span
            className="diamond"
            style={{ background: "var(--bad)", width: 9, height: 9 }}
            aria-hidden="true"
          />
          lost
        </span>
        <span style={{ marginLeft: "auto", color: "var(--ink-faint)" }}>
          {over} of {points.length} matches over the line
        </span>
      </div>
    </section>
  );
}

function TrendTable({ points, threshold }) {
  return (
    <div className="table-scroll">
      <table>
        <caption className="footnote" style={{ textAlign: "left", captionSide: "top" }}>
          Force-buy rate per match
        </caption>
        <thead>
          <tr>
            <th scope="col">Map</th>
            <th scope="col">Force-buy rate</th>
            <th scope="col">Over {pct(threshold)}</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.id}>
              <td className="tl">{p.map}</td>
              <td>{pct(p.rate)}</td>
              <td>{p.rate > threshold ? "yes" : "no"}</td>
              <td>{p.won === null ? "—" : p.won ? "won" : "lost"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
