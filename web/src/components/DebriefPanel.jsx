import ClaimCard from "./TraceView.jsx";

const SEV_ORDER = { critical: 0, warning: 1, info: 2 };

export default function DebriefPanel({ debrief, trace, excluded }) {
  const verified = trace.conclusions
    .filter((c) => c.verified === true)
    .sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h2 style={{ fontSize: 15 }}>Debrief</h2>
          <span className="tag">
            {debrief.used_llm ? "LLM-phrased · numeral check passed" : "Template text"}
          </span>
        </div>
        <p className="card-sub">
          {debrief.used_llm
            ? "A language model phrased the verified findings. Every numeral in the text was checked against the decision trace before it was accepted."
            : "Generated without the language model. The findings are identical either way — only the prose differs."}
        </p>
        <div className="debrief-text">{debrief.text}</div>
        {debrief.rejected_numerals?.length > 0 && (
          <p className="footnote">
            An LLM draft was rejected for containing numbers absent from the trace:{" "}
            {debrief.rejected_numerals.join(", ")}. The template text is shown instead.
          </p>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h2 style={{ fontSize: 15 }}>Claims and their evidence</h2>
          <span className="tag">
            <span className="tag-dot ok" aria-hidden="true" />
            {verified.length} verified · {trace.summary.source_rows_cited} raw rows cited
          </span>
        </div>
        <p className="card-sub">
          Each claim was produced by a deterministic rule, then re-checked against the
          database by the Watchdog. Anything whose cited value no longer matched the store
          was dropped before this page was generated.
        </p>

        {verified.map((c) => (
          <ClaimCard key={c.rule_id + c.claim} conclusion={c} />
        ))}

        {verified.length === 0 && <p className="empty">No verified findings for this match.</p>}

        {excluded?.length > 0 && (
          <p className="footnote">
            Excluded by the Watchdog:{" "}
            {excluded.map((e) => `${e.rule_id} (${e.reason ?? "unchecked"})`).join(", ")}
          </p>
        )}
      </section>
    </>
  );
}
