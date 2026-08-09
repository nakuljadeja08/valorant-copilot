/* A KPI tile. `tone` colours the value and the footnote together; `alert` adds
   the full red border the design reserves for the one worst habit. */

export default function Tile({ label, value, foot, tone = "neutral", alert = false, dense }) {
  const toneClass = tone === "neutral" ? "" : ` tone-${tone}`;

  return (
    <div className={`tile${alert ? " alert" : ""}${dense ? " dense" : ""}`}>
      <div className="tile-label">{label}</div>
      <div className={`tile-value${toneClass}`}>{value}</div>
      {foot && <div className={`tile-foot${toneClass}`}>{foot}</div>}
    </div>
  );
}
