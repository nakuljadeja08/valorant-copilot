import { pct } from "../lib/data.js";

/* Round win rate by the buy that went into the round.

   No table twin, deliberately: the label, the denominator and the percentage
   are all printed on every row, so the list already is the table. Adding a
   toggle here would show the same six numbers twice. */

const ORDER = ["full", "eco", "half", "force"];

// Force is the habit the whole overview is about, so it is called out in red;
// full-buy conversion is the thing that works. Everything else is neutral —
// the bar is a magnitude, not a status.
const TONE = { full: "var(--good)", eco: "var(--good)", half: "var(--ink-muted)", force: "var(--bad)" };

export default function BuyTypeBars({ byBuyType }) {
  const rows = ORDER.map((buy) => ({ buy, ...(byBuyType?.[buy] ?? {}) })).filter(
    (r) => r.rounds > 0,
  );
  if (!rows.length) return null;

  const worst = rows.reduce((a, b) => (b.rate < a.rate ? b : a));

  return (
    <section className="panel">
      <h2 className="section-title" style={{ marginBottom: 12 }}>
        Buy type → round wins
      </h2>
      <div className="bar-list">
        {rows.map((r) => (
          <div key={r.buy}>
            <div className="bar-head">
              <span>
                {r.buy.toUpperCase()}{" "}
                <span className="tone-muted">
                  · {r.won} of {r.rounds} rounds
                </span>
              </span>
              <span className="bar-value">{pct(r.rate)}</span>
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${Math.round(r.rate * 100)}%`, background: TONE[r.buy] }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="footnote">
        {worst.buy === "force"
          ? "Forcing is the worst-converting buy you make."
          : `${worst.buy.toUpperCase()} is the worst-converting buy you make.`}
      </p>
    </section>
  );
}
