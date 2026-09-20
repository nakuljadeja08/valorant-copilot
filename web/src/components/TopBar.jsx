import { heroTeam } from "../lib/data.js";

/* The sticky client top bar: a breadcrumb of where you are, and the two
   season-level numbers the whole product turns on -- record, and how many
   claims survived the Watchdog. Both are read from the same index bundle every
   view cites; nothing here is invented. */

const CRUMB = {
  "": "Overview",
  matches: "Matches",
  agents: "Agent Pipeline",
  role: "Role Lens",
};

export default function TopBar({ route, matchId, season, matches }) {
  let crumb = CRUMB[route] ?? "Overview";
  if (matchId) {
    const m = matches?.find((x) => x.match_id === matchId);
    crumb = m ? `Match · ${m.map_name}` : "Match";
  }

  // Every first-person number is phrased for one side; say which, rather than
  // implying a "you" the data may not support.
  const side = matches?.[0] ? heroTeam(matches[0]) : "Blue";
  const sub = `Competitive · ${matches?.length ?? 0} matches · hero: ${side}`;

  return (
    <div className="topbar">
      <div className="topbar-edge" aria-hidden="true" />
      <div className="crumb-block">
        <div className="crumb">// {crumb}</div>
        <div className="crumb-sub">{sub}</div>
      </div>

      <div className="topbar-stats">
        {season && (
          <>
            <div className="stat-mini">
              <div className="stat-mini-label">Record</div>
              <div className="stat-mini-value">
                {season.record.wins}
                <span className="tone-muted">–</span>
                {season.record.losses}
              </div>
            </div>
            <span className="stat-div" aria-hidden="true" />
            <div className="stat-mini">
              <div className="stat-mini-label">Verified</div>
              <div className="stat-mini-value tone-good">{season.verified_claims}</div>
            </div>
          </>
        )}
        <div className="account">
          <span className="account-avatar" aria-hidden="true">
            NJ
          </span>
          <span className="account-label">{side} side</span>
        </div>
      </div>
    </div>
  );
}
