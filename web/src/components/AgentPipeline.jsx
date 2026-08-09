import { fmt } from "../lib/data.js";

/* The multi-agent pipeline, folded into the overview from the Agent Ops
   direction.

   Rendered as an ordered list rather than a grid of divs: the arrows are
   decoration and the reading order has to carry the sequence on its own for
   anyone not seeing the layout. */

const AGENTS = [
  { name: "Analyst", role: "pivotal rounds, plants, trades", accent: "var(--analyst)" },
  { name: "Economist", role: "buys, banks, broken buys", accent: "var(--economist)" },
  { name: "Watchdog", role: "re-checks every cited value", accent: "var(--watchdog)" },
];

export default function AgentPipeline({ season, findings }) {
  // Findings are attributed by the agent that produced them; the Watchdog does
  // not author claims, it verifies them, so its counters are the verification
  // totals rather than a share of the findings.
  const byAgent = {};
  for (const f of findings ?? []) {
    byAgent[f.agent] = (byAgent[f.agent] ?? 0) + 1;
  }

  const stat = (name) => {
    if (name === "Watchdog") {
      return [
        `${fmt(season.verified_claims)} verified`,
        `${fmt(season.unverified_claims)} dropped`,
        season.unverified_claims === 0 ? "tone-good" : "tone-bad",
      ];
    }
    return [`${fmt(byAgent[name] ?? 0)} in top findings`, null, null];
  };

  return (
    <section className="section" id="agents">
      <h2 className="page-title" style={{ fontSize: 28, marginBottom: 4 }}>
        Agent pipeline
      </h2>
      <p className="lede" style={{ marginBottom: 16 }}>
        Deterministic rules read the feature store. A Watchdog re-queries every cited value
        against the database and drops anything that does not match. The language model only
        phrases what survives — it never introduces a number.
      </p>

      <ol className="pipeline">
        <li className="pipeline-node">
          <span className="eyebrow">Input</span>
          <span className="pipeline-node-name">Feature store</span>
          <span className="pipeline-node-meta">
            {fmt(season.rounds)} rounds
            <br />
            {fmt(season.source_rows_cited)} rows cited
          </span>
        </li>

        <li className="pipeline-arrow" aria-hidden="true">
          →
        </li>

        <li>
          <ul className="agent-cards">
            {AGENTS.map((a) => {
              const [primary, secondary, tone] = stat(a.name);
              return (
                <li className="agent-card" key={a.name} style={{ "--accent": a.accent }}>
                  <div className="agent-card-name">{a.name}</div>
                  <div className="agent-card-role">{a.role}</div>
                  <div className="agent-card-stat">
                    {primary}
                    {secondary && (
                      <>
                        <br />
                        <span className={tone}>{secondary}</span>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </li>

        <li className="pipeline-arrow" aria-hidden="true">
          →
        </li>

        <li className="pipeline-node">
          <span className="eyebrow">Output</span>
          <span className="pipeline-node-name">Report writer</span>
          <span className="pipeline-node-meta">
            LLM phrases only
            <br />
            never adds a number
          </span>
        </li>
      </ol>
    </section>
  );
}
