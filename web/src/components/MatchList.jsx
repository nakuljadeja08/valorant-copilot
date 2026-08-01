import { fmt } from "../lib/data.js";

function total(matches, key) {
  return matches.reduce((sum, m) => sum + (m[key] || 0), 0);
}

export default function MatchList({ index }) {
  const { matches } = index;

  return (
    <>
      <header className="page-head">
        <p className="eyebrow">VALORANT coaching copilot</p>
        <h1>Every claim, and the rows it came from</h1>
        <p className="lede">
          Deterministic rules read a feature store and produce the conclusions. A Watchdog
          re-queries every cited value against the database and drops anything that does not
          match. The language model only phrases what survives — it is never allowed to
          introduce a number. Open any claim to walk the chain back to raw round rows.
        </p>
      </header>

      <div className="kpi-row">
        <Stat label="Matches" value={fmt(index.match_count)} />
        <Stat label="Verified claims" value={fmt(total(matches, "verified_claims"))} />
        <Stat label="Dropped by Watchdog" value={fmt(total(matches, "unverified_claims"))} />
        <Stat label="Raw rows cited" value={fmt(total(matches, "source_rows_cited"))} />
      </div>

      <h2 style={{ fontSize: 15, marginBottom: 12 }}>Matches</h2>
      <div className="match-grid">
        {matches.map((m) => (
          <a className="match-card" key={m.match_id} href={`#/match/${m.match_id}`}>
            <div className="match-map">{m.map_name}</div>
            <div className="scoreline">
              <span className="key-dot blue" aria-hidden="true" />
              <span className="score-num">{m.score.Blue}</span>
              <span className="score-sep">–</span>
              <span className="score-num">{m.score.Red}</span>
              <span className="key-dot red" aria-hidden="true" />
              <span style={{ fontSize: 13, color: "var(--muted)", marginLeft: 6 }}>
                {m.winner ? `${m.winner} won` : "drawn"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <span className="tag">
                <span className="tag-dot ok" aria-hidden="true" />
                {m.verified_claims} verified
              </span>
              {["critical", "warning"].map(
                (sev) =>
                  m.severities?.[sev] > 0 && (
                    <span className="tag" key={sev}>
                      <span className={`tag-dot sev-${sev}`} aria-hidden="true" />
                      {m.severities[sev]} {sev}
                    </span>
                  ),
              )}
            </div>
            <div className="match-id">{m.match_id}</div>
          </a>
        ))}
      </div>
    </>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}
