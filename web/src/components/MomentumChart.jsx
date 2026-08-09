import { useState } from "react";

import { useWidth } from "../lib/data.js";

/* The per-round momentum proxy, annotated with the events that moved it.

   IMPORTANT — this is NOT a win-probability chart, and the copy here must not
   drift into calling it one. src/features/pivotal_round.py is explicit: the
   value "is not a calibrated probability -- it's a bounded momentum index used
   only to rank rounds against each other within one match." So:

     - the title says "momentum index", never "win probability"
     - the axis reads 0.0 / 0.5 / 1.0, never percentages; a % sign is what makes
       a reader treat a number as a probability
     - the tooltip reads "proxy 0.62"
     - the disclaimer comes from the bundle (provenance.proxy_note), so it
       cannot drift from the feature that produced it

   The pivotal-round *swing* keeps its percentage phrasing elsewhere: a
   difference between two index values is an honest thing to state. */

const M = { top: 20, right: 20, bottom: 30, left: 44 };
const PLOT_H = 200;

export default function MomentumChart({ rounds, pivotalRound, team, proxyNote }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const [showTable, setShowTable] = useState(false);

  const points = rounds
    .map((r) => ({
      round: r.round_num,
      value: r.economy?.[team]?.win_prob_proxy,
      broken: r.economy?.[team]?.broken_buy === 1,
      pivotal: r.pivotal,
      winner: r.winning_team,
    }))
    .filter((p) => p.value !== null && p.value !== undefined);

  // A shutout has no proxy series at all — the feature declines to rank rounds
  // when only one side ever won one. Nothing to draw.
  if (points.length < 2) return null;

  const w = Math.max(width, 320);
  const innerW = Math.max(w - M.left - M.right, 80);
  const last = points.length - 1;
  const x = (i) => M.left + (i * innerW) / last;
  const y = (v) => M.top + PLOT_H - v * PLOT_H;

  const pivotIdx = points.findIndex((p) => p.round === pivotalRound);
  const brokenRounds = points.filter((p) => p.broken).map((p) => p.round);

  function pick(clientX, target) {
    const box = target.getBoundingClientRect();
    const i = Math.round(((clientX - box.left - M.left) / innerW) * last);
    setActive(Math.min(Math.max(i, 0), last));
  }

  function onKeyDown(e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setActive(Math.min(Math.max((active ?? 0) + (e.key === "ArrowRight" ? 1 : -1), 0), last));
  }

  const a = active === null ? null : points[active];
  const accent = team === "Red" ? "var(--team-red)" : "var(--team-blue)";

  return (
    <section className="panel section" data-chart="momentum">
      <div className="panel-head">
        <div>
          <h2 className="section-title">Momentum index, round by round</h2>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="legend">
            <span className="key">
              <span className="key-line" style={{ background: accent }} aria-hidden="true" />
              {team} momentum (proxy)
            </span>
            <span className="key">
              <span
                className="diamond"
                style={{ background: "var(--bad)", width: 8, height: 8 }}
                aria-hidden="true"
              />
              broken buy
            </span>
            <span className="key">
              <span className="key-bar" style={{ background: "var(--warn)" }} aria-hidden="true" />
              pivotal round
            </span>
          </div>
          <button className="table-toggle" onClick={() => setShowTable((v) => !v)}>
            {showTable ? "Chart view" : "Table view"}
          </button>
        </div>
      </div>

      {showTable ? (
        <MomentumTable points={points} team={team} />
      ) : (
        <div className="plot-wrap" ref={ref}>
          <svg
            width={w}
            height={M.top + PLOT_H + M.bottom}
            role="img"
            tabIndex={0}
            aria-label={`Line chart of the ${team} momentum proxy across ${points.length} rounds, on a 0 to 1 scale. This is a bounded momentum index, not a win probability. Use the table view for exact values.`}
            onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
            onPointerLeave={() => setActive(null)}
            onKeyDown={onKeyDown}
            onFocus={() => setActive((v) => v ?? 0)}
            onBlur={() => setActive(null)}
            style={{ display: "block", touchAction: "pan-y" }}
          >
            {/* Axis labels are index values, not percentages. */}
            {[0, 0.5, 1].map((t) => (
              <g key={t}>
                <line
                  x1={M.left}
                  x2={M.left + innerW}
                  y1={y(t)}
                  y2={y(t)}
                  stroke={t === 0.5 ? "var(--line-strong)" : "var(--grid)"}
                  strokeWidth="1"
                  strokeDasharray={t === 0.5 ? "3 4" : undefined}
                />
                <text
                  x={M.left - 8}
                  y={y(t) + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--ink-faint)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {t.toFixed(1)}
                </text>
              </g>
            ))}

            {pivotIdx >= 0 && (
              <>
                <rect
                  x={x(pivotIdx) - 18}
                  y={M.top}
                  width="36"
                  height={PLOT_H}
                  fill="var(--warn)"
                  opacity="0.08"
                />
                <line
                  x1={x(pivotIdx)}
                  x2={x(pivotIdx)}
                  y1={M.top}
                  y2={M.top + PLOT_H}
                  stroke="var(--warn)"
                  strokeWidth="2"
                />
                <text
                  x={x(pivotIdx)}
                  y={M.top + PLOT_H + 20}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--warn)"
                >
                  R{pivotalRound}
                </text>
              </>
            )}

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

            <path
              d={points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)} ${y(p.value)}`).join(" ")}
              fill="none"
              stroke={accent}
              strokeWidth="2.5"
              strokeLinejoin="round"
            />

            {points.map((p, i) =>
              p.broken ? (
                <path
                  key={p.round}
                  d={`M${x(i)} ${y(p.value) - 6} l-6 6 6 6 6 -6 z`}
                  fill="var(--bad)"
                  stroke="var(--surface-panel)"
                  strokeWidth="1.5"
                />
              ) : null,
            )}

            <circle
              cx={x(last)}
              cy={y(points[last].value)}
              r="5"
              fill={accent}
              stroke="var(--surface-panel)"
              strokeWidth="2"
            />

            <text x={M.left} y={M.top + PLOT_H + 20} fontSize="10" fill="var(--ink-faint)">
              R{points[0].round}
            </text>
            <text
              x={M.left + innerW}
              y={M.top + PLOT_H + 20}
              textAnchor="end"
              fontSize="10"
              fill="var(--ink-faint)"
            >
              R{points[last].round}
            </text>
          </svg>

          {a && (
            <div
              className="tooltip"
              style={{ left: Math.min(Math.max(x(active) - 74, 0), Math.max(w - 160, 0)), top: 0 }}
            >
              <div className="tooltip-title">
                Round {a.round}
                {a.winner ? ` · ${a.winner} won` : ""}
              </div>
              <div className="tooltip-row">
                <span className="tooltip-name">{team} proxy</span>
                <span className="tooltip-val">{a.value.toFixed(2)}</span>
              </div>
              {a.broken && (
                <div className="tooltip-row">
                  <span className="tooltip-name tone-bad">broken buy</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <Callouts
        pivotalRound={pivotalRound}
        brokenRounds={brokenRounds}
        points={points}
        team={team}
      />

      {/* Shipped in the bundle alongside the series, so this caption cannot
          drift away from the feature that produced the numbers. */}
      <p className="footnote">{proxyNote}</p>
    </section>
  );
}

/* Every numeral below is read from the data, never written into the copy —
   the same discipline the writer's numeral check enforces server-side. */
function Callouts({ pivotalRound, brokenRounds, points, team }) {
  const closing = points.slice(-3);
  const closedWell = closing.filter((p) => p.winner === team).length;

  return (
    <div className="callout-row">
      {pivotalRound !== null && (
        <div className="callout" style={{ borderLeftColor: "var(--warn)" }}>
          <div className="callout-kicker tone-warn">R{pivotalRound} · pivotal</div>
          <div className="callout-body">
            The largest single move in the index. It is the round the Analyst narrates.
          </div>
        </div>
      )}
      {brokenRounds.length > 0 && (
        <div className="callout" style={{ borderLeftColor: "var(--bad)" }}>
          <div className="callout-kicker tone-bad">
            {brokenRounds.map((r) => `R${r}`).join(" / ")} · broken buys
          </div>
          <div className="callout-body">
            The loss bonus had funded a real buy and {team} went in short anyway.
          </div>
        </div>
      )}
      <div className="callout" style={{ borderLeftColor: closedWell >= 2 ? "var(--good)" : "var(--ink-neutral)" }}>
        <div className={`callout-kicker ${closedWell >= 2 ? "tone-good" : "tone-muted"}`}>
          R{closing[0].round}–R{closing[closing.length - 1].round} · the close
        </div>
        <div className="callout-body">
          {team} took {closedWell} of the last {closing.length} rounds.
        </div>
      </div>
    </div>
  );
}

function MomentumTable({ points, team }) {
  return (
    <div className="table-scroll">
      <table>
        <caption className="footnote" style={{ textAlign: "left", captionSide: "top" }}>
          {team} momentum proxy per round, with the events annotated on the chart
        </caption>
        <thead>
          <tr>
            <th scope="col">Round</th>
            <th scope="col">Proxy (0–1)</th>
            <th scope="col">Won by</th>
            <th scope="col" className="tl">
              Annotation
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.round}>
              <td>R{p.round}</td>
              <td>{p.value.toFixed(3)}</td>
              <td>{p.winner ?? "—"}</td>
              <td className="tl">
                {[p.pivotal && "pivotal", p.broken && "broken buy"].filter(Boolean).join(", ") ||
                  "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
