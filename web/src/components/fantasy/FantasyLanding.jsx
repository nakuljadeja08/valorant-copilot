/* The pitch, then the one choice a manager makes for the whole season. */

const REGION_LABEL = { americas: "Americas", emea: "EMEA", pacific: "Pacific", china: "China" };
export const regionLabel = (r) => REGION_LABEL[r] ?? r;

export default function FantasyLanding({ season, onStart }) {
  const first = season.events[0];
  const champs = season.events.at(-1);

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">Concept · simulated VCT 2027 season</div>
          <h1 className="page-title">Fantasy VALORANT</h1>
          <p className="lede" style={{ margin: "8px 0 0" }}>
            Pick five pros, two subs and two coaches. Score from what they do on the server: kills,
            clutches, first bloods, map wins. Then open any point and see the exact rounds that earned
            it.
          </p>
        </div>
      </header>

      <div className="section fx-pitch">
        <div className="panel">
          <div className="section-title">One region, then the world</div>
          <p className="lede">
            You pick a home region for the season. At Kickoff and both Cups your squad comes from that
            region's teams. At both Masters and at {champs.name}, you can pick from every qualified team.
          </p>
        </div>
        <div className="panel">
          <div className="section-title">Every point has a receipt</div>
          <p className="lede">
            Points are computed from the round-by-round kill timeline and re-checked by the same
            Watchdog the coaching dashboard uses. A point that can't be re-derived is never shown.
          </p>
        </div>
        <div className="panel">
          <div className="section-title">Play the whole season now</div>
          <p className="lede">
            The season is simulated, so you can replay it week by week: lock a squad, see the points,
            make transfers, use your chips, and finish against eight rival managers.
          </p>
        </div>
      </div>

      <div className="section panel">
        <div className="panel-head">
          <div className="section-title">Choose your home region</div>
          <span className="panel-meta">
            Starts at {first.name}, {first.starts_on}
          </span>
        </div>
        <div className="fx-regions">
          {season.regions.map((r) => (
            <button key={r} type="button" className="fx-region" onClick={() => onStart(r)}>
              <span className="fx-region-name">{regionLabel(r)}</span>
              <span className="fx-region-meta">
                {season.teams.filter((t) => t.region === r).length} teams
              </span>
            </button>
          ))}
        </div>
        <p className="footnote">
          Your season is saved in this browser only. There's no account and nothing is sent anywhere.
        </p>
      </div>
    </>
  );
}
