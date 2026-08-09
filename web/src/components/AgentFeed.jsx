import { fmt } from "../lib/data.js";

const ACCENT = {
  Analyst: "var(--analyst)",
  Economist: "var(--economist)",
  Watchdog: "var(--watchdog)",
};

const SEVERITY_LABEL = { critical: "CRIT", warning: "WARN", info: "INFO" };

/* The season's most severe verified claims, newest layer of the Agent Ops
   direction. Severity is a bordered chip with a text label, never a bare hue:
   warn and bad are ~4 ΔE apart under deuteranopia. */

export default function AgentFeed({ findings }) {
  if (!findings?.length) return null;

  return (
    <section className="section">
      <h2 className="section-title" style={{ marginBottom: 10 }}>
        Latest agent outputs
      </h2>
      <ul className="feed">
        {findings.map((f) => (
          <li
            className="feed-row"
            key={`${f.match_id}:${f.rule_id}:${f.claim}`}
            style={{ "--accent": ACCENT[f.agent] ?? "var(--ink-muted)" }}
          >
            <div className="feed-line">
              <span className="feed-agent">{f.agent}</span>
              <span className={`badge sev-${f.severity}`}>
                {SEVERITY_LABEL[f.severity] ?? f.severity.toUpperCase()}
              </span>
              <span className="feed-claim">{f.claim}</span>
              <span className="feed-meta">
                ✓ verified · {fmt(f.source_rows)} rows
              </span>
            </div>
            <div className="feed-trace">
              <a href={`#/match/${f.match_id}`}>
                ▸ {f.map_name} · {f.rule_id}
              </a>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
