import { useState } from "react";

const PREVIEW_ROWS = 8;

const short = (id) => (id && id.length > 8 ? `${id.slice(0, 8)}…` : id ?? "");
const num = (v) =>
  Number.isInteger(v) ? String(v) : Number(v).toFixed(2).replace(/\.?0+$/, "");

/** One rule's conclusion, with the chain that produced it hidden behind a
 *  disclosure: claim → feature rows → the raw rows each was computed from. */
export default function ClaimCard({ conclusion }) {
  const [open, setOpen] = useState(false);
  const rowCount = conclusion.evidence.reduce((n, e) => n + e.source_rows.length, 0);

  return (
    <article className="claim">
      <div className="claim-meta">
        <span className="tag">
          <span className={`tag-dot sev-${conclusion.severity}`} aria-hidden="true" />
          {conclusion.severity}
        </span>
        <span className="tag">{conclusion.agent}</span>
        {conclusion.verified === true && (
          <span className="tag">
            <span className="tag-dot ok" aria-hidden="true" />
            Watchdog verified
          </span>
        )}
        <span className="rule-id">{conclusion.rule_id}</span>
      </div>

      <p className="claim-text">{conclusion.claim}</p>

      <button className="disclose" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? "Hide decision trace" : `Show decision trace — ${conclusion.evidence.length} feature row(s), ${rowCount} raw row(s)`}
      </button>

      {open && (
        <div className="trace">
          <div className="chain">
            <span>raw rows</span>
            <span aria-hidden="true">→</span>
            <span>feature rows</span>
            <span aria-hidden="true">→</span>
            <span>{conclusion.rule_id}</span>
            <span aria-hidden="true">→</span>
            <span>claim</span>
          </div>
          {conclusion.evidence.map((e, i) => (
            <Evidence key={`${e.feature.name}-${e.feature.round_num}-${i}`} evidence={e} />
          ))}
        </div>
      )}
    </article>
  );
}

function Evidence({ evidence }) {
  const [showAll, setShowAll] = useState(false);
  const { feature, source_rows: rows } = evidence;
  const shown = showAll ? rows : rows.slice(0, PREVIEW_ROWS);

  return (
    <div className="evidence">
      <div className="evidence-head">
        <span className="feature-name">{feature.name}</span>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          {feature.round_num === -1 ? "match-scoped" : `round ${feature.round_num}`} ·{" "}
          {feature.scope}
        </span>
        <span className="feature-value">= {num(feature.value)}</span>
      </div>

      <ul className="rows">
        {shown.map((r, i) => (
          <li key={i}>
            {r.table}
            {r.round_num !== undefined && r.round_num !== null ? ` · round ${r.round_num}` : ""}
            {r.puuid ? ` · player ${short(r.puuid)}` : ""}
          </li>
        ))}
      </ul>

      {rows.length > PREVIEW_ROWS && (
        <button className="disclose" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer rows" : `Show all ${rows.length} rows`}
        </button>
      )}
      {rows.length === 0 && <p className="footnote">No raw rows cited.</p>}
    </div>
  );
}
