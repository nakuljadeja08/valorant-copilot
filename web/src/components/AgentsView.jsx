import { useMemo, useState } from "react";

import { fmt, useJson } from "../lib/data.js";
import AgentPipeline from "./AgentPipeline.jsx";
import AgentFeed from "./AgentFeed.jsx";

const PAGE = 20;

export default function AgentsView({ season }) {
  // Its own bundle: every verified claim is roughly three times the size of the
  // whole index, and no other route needs it.
  const { data, error } = useJson("agents.json");
  const [agent, setAgent] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [limit, setLimit] = useState(PAGE);

  const findings = data?.findings ?? [];
  const agents = useMemo(
    () => [...new Set(findings.map((f) => f.agent))].sort(),
    [findings],
  );

  const shown = useMemo(
    () =>
      findings.filter(
        (f) =>
          (agent === "all" || f.agent === agent) &&
          (severity === "all" || f.severity === severity),
      ),
    [findings, agent, severity],
  );

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Agent pipeline</h1>
        <p className="lede" style={{ margin: 0 }}>
          Deterministic rules read the feature store. A Watchdog re-queries every cited value
          against the database and drops anything that does not match. The language model only
          phrases what survives — it never introduces a number.
        </p>
      </header>

      <AgentPipeline season={season} />

      <div className="section">
        <div className="panel-head">
          <h2 className="section-title">
            Findings — {fmt(shown.length)}
            {shown.length !== findings.length && ` of ${fmt(findings.length)}`}
          </h2>
          <span className="panel-meta">
            Watchdog: {fmt(season?.source_rows_cited)} rows re-checked ·{" "}
            {fmt(season?.unverified_claims)} dropped
          </span>
        </div>

        <div className="chip-row" style={{ marginBottom: 14 }}>
          <span className="chip-label" id="agent-label">
            Agent
          </span>
          <span role="radiogroup" aria-labelledby="agent-label" className="chip-row">
            {["all", ...agents].map((a) => (
              <button
                key={a}
                type="button"
                role="radio"
                className="chip"
                aria-checked={agent === a}
                onClick={() => {
                  setAgent(a);
                  setLimit(PAGE);
                }}
              >
                {a === "all" ? "All" : a}
              </button>
            ))}
          </span>
          <span className="chip-label" id="sev-label" style={{ marginLeft: 8 }}>
            Severity
          </span>
          <span role="radiogroup" aria-labelledby="sev-label" className="chip-row">
            {["all", "critical", "warning", "info"].map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                className="chip"
                aria-checked={severity === s}
                onClick={() => {
                  setSeverity(s);
                  setLimit(PAGE);
                }}
              >
                {s === "all" ? "All" : s}
              </button>
            ))}
          </span>
        </div>

        {error && <p className="empty">Could not load agents.json ({String(error.message)}).</p>}
        {!data && !error && <p className="empty">Loading findings…</p>}

        {data && <AgentFeed findings={shown.slice(0, limit)} />}
        {data && !shown.length && <p className="empty">No findings match that filter.</p>}

        {shown.length > limit && (
          <p style={{ textAlign: "center", marginTop: 12 }}>
            <button className="table-toggle" onClick={() => setLimit((n) => n + PAGE)}>
              Show {Math.min(PAGE, shown.length - limit)} more
            </button>
          </p>
        )}
      </div>
    </>
  );
}
